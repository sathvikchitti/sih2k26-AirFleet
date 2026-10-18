"""Reserve-override authorization and atomicity contract.

The demo role headers are caller-selected labels, not authenticated identity.
These tests cover the configured capability checks and reserve arithmetic.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import AuditRepository, InventoryRepository, reset, snapshot
from app.services import maintenance_service, transfer_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(app) as instance:
        yield instance
    reset()


def _set_stock(quantity=6, reserved=1, minimum=2):
    inv = InventoryRepository.find("bravo", "HP-204")
    return InventoryRepository.update(
        inv["id"], quantity=quantity, reserved=reserved,
        minimum_reserve=minimum, condition_pct=90,
    )


def _pending(client, quantity=5):
    response = client.post(
        "/api/transfers",
        json={"part_number": "HP-204", "source_base": "bravo",
              "dest_base": "alpha", "quantity": quantity},
        headers={"X-Demo-Role": "logistics"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_logistics_override_crosses_floor_and_audits_resolved_actor_and_donor(client):
    _set_stock()
    transfer = _pending(client)

    response = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True, "actor": "commander"},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 200, response.text
    stock = InventoryRepository.find("bravo", "HP-204")
    assert (stock["quantity"], stock["reserved"], stock["minimum_reserve"]) == (1, 1, 2)
    overrides = [row for row in AuditRepository.list_all()
                 if row["event_type"] == "RESERVE_OVERRIDE_APPLIED"]
    assert len(overrides) == 1
    assert overrides[0]["actor"] == "logistics"
    assert overrides[0]["details"]["donor_base"] == "bravo"
    assert overrides[0]["entity_id"] == transfer["id"]


@pytest.mark.parametrize("headers", [
    {},
    {"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
    {"X-Demo-Role": "commander"},
    {"X-Demo-Role": "not-a-role"},
])
def test_override_flag_does_not_grant_transfer_permission(client, headers):
    _set_stock()
    transfer = _pending(client)
    before = snapshot()

    response = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True, "actor": "logistics"},
        headers=headers,
    )

    assert response.status_code == 403, response.text
    assert snapshot() == before


def test_no_override_rejects_reserve_breach_atomically(client):
    _set_stock()
    transfer = _pending(client)
    before = snapshot()

    response = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": False},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 400
    assert "below its minimum reserve" in response.json()["detail"]
    assert snapshot() == before


def test_override_cannot_spend_reserved_units_and_rejection_is_atomic(client):
    _set_stock()
    transfer = _pending(client, quantity=6)
    before = snapshot()

    response = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 400
    assert "unreserved unit" in response.json()["detail"]
    assert snapshot() == before


def test_override_cannot_spend_unit_reserved_by_active_maintenance(client):
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    assert work_order is not None
    started = maintenance_service.start_maintenance(work_order["id"])
    assert started["status"] == "IN_PROGRESS"
    inv = InventoryRepository.find("alpha", "AV-077")
    assert inv["reserved"] == 1

    created = client.post(
        "/api/transfers",
        json={"part_number": "AV-077", "source_base": "alpha",
              "dest_base": "bravo", "quantity": inv["quantity"]},
        headers={"X-Demo-Role": "logistics"},
    )
    assert created.status_code == 200, created.text
    before_approval = snapshot()

    response = client.post(
        f"/api/transfers/{created.json()['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 400
    assert "unreserved unit" in response.json()["detail"]
    assert snapshot() == before_approval

    completed = maintenance_service.complete_maintenance(work_order["id"])
    remaining = InventoryRepository.find("alpha", "AV-077")
    assert completed["status"] == "COMPLETED"
    assert (remaining["quantity"], remaining["reserved"]) == (1, 0)


def test_override_flag_at_exact_reserve_boundary_does_not_claim_override(client):
    _set_stock()
    transfer = _pending(client, quantity=3)  # 6 - 3 - 1 reserved == minimum 2

    response = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "logistics"},
    )

    assert response.status_code == 200, response.text
    assert InventoryRepository.find("bravo", "HP-204")["quantity"] == 3
    assert not [row for row in AuditRepository.list_all()
                if row["event_type"] == "RESERVE_OVERRIDE_APPLIED"]


def test_commander_recommendation_flag_cannot_select_infeasible_reserve_donor(client):
    work_order = maintenance_service.create_manual_work_order("A19", "HP-204")
    assert work_order is not None
    for inv in InventoryRepository.find_all_for_part("HP-204"):
        if inv["base_id"] != "alpha":
            InventoryRepository.update(inv["id"], minimum_reserve=inv["quantity"])
    before = snapshot()

    response = client.post(
        f"/api/work-orders/{work_order['id']}/recommendation/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "commander"},
    )

    assert response.status_code == 400
    assert "no feasible source" in response.json()["detail"]
    assert snapshot() == before


def test_base_and_commander_cannot_use_direct_transfer_approval_route(client):
    transfer = _pending(client, quantity=1)
    before = snapshot()

    base = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
    )
    commander = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "commander"},
    )

    assert base.status_code == commander.status_code == 403
    assert snapshot() == before
