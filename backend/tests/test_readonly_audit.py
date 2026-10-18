"""Read endpoints are pure; explicit decisions and inventory changes audit."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import InventoryRepository, reset, snapshot
from app.services import recommendation_service
from app.services.transfer_service import TransferError, approve_recommendation


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(app) as test_client:
        yield test_client
    reset()


def test_recommendation_and_read_only_gets_do_not_change_any_repository_state(client):
    before = snapshot()
    paths = [
        "/api/work-orders/WO-1042/recommendation",
        "/api/work-orders/WO-1042/recommendation",
        "/api/recommendations/A17",
        "/api/recommendations/A17",
        "/api/aircraft/A17",
        "/api/aircraft/A17",
        "/api/resources/allocation-preview",
        "/api/fleet/readiness-simulation?horizon_hours=4",
        "/api/aircraft/A17/maintenance-timeline?work_order_id=WO-1042",
    ]
    responses = [client.get(path) for path in paths]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json().keys() == responses[1].json().keys()
    assert responses[2].json().keys() == responses[3].json().keys()
    assert snapshot() == before


def test_direct_recommendation_evaluation_is_pure(client):
    before = snapshot()
    first = recommendation_service.evaluate_candidates("WO-1042")
    second = recommendation_service.evaluate_candidates("WO-1042")
    assert first == second
    assert snapshot() == before


def test_successful_explicit_approval_records_evaluation_and_approval(client):
    before_audit = len(snapshot()["audit"])
    response = client.post(
        "/api/work-orders/WO-1042/recommendation/approve",
        json={"actor": "commander"}, headers={"X-Demo-Role": "commander"},
    )
    assert response.status_code == 200
    appended = snapshot()["audit"][before_audit:]
    assert [row["event_type"] for row in appended][-2:] == [
        "RECOMMENDATION_GENERATED", "RECOMMENDATION_APPROVED",
    ]
    assert appended[-2]["actor"] == appended[-1]["actor"] == "commander"


def test_failed_approval_leaves_full_state_unchanged(client):
    for base in ("bravo", "charlie"):
        inv = InventoryRepository.find(base, "HP-204")
        InventoryRepository.update(inv["id"], minimum_reserve=inv["quantity"])
    before = snapshot()
    with pytest.raises(TransferError, match="no feasible source"):
        approve_recommendation("WO-1042", actor="commander")
    assert snapshot() == before


def test_rejection_is_still_an_explicit_audited_decision(client):
    before = snapshot()
    response = client.post(
        "/api/recommendations/A17/reject",
        json={"actor": "commander", "reason": "defer"},
        headers={"X-Demo-Role": "commander"},
    )
    assert response.status_code == 200
    after = snapshot()
    added = after["audit"][len(before["audit"]):]
    assert len(added) == 1
    assert added[0]["event_type"] == "RECOMMENDATION_REJECTED"
    assert after["transfers"] == before["transfers"]
    assert {key: after[key] for key in after if key not in {"audit", "audit_seq"}} == {
        key: before[key] for key in before if key not in {"audit", "audit_seq"}
    }


def test_inventory_update_audits_selected_actor_and_changed_fields(client):
    inv = InventoryRepository.get("inv-03")
    old_condition = inv["condition_pct"]
    before_count = len(snapshot()["audit"])
    response = client.patch(
        f"/api/inventory/{inv['id']}", json={"condition_pct": old_condition - 1},
        headers={"X-Demo-Role": "logistics"},
    )
    assert response.status_code == 200
    events = snapshot()["audit"][before_count:]
    assert len(events) == 1
    assert events[0]["event_type"] == "INVENTORY_UPDATED"
    assert events[0]["actor"] == "logistics"
    assert events[0]["details"]["changed_fields"]["condition_pct"] == {
        "before": old_condition, "after": old_condition - 1,
    }


@pytest.mark.parametrize(("headers", "payload", "status"), [
    ({"X-Demo-Role": "commander"}, {"condition_pct": 75}, 403),
    ({"X-Demo-Role": "logistics"}, {"condition_pct": 101}, 422),
])
def test_denied_or_invalid_inventory_edit_has_no_audit_or_state_change(client, headers, payload, status):
    inv = InventoryRepository.get("inv-03")
    before = snapshot()
    response = client.patch(f"/api/inventory/{inv['id']}", json=payload, headers=headers)
    assert response.status_code == status
    assert snapshot() == before
