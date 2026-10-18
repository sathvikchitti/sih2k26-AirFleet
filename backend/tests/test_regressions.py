"""Focused regression tests for prediction, ranking and state invariants.

Run from backend: `python -m pytest tests/test_regressions.py -q`.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import math
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import (
    AircraftRepository, EventRepository, InventoryRepository, PredictionHistoryRepository, TransferRepository,
    WorkOrderRepository, reset,
)
from app.repositories.store import store
from app.services import maintenance_service, recommendation_service, transfer_service
from app.services.impact_service import preview
from app.services.resource_service import urgency_weight
from app.services.ml import (
    PredictionValidationError, get_provider, predict_validated, risk_band,
    set_provider, validate_prediction,
)


def valid_prediction(**changes):
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "aircraft_id": "A17", "timestamp": now, "health_score": 85,
        "failure_probability": .1, "rul": 40, "rul_unit": "flight_hours",
        "confidence": .9, "prediction_horizon_hours": 72,
        "model_version": "test-v1", "risk_level": "CRITICAL",
    }
    result.update(changes)
    return result


@pytest.mark.parametrize(("score", "expected"), [
    (44.999, "CRITICAL"), (45, "HIGH"), (59.999, "HIGH"),
    (60, "MEDIUM"), (79.999, "MEDIUM"), (80, "LOW"), (100, "LOW"),
])
def test_health_risk_threshold_boundaries(score, expected):
    assert risk_band(score) == expected


@pytest.mark.parametrize(("probability", "expected"), [
    (0, "LOW"), (.249999, "LOW"), (.25, "MEDIUM"), (.449999, "MEDIUM"),
    (.45, "HIGH"), (.699999, "HIGH"), (.70, "CRITICAL"), (1, "CRITICAL"),
])
def test_probability_risk_threshold_boundaries(probability, expected):
    assert risk_band(100, probability) == expected


def test_risk_fuses_conflicts_and_prediction_provider_label_is_ignored():
    assert risk_band(20, .01) == "CRITICAL"
    assert risk_band(99, .9) == "CRITICAL"
    normalized = validate_prediction(valid_prediction(), "A17")
    assert normalized["risk_level"] == "LOW"


def test_prediction_validation_distinguishes_zero_from_unavailable_and_rejects_bad_ranges():
    assert validate_prediction(valid_prediction(health_score=0), "A17")["health_score"] == 0
    zero = validate_prediction(valid_prediction(failure_probability=0), "A17")
    unavailable = validate_prediction(valid_prediction(failure_probability=None), "A17")
    omitted = validate_prediction({k: v for k, v in valid_prediction().items()
                                   if k != "failure_probability"}, "A17")
    assert zero["failure_probability"] == 0 and zero["probability_status"] == "available"
    assert unavailable["failure_probability"] is None and unavailable["probability_status"] == "unavailable"
    assert omitted["failure_probability"] is None and omitted["probability_status"] == "unavailable"
    for bad in ({"health_score": None},
                {"health_score": -1}, {"health_score": 101},
                {"failure_probability": -0.1}, {"failure_probability": 1.1},
                {"health_score": math.nan}, {"failure_probability": math.inf}):
        with pytest.raises(PredictionValidationError):
            validate_prediction(valid_prediction(**bad), "A17")


def test_cycle_rul_has_no_fabricated_hour_horizon_or_deadline():
    cycle_pred = valid_prediction(
        failure_probability=None, rul=12, rul_unit="cycles",
        prediction_horizon_hours=None, health_score=10,
        predicted_maintenance=True, subsystem=None,
        predicted_issue="FD001 RUL indicator is 12.0 cycles; human subsystem diagnosis required",
    )
    normalized = validate_prediction(cycle_pred, "A17")
    assert normalized["rul"] == 12 and normalized["rul_unit"] == "cycles"
    assert normalized["prediction_horizon_hours"] is None
    assert normalized["probability_status"] == "unavailable"
    assert maintenance_service.iso_in_rul(12, rul_unit="cycles") is None
    assert urgency_weight({"priority": "MEDIUM", "rul_unit": "cycles"}, rul=10) == 2.0
    assert urgency_weight({"priority": "MEDIUM", "rul_unit": "flight_hours"}, rul=10) == 4.0

    class CycleProvider:
        name = "test-cycle-provider"
        def predict(self, aircraft_id):
            return valid_prediction(
                aircraft_id=aircraft_id, failure_probability=None, rul=12,
                rul_unit="cycles", prediction_horizon_hours=None,
                health_score=10, predicted_maintenance=(aircraft_id == "A19"),
                subsystem=None,
                predicted_issue=("FD001 RUL indicator is 12.0 cycles; human subsystem diagnosis required"
                                 if aircraft_id == "A19" else None),
            )

    previous = get_provider()
    try:
        reset()
        set_provider(CycleProvider())
        event = maintenance_service.ingest_prediction("A19")
        assert event and event["rul_unit"] == "cycles" and event["predicted_time"] is None
        assert event["subsystem"] is None
        assert maintenance_service.create_work_order_from_event(event["id"]) is None
        response = TestClient(app).post(
            f"/api/maintenance/events/{event['id']}/work-order",
            json={"required_component": "HP-204", "actor": "base"},
            headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
        )
        assert response.status_code == 200
        work_order = response.json()
        assert work_order and work_order["rul_unit"] == "cycles"
        assert work_order["required_by_rul"] == 12
        assert work_order["required_by_flight_hours"] is None
    finally:
        set_provider(previous)
        reset()


def test_event_triage_requires_catalog_part_and_respects_matched_rule_candidates():
    reset()
    event = EventRepository.create(
        aircraft_id="A17", prediction_id="triage-validation",
        predicted_issue="High-pressure subsystem degradation", subsystem="HIGH_PRESSURE",
        risk_level="CRITICAL", rul=12, rul_unit="flight_hours", confidence=.9,
        health_score=41, predicted_time=None, required_resource_type="COMPONENT",
        status="OPEN", work_order_id=None, created_at="2026-10-17T00:00:00+00:00",
        updated_at="2026-10-17T00:00:00+00:00",
    )
    client = TestClient(app)
    headers = {"X-Demo-Role": "base", "X-Demo-Base": "alpha"}
    initial_count = len(WorkOrderRepository.list_all())

    unknown = client.post(
        f"/api/maintenance/events/{event['id']}/work-order",
        json={"required_component": "NOT-A-PART", "actor": "base"}, headers=headers,
    )
    unrelated = client.post(
        f"/api/maintenance/events/{event['id']}/work-order",
        json={"required_component": "FP-102", "actor": "base"}, headers=headers,
    )
    assert unknown.status_code == 409 and "catalogued part" in unknown.json()["detail"]
    assert unrelated.status_code == 409 and "not a candidate" in unrelated.json()["detail"]
    assert event["status"] == "OPEN" and len(WorkOrderRepository.list_all()) == initial_count

    compatible = client.post(
        f"/api/maintenance/events/{event['id']}/work-order",
        json={"required_component": "hp-204", "actor": "base"}, headers=headers,
    )
    assert compatible.status_code == 200
    assert compatible.json()["required_component"] == "HP-204"


def test_prediction_validation_checks_identity_time_horizon_and_rul():
    with pytest.raises(PredictionValidationError, match="does not match"):
        validate_prediction(valid_prediction(aircraft_id="A19"), "A17")
    with pytest.raises(PredictionValidationError, match="timezone"):
        validate_prediction(valid_prediction(timestamp="2026-10-17T10:00:00"), "A17")
    stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with pytest.raises(PredictionValidationError, match="stale"):
        validate_prediction(valid_prediction(timestamp=stale), "A17")
    with pytest.raises(PredictionValidationError, match="horizon"):
        validate_prediction(valid_prediction(prediction_horizon_hours=0), "A17")
    with pytest.raises(PredictionValidationError, match="rul_unit"):
        validate_prediction(valid_prediction(rul_unit=None), "A17")


def test_provider_success_malformed_and_timeout_are_explicit():
    class Provider:
        def __init__(self, prediction):
            self.prediction = prediction
        def predict(self, _aircraft_id):
            return self.prediction

    assert predict_validated(Provider(valid_prediction()), "A17")["model_version"] == "test-v1"
    with pytest.raises(PredictionValidationError, match="prediction must be an object"):
        predict_validated(Provider(None), "A17")

    class SlowProvider:
        def predict(self, _aircraft_id):
            time.sleep(.1)
            return valid_prediction()

    with pytest.raises(PredictionValidationError, match="timed out"):
        predict_validated(SlowProvider(), "A17", timeout_seconds=.005)


def test_ranking_uses_expected_downtime_and_is_order_independent():
    a = {"base_id": "bravo", "score": 20, "expected_downtime_hours": 4,
         "eta_hours": 2, "distance_km": 100, "donor_impact": "LOW"}
    b = {"base_id": "charlie", "score": 99, "expected_downtime_hours": 8,
         "eta_hours": 1, "distance_km": 10, "donor_impact": "LOW"}
    rejected = {"base_id": "alpha", "score": 100, "expected_downtime_hours": 0,
                "eta_hours": 0, "distance_km": 0, "donor_impact": "LOW", "feasible": False}
    first = recommendation_service.rank_candidates([a.copy(), b.copy(), rejected.copy()], {}, 1)
    second = recommendation_service.rank_candidates([rejected.copy(), b.copy(), a.copy()], {}, 1)
    assert [row["base_id"] for row in first] == ["bravo", "charlie"]
    assert [row["base_id"] for row in first] == [row["base_id"] for row in second]
    assert first[0]["ranking_explanation"]


def test_impact_is_time_aware_and_labels_projection_as_estimate():
    reset()
    result = preview("WO-1042")
    assert result["projection_type"] == "estimate"
    assert len(result["options"]) == 2
    assert len({row["projected_at_hours"] for row in result["options"]}) > 1
    assert all(row["donor_base_projection"]["base_id"] == row["source_base"]
               for row in result["options"])
    assert all(row["assumptions"] for row in result["options"])
    aircraft = AircraftRepository.get("A17")
    AircraftRepository.update(aircraft["id"], status="AVAILABLE")
    already_available = preview("WO-1042")
    assert all(row["target_aircraft_returns_to_service"] is False
               and row["delta_pct"] == 0 for row in already_available["options"])


def test_prediction_history_deduplicates_same_model_observation():
    reset()
    record = {"id": "same", "aircraft_id": "A17", "timestamp": "2026-10-17T10:00:00+00:00",
              "model_version": "demo-v1", "health_score": 41, "is_synthetic": True}
    first = PredictionHistoryRepository.append(**record)
    second = PredictionHistoryRepository.append(**record)
    assert first is second
    assert sum(1 for row in PredictionHistoryRepository.for_aircraft("A17")
               if row["timestamp"] == record["timestamp"] and row.get("model_version") == "demo-v1") == 1


def test_transfer_duplicate_approval_receipt_and_cancellation_do_not_move_stock_twice():
    reset()
    pending = transfer_service.create_transfer("HP-204", "bravo", "alpha", work_order_id="WO-1042")
    with pytest.raises(transfer_service.TransferError, match="active transfer"):
        transfer_service.create_transfer("HP-204", "charlie", "alpha", work_order_id="WO-1042")
    before = InventoryRepository.find("bravo", "HP-204")["quantity"]
    dispatched = transfer_service.approve_transfer(pending["id"])
    assert dispatched["status"] == "IN_TRANSIT"
    assert InventoryRepository.find("bravo", "HP-204")["quantity"] == before - 1
    with pytest.raises(transfer_service.TransferError):
        transfer_service.cancel_transfer(pending["id"])
    transfer_service.receive_transfer(pending["id"])
    destination = InventoryRepository.find("alpha", "HP-204")["quantity"]
    with pytest.raises(transfer_service.TransferError):
        transfer_service.receive_transfer(pending["id"])
    assert InventoryRepository.find("alpha", "HP-204")["quantity"] == destination

    cancelled = transfer_service.create_transfer("FP-102", "alpha", "bravo")
    source_before = InventoryRepository.find("alpha", "FP-102")["quantity"]
    transfer_service.cancel_transfer(cancelled["id"])
    transfer_service.cancel_transfer(cancelled["id"])
    assert InventoryRepository.find("alpha", "FP-102")["quantity"] == source_before


@pytest.mark.parametrize("stage", ["IN_TRANSIT", "RESOURCE_AVAILABLE", "IN_PROGRESS", "COMPLETED", "SCHEDULED"])
def test_recommendation_approval_retry_respects_work_order_lifecycle(stage):
    reset()
    work_order = WorkOrderRepository.get("WO-1042")
    if stage == "SCHEDULED":
        WorkOrderRepository.update(work_order["id"], status="SCHEDULED")
        transfers_before = TransferRepository.list_all()
        stock_before = [dict(row) for row in InventoryRepository.list_all()]
        with pytest.raises(transfer_service.TransferError, match="no longer eligible"):
            transfer_service.approve_recommendation(work_order["id"])
        assert TransferRepository.list_all() == transfers_before
        assert InventoryRepository.list_all() == stock_before
        return

    transfer = transfer_service.approve_recommendation(work_order["id"])["transfer"]
    if stage == "IN_TRANSIT":
        transfers_before = TransferRepository.list_all()
        stock_before = [dict(row) for row in InventoryRepository.list_all()]
        retry = transfer_service.approve_recommendation(work_order["id"])
        assert retry["transfer"]["id"] == transfer["id"]
        assert TransferRepository.list_all() == transfers_before
        assert InventoryRepository.list_all() == stock_before
        return

    transfer_service.receive_transfer(transfer["id"])
    assert WorkOrderRepository.get(work_order["id"])["status"] == "RESOURCE_AVAILABLE"
    if stage in {"IN_PROGRESS", "COMPLETED"}:
        maintenance_service.start_maintenance(work_order["id"])
    if stage == "COMPLETED":
        maintenance_service.complete_maintenance(work_order["id"])
    assert WorkOrderRepository.get(work_order["id"])["status"] == stage

    count_before_retry = len(TransferRepository.list_all())
    stock_before_retry = [dict(row) for row in InventoryRepository.list_all()]
    with pytest.raises(transfer_service.TransferError, match="already arrived"):
        transfer_service.approve_recommendation(work_order["id"])

    assert len(TransferRepository.list_all()) == count_before_retry
    assert InventoryRepository.list_all() == stock_before_retry


def test_recommendation_rejection_is_audit_only_and_moves_no_stock():
    reset()
    client = TestClient(app)
    transfers_before = TransferRepository.list_all()
    inventory_before = [dict(row) for row in InventoryRepository.list_all()]
    rejected = client.post(
        "/api/recommendations/A17/reject",
        json={"actor": "commander", "reason": "readiness audit"},
        headers={"X-Demo-Role": "commander"},
    )
    assert rejected.status_code == 200 and rejected.json()["rejected"] is True
    assert TransferRepository.list_all() == transfers_before
    assert InventoryRepository.list_all() == inventory_before

    # Rejection is currently logged rather than a terminal work-order state;
    # a later, explicit Commander approval remains possible.
    approved = client.post(
        "/api/work-orders/WO-1042/recommendation/approve",
        json={"actor": "commander"},
        headers={"X-Demo-Role": "commander"},
    )
    assert approved.status_code == 200
    assert approved.json()["transfer"]["status"] == "IN_TRANSIT"


def test_concurrent_transfer_approvals_cannot_oversell_stock():
    reset()
    a = transfer_service.create_transfer("HP-204", "charlie", "alpha", quantity=2)
    b = transfer_service.create_transfer("HP-204", "charlie", "bravo", quantity=2)
    def attempt(transfer_id):
        try:
            transfer_service.approve_transfer(transfer_id)
            return True
        except transfer_service.TransferError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (a["id"], b["id"])))
    assert sum(results) == 1
    assert InventoryRepository.find("charlie", "HP-204")["quantity"] == 0


def test_maintenance_reserves_one_unit_and_duplicate_completion_is_idempotent():
    reset()
    inv = InventoryRepository.find("alpha", "AV-077")
    InventoryRepository.update(inv["id"], quantity=1, reserved=0, minimum_reserve=0)
    a = maintenance_service.create_manual_work_order("A19", "AV-077")
    b = maintenance_service.create_manual_work_order("A19", "AV-077")
    def start(work_order_id):
        try:
            maintenance_service.start_maintenance(work_order_id)
            return True
        except maintenance_service.MaintenanceTransitionError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        started = list(pool.map(start, (a["id"], b["id"])))
    assert sum(started) == 1
    started_id = a["id"] if started[0] else b["id"]
    finished = maintenance_service.complete_maintenance(started_id)
    assert finished["status"] == "COMPLETED"
    quantity = InventoryRepository.find("alpha", "AV-077")["quantity"]
    maintenance_service.complete_maintenance(started_id)
    assert InventoryRepository.find("alpha", "AV-077")["quantity"] == quantity == 0
    assert InventoryRepository.find("alpha", "AV-077")["reserved"] == 0


def test_demo_role_and_base_scope_are_enforced_by_api_headers():
    reset()
    client = TestClient(app)
    denied = client.patch("/api/inventory/inv-04", json={"quantity": 5},
                          headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"})
    assert denied.status_code == 403
    allowed = client.patch("/api/inventory/inv-04", json={"quantity": 5},
                           headers={"X-Demo-Role": "logistics"})
    assert allowed.status_code == 200
    wrong_base = client.post("/api/maintenance/work-orders?aircraft_id=A17",
                             json={"component": "HP-204"},
                             headers={"X-Demo-Role": "base", "X-Demo-Base": "bravo"})
    assert wrong_base.status_code == 403
    # Header-selected role takes precedence over a stale actor query value.
    same_base = client.post("/api/maintenance/work-orders/WO-1042/start?actor=commander",
                            headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"})
    assert same_base.status_code == 400  # authorized; rejected only by lifecycle state


def test_malformed_provider_is_a_clear_unavailable_api_response(caplog):
    reset()
    previous = get_provider()
    class BrokenProvider:
        name = "broken-test-provider"
        def predict(self, _aircraft_id):
            return {"health_score": 0}
    try:
        set_provider(BrokenProvider())
        response = TestClient(app).get("/api/health/A17")
        assert response.status_code == 503
        assert response.json()["prediction_status"] == "unavailable"
        assert response.json()["detail"] == "prediction provider unavailable"
        assert "aircraft_id does not match request" in caplog.text
    finally:
        set_provider(previous)


def test_failed_recommendation_approval_does_not_leave_pending_transfer_or_approval_audit():
    reset()
    # Preserve nominal stock but make every donor unit mandatory reserve.
    for base in ("bravo", "charlie"):
        inv = InventoryRepository.find(base, "HP-204")
        InventoryRepository.update(inv["id"], minimum_reserve=inv["quantity"])
    before = len(TransferRepository.list_all())
    with pytest.raises(transfer_service.TransferError, match="no feasible source"):
        transfer_service.approve_recommendation("WO-1042")
    assert len(TransferRepository.list_all()) == before
    assert not any(row["event_type"] == "RECOMMENDATION_APPROVED"
                   and row.get("entity_id") == "WO-1042" for row in store()["audit"])
