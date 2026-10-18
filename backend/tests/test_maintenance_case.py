"""Read-only and explicit-linkage tests for maintenance case timelines."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import main
from app.repositories import InventoryRepository, reset, store
from app.services.ml import set_provider
from app.services.ml.mock_provider import MockMLProvider


@pytest.fixture
def case_client(monkeypatch):
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    set_provider(MockMLProvider())
    reset()
    yield TestClient(main.app)
    reset()
    set_provider(MockMLProvider())


def test_case_timeline_links_prediction_through_completed_transfer_and_is_read_only(case_client):
    # A35 has a deliberately open HIGH_PRESSURE event in the seed. Remove its
    # local part so triage and the later approval must use a real donor.
    local = InventoryRepository.find("charlie", "HP-204")
    InventoryRepository.update(local["id"], quantity=0, status="STOCKOUT")
    headers = {"X-Demo-Role": "base", "X-Demo-Base": "charlie"}

    first_prediction = case_client.post("/api/aircraft/A35/predict", headers=headers)
    second_prediction = case_client.post("/api/aircraft/A35/predict", headers=headers)
    assert first_prediction.status_code == second_prediction.status_code == 200
    first_event = first_prediction.json()["predicted_maintenance_event"]
    second_event = second_prediction.json()["predicted_maintenance_event"]
    assert first_event["id"] == second_event["id"] == "PM-005"
    # This seed event predates prediction-history records. New observations
    # may be linked as latest evidence, but must not be backfilled as origin.
    assert first_event.get("prediction_history_id") is None
    assert first_event.get("prediction_history_origin_status") == "legacy_unknown"
    assert second_event.get("prediction_history_id") is None
    assert second_event.get("prediction_history_origin_status") == "legacy_unknown"
    assert len(second_event["prediction_history_ids"]) >= 1

    history_ids = list(second_event["prediction_history_ids"])
    triaged = case_client.post(
        f"/api/maintenance/events/{second_event['id']}/work-order",
        json={"required_component": "HP-204", "actor": "base"}, headers=headers,
    )
    assert triaged.status_code == 200
    work_order = triaged.json()
    work_order_id = work_order["id"]
    assert work_order["aircraft_id"] == "A35"
    assert work_order["predicted_event_id"] == "PM-005"
    assert work_order["required_component"] == "HP-204"
    assert work_order["component_source"] == "human_selected"

    recommendation_response = case_client.get(
        f"/api/work-orders/{work_order_id}/recommendation"
    )
    assert recommendation_response.status_code == 200
    recommendation = recommendation_response.json()
    assert recommendation["recommended"]["source_base"] == "bravo"
    recommendation_snapshot = {
        "source_base": recommendation["recommended"]["source_base"],
        "eta_hours": recommendation["recommended"]["eta_hours"],
        "expected_downtime_hours": recommendation["recommended"]["expected_downtime_hours"],
    }

    # A rejection is an audit decision only: stock, transfer rows, and the
    # work-order state remain unchanged until a separate approval action.
    before_reject = deepcopy(store())
    rejected = case_client.post(
        "/api/recommendations/A35/reject",
        json={"actor": "commander", "reason": "Independent review required"},
        headers={"X-Demo-Role": "commander"},
    )
    assert rejected.status_code == 200
    after_reject = store()
    assert after_reject["inventory"] == before_reject["inventory"]
    assert after_reject["transfers"] == before_reject["transfers"]
    assert next(row for row in after_reject["work_orders"] if row["id"] == work_order_id)["status"] == work_order["status"]

    approved = case_client.post(
        f"/api/work-orders/{work_order_id}/recommendation/approve",
        json={"actor": "commander"}, headers={"X-Demo-Role": "commander"},
    )
    assert approved.status_code == 200
    transfer = approved.json()["transfer"]
    transfer_id = transfer["id"]
    assert transfer["work_order_id"] == work_order_id
    assert transfer["source_base"] == "bravo" and transfer["dest_base"] == "charlie"
    assert transfer["status"] == "IN_TRANSIT"

    received = case_client.post(
        f"/api/transfers/{transfer_id}/receive",
        headers={"X-Demo-Role": "logistics"},
    )
    assert received.status_code == 200
    started = case_client.post(
        f"/api/maintenance/work-orders/{work_order_id}/start",
        headers={"X-Demo-Role": "base", "X-Demo-Base": "charlie"},
    )
    assert started.status_code == 200
    completed = case_client.post(
        f"/api/maintenance/work-orders/{work_order_id}/complete",
        headers={"X-Demo-Role": "base", "X-Demo-Base": "charlie"},
    )
    assert completed.status_code == 200

    # Capture the live state after the actions. A case GET must not generate
    # another prediction/recommendation, change stock, or append audit rows.
    before_get = deepcopy(store())
    response = case_client.get(f"/api/aircraft/A35/maintenance-timeline?work_order_id={work_order_id}")
    assert response.status_code == 200
    assert store() == before_get
    case = response.json()
    assert case["mutated_state"] is False
    assert case["aircraft_id"] == "A35"
    assert [row["id"] for row in case["work_orders"]] == [work_order_id]
    assert [row["id"] for row in case["events"]] == ["PM-005"]
    assert {row["id"] for row in case["prediction_history"]} == set(history_ids)
    assert case["events"][0].get("prediction_history_id") is None
    assert case["events"][0]["prediction_history_origin_status"] == "legacy_unknown"
    assert case["events"][0]["latest_prediction_history_id"] == history_ids[-1]
    assert set(case["events"][0]["prediction_history_ids"]) == set(history_ids)
    assert case["linkage"]["unknown_origin_event_ids"] == ["PM-005"]
    assert case["work_orders"][0]["predicted_event_id"] == "PM-005"
    assert [row["id"] for row in case["transfers"]] == [transfer_id]
    assert all(row["aircraft_id"] == "A35" for row in case["events"])
    assert all(row["work_order_id"] == work_order_id for row in case["transfers"])

    generated = case["recommendations"]
    assert len(generated) >= 1
    first_stored_snapshot = generated[0]["details"]["recommended_candidate"]
    assert first_stored_snapshot["source_base"] == recommendation_snapshot["source_base"]
    assert first_stored_snapshot["eta_hours"] == recommendation_snapshot["eta_hours"]
    assert first_stored_snapshot["expected_downtime_hours"] == recommendation_snapshot["expected_downtime_hours"]
    assert {row["event_type"] for row in case["decisions"]} == {
        "RECOMMENDATION_REJECTED", "RECOMMENDATION_APPROVED",
    }
    rejected_audit = next(row for row in case["decisions"]
                          if row["event_type"] == "RECOMMENDATION_REJECTED")
    approved_audit = next(row for row in case["decisions"]
                          if row["event_type"] == "RECOMMENDATION_APPROVED")
    assert rejected_audit["actor"] == "commander"
    assert rejected_audit["details"]["reason"] == "Independent review required"
    assert approved_audit["actor"] == "commander"
    assert approved_audit["details"]["transfer_id"] == transfer_id
    created_audit = next(row for row in case["timeline"]
                         if row.get("event_type") == "WORK_ORDER_CREATED")
    assert created_audit["details"]["component_source"] == "human_selected"
    transitions = [row["details"] for row in case["timeline"]
                   if row.get("event_type") == "WORK_ORDER_STATUS_CHANGED"]
    assert { (row["previous_status"], row["status"]) for row in transitions } >= {
        ("WAITING_FOR_RESOURCE", "RESOURCE_AVAILABLE"),
        ("RESOURCE_AVAILABLE", "IN_PROGRESS"),
        ("IN_PROGRESS", "COMPLETED"),
    }
    assert all(row["previous_status"] != row["status"] for row in transitions)
    assert {row["event_type"] for row in case["timeline"] if row["record_type"] == "audit"} >= {
        "TRANSFER_CREATED", "TRANSFER_STARTED", "TRANSFER_RECEIVED",
        "MAINTENANCE_STARTED", "MAINTENANCE_COMPLETED",
    }


def test_manual_case_is_unlinked_and_cross_aircraft_records_do_not_leak(case_client):
    created = case_client.post(
        "/api/maintenance/work-orders?aircraft_id=A33",
        json={"component": "AV-077", "issue": "Manual inspection", "actor": "base"},
        headers={"X-Demo-Role": "base", "X-Demo-Base": "charlie"},
    )
    assert created.status_code == 200
    manual = created.json()
    assert manual["source"] == "MANUAL"
    assert manual["predicted_event_id"] is None

    response = case_client.get(
        f"/api/aircraft/A33/maintenance-timeline?work_order_id={manual['id']}"
    )
    assert response.status_code == 200
    case = response.json()
    assert [row["id"] for row in case["work_orders"]] == [manual["id"]]
    assert case["events"] == []
    assert case["prediction_history"] == []
    assert case["transfers"] == []

    a35_case = case_client.get("/api/aircraft/A35/maintenance-timeline")
    assert a35_case.status_code == 200
    assert all(row["aircraft_id"] == "A35" for row in a35_case.json()["work_orders"])
    assert manual["id"] not in {row["id"] for row in a35_case.json()["work_orders"]}
    assert case_client.get(
        f"/api/aircraft/A35/maintenance-timeline?work_order_id={manual['id']}"
    ).status_code == 404


def test_legacy_prediction_and_event_without_explicit_history_link_are_unlinked(case_client):
    from app.services.audit_service import prediction_generated

    prediction_generated("A35", {
        "source": "legacy-test", "health_score": 72, "risk_level": "MEDIUM",
        "rul": 55, "subsystem": "HIGH_PRESSURE",
    })

    response = case_client.get("/api/aircraft/A35/maintenance-timeline")

    assert response.status_code == 200
    case = response.json()
    assert "PM-005" in case["linkage"]["unlinked_event_ids"]
    legacy_rows = [row for row in case["timeline"]
                   if row["record_type"] == "audit" and row["link_status"] == "unlinked"]
    assert legacy_rows
    assert any(row["record"]["event_type"] == "PREDICTION_GENERATED"
               for row in legacy_rows)


def test_case_timeline_unknown_aircraft_and_mismatched_work_order_return_404(case_client):
    assert case_client.get("/api/aircraft/UNKNOWN/maintenance-timeline").status_code == 404
    assert case_client.get(
        "/api/aircraft/A35/maintenance-timeline?work_order_id=WO-1042"
    ).status_code == 404


def test_singular_history_link_and_offsets_are_respected_without_mutating_snapshot(monkeypatch):
    from app.services import case_timeline_service

    state = {
        "aircraft": [{"id": "A1"}],
        "prediction_history": [
            {"id": "PH-1", "aircraft_id": "A1", "timestamp": "2026-10-17T06:15:00+05:30"},
            {"id": "PH-2", "aircraft_id": "A1", "timestamp": "2026-10-17T00:30:00Z"},
        ],
        "predicted_events": [{
            "id": "PM-1", "aircraft_id": "A1", "prediction_history_id": "PH-1",
            "created_at": "2026-10-17T06:15:00+05:30",
        }],
        "work_orders": [], "transfers": [], "audit": [],
    }
    before = deepcopy(state)
    monkeypatch.setattr(case_timeline_service, "snapshot", lambda: state)

    case = case_timeline_service.maintenance_case_timeline("A1")

    assert state == before
    assert [row["id"] for row in case["prediction_history"]] == ["PH-2", "PH-1"]
    timeline_histories = [row for row in case["timeline"] if row["record_type"] == "prediction_history"]
    assert {row["record_id"]: row["link_status"] for row in timeline_histories} == {
        "PH-1": "linked", "PH-2": "aircraft_scoped",
    }

