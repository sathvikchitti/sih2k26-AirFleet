"""Focused stock/reservation integrity regressions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import AuditRepository, InventoryRepository, TransferRepository, reset, snapshot
from app.services import maintenance_service, transfer_service


def _set_stock(*, quantity=6, reserved=1, minimum=2):
    inv = InventoryRepository.find("bravo", "HP-204")
    InventoryRepository.update(
        inv["id"], quantity=quantity, reserved=reserved,
        minimum_reserve=minimum, condition_pct=90,
    )
    return InventoryRepository.get(inv["id"])


def _pending(quantity):
    return transfer_service.create_transfer(
        "HP-204", "bravo", "alpha", quantity=quantity,
    )


def test_transfer_reserve_uses_after_minus_reserved_and_reject_is_atomic():
    reset()
    inv = _set_stock()
    transfer = _pending(4)
    before = snapshot()

    with pytest.raises(transfer_service.TransferError, match="unreserved unit"):
        transfer_service.approve_transfer(transfer["id"])

    assert snapshot() == before
    assert InventoryRepository.get(inv["id"])["quantity"] == 6


def test_transfer_at_minimum_reserve_boundary_is_accepted():
    reset()
    inv = _set_stock()
    transfer = _pending(3)

    approved = transfer_service.approve_transfer(transfer["id"])

    assert approved["status"] == "IN_TRANSIT"
    assert InventoryRepository.get(inv["id"])["quantity"] == 3
    assert InventoryRepository.get(inv["id"])["reserved"] == 1
    assert 3 - 1 == 2  # remaining unreserved stock equals the minimum reserve


def test_authorized_reserve_override_preserves_committed_units_and_is_audited():
    reset()
    inv = _set_stock()
    transfer = _pending(5)

    approved = transfer_service.approve_transfer(
        transfer["id"], actor="logistics", allow_reserve_override=True,
    )

    row = InventoryRepository.get(inv["id"])
    assert approved["status"] == "IN_TRANSIT"
    assert row["quantity"] == row["reserved"] == 1
    assert any(event["event_type"] == "RESERVE_OVERRIDE_APPLIED"
               for event in AuditRepository.list_all())

    # Even an explicit minimum-reserve override cannot spend a reserved unit.
    rejected = _pending(1)
    before = snapshot()
    with pytest.raises(transfer_service.TransferError, match="unreserved unit"):
        transfer_service.approve_transfer(rejected["id"], allow_reserve_override=True)
    assert snapshot() == before


def test_concurrent_approvals_cannot_overspend_shared_stock():
    reset()
    inv = _set_stock()
    transfers = [_pending(3), _pending(3)]
    gate = Barrier(2)

    def approve(transfer_id):
        gate.wait()
        try:
            transfer_service.approve_transfer(transfer_id)
            return "approved"
        except transfer_service.TransferError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(approve, (row["id"] for row in transfers)))

    assert sorted(outcomes) == ["approved", "rejected"]
    assert InventoryRepository.get(inv["id"])["quantity"] == 3
    persisted = [TransferRepository.get(row["id"]) for row in transfers]
    assert sum(row["status"] == "IN_TRANSIT" for row in persisted) == 1


def test_inventory_patch_cannot_release_active_maintenance_reservation():
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    assert work_order["status"] == "RESOURCE_AVAILABLE"
    started = maintenance_service.start_maintenance(work_order["id"])
    assert started["resource_reserved"] is True
    inv = InventoryRepository.find("alpha", "AV-077")
    before = snapshot()

    response = TestClient(app).patch(
        f"/api/inventory/{inv['id']}", json={"reserved": 0},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 400
    assert "active work-order commitment" in response.json()["detail"]
    assert snapshot() == before
    completed = maintenance_service.complete_maintenance(work_order["id"])
    assert completed["status"] == "COMPLETED"
    assert InventoryRepository.find("alpha", "AV-077")["quantity"] == 1
    assert InventoryRepository.find("alpha", "AV-077")["reserved"] == 0
