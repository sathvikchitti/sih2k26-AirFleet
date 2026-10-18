"""Detailed audit context for successful reserve-floor crossings."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import AuditRepository, InventoryRepository, reset


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


def test_override_audit_records_authorized_dispatch_context(client):
    inventory = InventoryRepository.find("bravo", "HP-204")
    InventoryRepository.update(
        inventory["id"], quantity=6, reserved=1,
        minimum_reserve=2, condition_pct=90,
    )
    created = client.post(
        "/api/transfers",
        json={"part_number": "HP-204", "source_base": "bravo",
              "dest_base": "alpha", "quantity": 5},
        headers={"X-Demo-Role": "logistics"},
    )
    assert created.status_code == 200, created.text
    transfer = created.json()

    approved = client.post(
        f"/api/transfers/{transfer['id']}/approve",
        json={"allow_reserve_override": True},
        headers={"X-Demo-Role": "logistics"},
    )
    assert approved.status_code == 200, approved.text
    current = InventoryRepository.get(inventory["id"])
    assert current["quantity"] == 1
    assert approved.json()["status"] == "IN_TRANSIT"

    event, = [row for row in AuditRepository.list_all()
              if row["event_type"] == "RESERVE_OVERRIDE_APPLIED"]
    assert event["entity_type"] == "work_order"
    assert event["entity_id"] == transfer["id"]  # unlinked transfer is the audit subject
    assert event["actor"] == "logistics"
    details = event["details"]
    assert details == {
        "actor_role": "logistics",
        "donor_base": "bravo",
        "transfer_id": transfer["id"],
        "inventory_id": inventory["id"],
        "source_base": "bravo",
        "destination_base": "alpha",
        "quantity_requested": 5,
        "quantity_before": 6,
        "unreserved_before": 5,
        "available_for_transfer_before": 3,
        "reserved_quantity": 1,
        "minimum_reserve": 2,
        "quantity_after": 1,
        "unreserved_after": 0,
        "available_for_transfer_after": 0,
        "reserve_floor_crossed": True,
        "decision_outcome": "APPROVED",
        "resulting_transfer_status": "IN_TRANSIT",
    }
