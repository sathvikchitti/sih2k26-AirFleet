"""Indicative cycle-based spares forecast contracts and snapshot purity."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app import data
from app.domain import knowledge
from app.repositories.store import snapshot as live_snapshot, store as live_store
from app.services import demand_forecast_service as forecast


def _prediction(aircraft_id: str, engine_id: int, rul: float, std: float,
                low: float | None = None, high: float | None = None) -> dict:
    return {
        "aircraft_id": aircraft_id,
        "rul": rul,
        "rul_unit": "cycles",
        "rul_std": std,
        "rul_low": low if low is not None else max(0, rul - 2 * std),
        "rul_high": high if high is not None else rul + 2 * std,
        "source": "cmapss-fd001-demo-history",
        "model_version": "rf-test-v1",
        "metadata": {"engine_id": engine_id},
    }


def _setup(monkeypatch, aircraft=None, predictions=None):
    state = data.build_seed()
    state["aircraft"] = aircraft or [
        {"id": "A17", "base_id": "alpha"},
        {"id": "A19", "base_id": "alpha"},
        {"id": "A21", "base_id": "bravo"},
    ]
    state["work_orders"] = []
    state["transfers"] = []
    state["inventory"] = [
        {**row, "quantity": 0, "reserved": 0, "minimum_reserve": 0,
         "condition_pct": 0, "status": "STOCKOUT"}
        for row in state["inventory"]
    ]
    monkeypatch.setenv("FD001_ENGINE_PART_MAPPING", '{"1":"HP-204","2":"HP-204","3":"HP-204"}')
    monkeypatch.setattr(forecast, "snapshot", lambda: deepcopy(state))
    monkeypatch.setattr(forecast, "get_provider", lambda: type("Provider", (), {"name": "fd001-test"})())
    monkeypatch.setattr(forecast, "predict_validated", lambda _provider, aircraft_id: predictions[aircraft_id])
    return state


def _line(state, base, component="HP-204", *, quantity=0, reserved=0, minimum=0,
          condition=90):
    row = next(row for row in state["inventory"]
               if row["base_id"] == base and row["part_number"] == component)
    row.update(quantity=quantity, reserved=reserved, minimum_reserve=minimum,
               condition_pct=condition)
    return row


def _component(result, base, component="HP-204"):
    return next(row for row in next(row for row in result["bases"]
                                    if row["base_id"] == base)["components"]
                if row["component"] == component)


def test_fractional_demand_and_feasible_whole_unit_move_are_pure(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 30, 10),
        "A19": _prediction("A19", 2, 100, 1),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=preds)
    _line(state, "bravo", quantity=3, reserved=1, minimum=0, condition=42)
    before = deepcopy(state)
    live_store()
    live_before = live_snapshot()

    result = forecast.forecast_resources(30)
    alpha = _component(result, "alpha")

    assert alpha["expected_demand"] == pytest.approx(0.5)
    assert alpha["eligible_aircraft"][0]["provider_failure_probability"] is None
    assert alpha["projected_shortfall"] == 1
    assert alpha["suggested_moves"] == [{
        "part_number": "HP-204", "source_base": "bravo", "destination_base": "alpha",
        "quantity": 1, "eta_hours": 2.0, "distance_km": 120,
        "condition_pct": 42, "min_condition_pct": 40, "feasible": True,
        "action": "create_transfer",
    }]
    assert result["mutated_state"] is False
    assert state == before
    assert live_snapshot() == live_before
    # Reporting uses the frozen post-WO ledger, not the mutable suggestion
    # ledger debited to construct Alpha's move.
    assert _component(result, "bravo")["committed_available_for_transfer"] == 2


@pytest.mark.parametrize(("charlie_stock", "expected_move"), [(1, 0), (3, 1)])
def test_future_local_demand_is_held_before_a_base_can_donate(monkeypatch, charlie_stock, expected_move):
    aircraft = [
        {"id": "A17", "base_id": "alpha"},
        {"id": "A19", "base_id": "alpha"},
        {"id": "A21", "base_id": "charlie"},
        {"id": "A23", "base_id": "charlie"},
    ]
    charlie_probability = 0.72
    z_for_probability = 0.5828415072712162
    predictions = {
        "A17": _prediction("A17", 1, 100, 1),
        "A19": _prediction("A19", 2, 100, 1),
        "A21": _prediction("A21", 3, 100 - z_for_probability, 1),
        "A23": _prediction("A23", 4, 100 - z_for_probability, 1),
    }
    state = _setup(monkeypatch, aircraft=aircraft, predictions=predictions)
    monkeypatch.setenv(
        "FD001_ENGINE_PART_MAPPING",
        '{"1":"HP-204","2":"HP-204","3":"HP-204","4":"HP-204"}',
    )
    _line(state, "charlie", quantity=charlie_stock, condition=90)
    before = deepcopy(state)

    first = forecast.forecast_resources(100, _state=state, _predictions=predictions)
    second = forecast.forecast_resources(100, _state=state, _predictions=predictions)
    alpha = _component(first, "alpha")
    charlie = _component(first, "charlie")

    assert alpha["expected_demand"] == pytest.approx(1.0)
    assert charlie["expected_demand"] == pytest.approx(1.44, abs=1e-6)
    assert charlie["forecast_protected_units"] == min(charlie_stock, 2)
    assert len(alpha["suggested_moves"]) == expected_move
    if expected_move:
        assert alpha["suggested_moves"][0]["source_base"] == "charlie"
        assert alpha["suggested_moves"][0]["quantity"] == 1
    else:
        assert alpha["suggested_moves"] == []
    assert first == second
    assert state == before


def test_open_work_order_excludes_duplicate_predictive_demand_and_ledger_claim(monkeypatch):
    preds = {key: _prediction(key, engine, 20, 5)
             for key, engine in (("A17", 1), ("A19", 2), ("A21", 3))}
    state = _setup(monkeypatch, predictions=preds)
    state["work_orders"] = [{
        "id": "WO-OPEN", "aircraft_id": "A17", "base_id": "alpha",
        "required_component": "HP-204", "status": "WAITING_FOR_RESOURCE",
    }]
    _line(state, "alpha", quantity=2, reserved=0, minimum=0, condition=90)
    result = forecast.forecast_resources(30)
    alpha = _component(result, "alpha")

    assert alpha["eligible_aircraft_count"] == 1
    assert result["excluded_open_work_order_count"] == 1
    assert alpha["on_hand"] == 2
    assert alpha["committed_available_for_transfer"] == 1
    assert alpha["expected_demand"] == pytest.approx(0.9772498680518208)
    assert alpha["projected_shortfall"] == 0


def test_pending_claims_reserves_and_condition_are_hard_donor_constraints(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 20, 2),
        "A19": _prediction("A19", 2, 100, 1),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=preds)
    _line(state, "alpha", quantity=0)
    _line(state, "bravo", quantity=2, reserved=0, minimum=1, condition=90)
    _line(state, "charlie", quantity=2, reserved=1, minimum=0, condition=39)
    state["transfers"] = [{
        "id": "T-PENDING", "part_number": "HP-204", "source_base": "bravo",
        "dest_base": "charlie", "quantity": 1, "status": "PENDING_APPROVAL",
        "condition_pct": 90,
    }]

    result = forecast.forecast_resources(30)
    alpha = _component(result, "alpha")
    bravo = _component(result, "bravo")

    # Bravo's only transferable unit is already provisionally claimed. Charlie
    # fails its catalog condition floor; neither may be proposed to Alpha.
    assert alpha["projected_shortfall"] == 1
    assert alpha["suggested_moves"] == []
    assert bravo["committed_available_for_transfer"] == 0
    assert _component(result, "charlie")["available_for_transfer"] == 0


def test_zero_standard_deviation_is_deterministic_and_zero_demand_is_not_missing(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 30, 0, low=20, high=40),
        "A19": _prediction("A19", 2, 40, 0, low=20, high=50),
        "A21": _prediction("A21", 3, 100, 1, low=80, high=110),
    }
    state = _setup(monkeypatch, predictions=preds)
    result = forecast.forecast_resources(30)
    alpha = _component(result, "alpha")
    bravo = _component(result, "bravo")

    assert alpha["expected_demand"] == 1.0
    assert alpha["eligible_aircraft_count"] == 2
    assert next(row for row in alpha["eligible_aircraft"]
                if row["aircraft_id"] == "A19")["probability_within_horizon"] == 0.0
    assert bravo["expected_demand"] is None
    assert bravo["demand_status"] == "no_eligible_predictions"
    assert result["forecast_status"] == "available"
    assert result["outside_horizon_prediction_count"] == 1
    assert result["unavailable_prediction_count"] == 0


def test_mock_hour_rul_is_unavailable_not_zero_demand(monkeypatch):
    state = _setup(monkeypatch, predictions={})
    monkeypatch.setattr(forecast, "get_provider", lambda: type("Provider", (), {"name": "mock"})())
    monkeypatch.setattr(forecast, "predict_validated", lambda _provider, aircraft_id: {
        "aircraft_id": aircraft_id, "rul": 12, "rul_unit": "flight_hours",
        "model_version": "mock-v1",
    })
    result = forecast.forecast_resources(30)

    assert result["forecast_status"] == "no_eligible_predictions"
    assert result["eligible_prediction_count"] == 0
    assert result["unavailable_prediction_count"] == 3
    assert result["suggested_horizon_cycles"] is None
    assert _component(result, "alpha")["expected_demand"] is None


@pytest.mark.parametrize(
    ("current_horizon", "rul", "std", "expected_horizon"),
    [(30, 90, 10, 100), (100, 140, 10, 125)],
)
def test_no_eligible_forecast_suggests_smallest_larger_tested_horizon(
        monkeypatch, current_horizon, rul, std, expected_horizon):
    predictions = {
        "A17": _prediction("A17", 1, rul, std),
        "A19": _prediction("A19", 2, 200, 1),
        "A21": _prediction("A21", 3, 200, 1),
    }
    state = _setup(monkeypatch, predictions=predictions)

    first = forecast.forecast_resources(
        current_horizon, _state=state, _predictions=predictions,
    )
    repeated = forecast.forecast_resources(
        current_horizon, _state=state, _predictions=predictions,
    )

    assert first["forecast_status"] == "no_eligible_predictions"
    assert first["eligible_prediction_count"] == 0
    assert first["suggested_horizon_cycles"] == expected_horizon
    assert repeated["suggested_horizon_cycles"] == expected_horizon


def test_horizon_suggestion_excludes_open_work_orders_and_has_no_guess_when_none_qualify(monkeypatch):
    predictions = {
        "A17": _prediction("A17", 1, 90, 10),
        "A19": _prediction("A19", 2, 200, 1),
        "A21": _prediction("A21", 3, 200, 1),
    }
    state = _setup(monkeypatch, predictions=predictions)
    state["work_orders"] = [{
        "id": "WO-OPEN", "aircraft_id": "A17", "base_id": "alpha",
        "required_component": "HP-204", "status": "WAITING_FOR_RESOURCE",
    }]

    result = forecast.forecast_resources(30, _state=state, _predictions=predictions)

    assert result["forecast_status"] == "no_eligible_predictions"
    assert result["excluded_open_work_order_count"] == 1
    assert result["suggested_horizon_cycles"] is None


def test_open_work_order_inbound_does_not_cover_another_aircraft_forecast(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 20, 2),
        "A19": _prediction("A19", 2, 20, 2),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=preds)
    state["work_orders"] = [{
        "id": "WO-OPEN", "aircraft_id": "A17", "base_id": "alpha",
        "required_component": "HP-204", "status": "WAITING_FOR_RESOURCE",
    }]
    _line(state, "bravo", quantity=2, condition=90)

    alpha = _component(forecast.forecast_resources(30), "alpha")

    assert alpha["eligible_aircraft_count"] == 1
    assert alpha["inbound_proposed_for_open_work_orders"] == 1
    assert alpha["projected_shortfall"] == 1
    # The first Bravo unit is assigned to WO-OPEN on the planner ledger; one
    # remaining unit may be proposed once for the separate A19 forecast.
    assert [(row["source_base"], row["quantity"]) for row in alpha["suggested_moves"]] == [("bravo", 1)]


def test_open_work_order_transfer_remains_earmarked_not_future_forecast_supply(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 20, 2),
        "A19": _prediction("A19", 2, 20, 2),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=preds)
    state["work_orders"] = [{
        "id": "WO-OPEN", "aircraft_id": "A17", "base_id": "alpha",
        "required_component": "HP-204", "status": "WAITING_FOR_RESOURCE",
    }]
    state["transfers"] = [{
        "id": "T-OPEN", "part_number": "HP-204", "source_base": "bravo",
        "dest_base": "alpha", "quantity": 1, "status": "IN_TRANSIT",
        "condition_pct": 90, "for_aircraft": "A17", "work_order_id": "WO-OPEN",
    }]

    alpha = _component(forecast.forecast_resources(30), "alpha")

    assert alpha["eligible_aircraft_count"] == 1
    assert alpha["inbound_pending_or_in_transit"] == 0
    assert alpha["inbound_work_order_committed"] == 1
    assert alpha["projected_shortfall"] == 1


def test_unbound_inbound_counts_only_serviceable_units_above_reserve(monkeypatch):
    preds = {
        "A17": _prediction("A17", 1, 20, 2),
        "A19": _prediction("A19", 2, 100, 1),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=preds)
    _line(state, "alpha", quantity=0, minimum=1)
    _line(state, "bravo", quantity=3, condition=90)
    state["transfers"] = [{
        "id": "T-UNBOUND", "part_number": "HP-204", "source_base": "bravo",
        "dest_base": "alpha", "quantity": 2, "status": "PENDING_APPROVAL",
        "condition_pct": 90, "for_aircraft": None, "work_order_id": None,
    }]

    alpha = _component(forecast.forecast_resources(30), "alpha")

    assert alpha["inbound_pending_or_in_transit"] == 1
    assert alpha["committed_available_for_transfer"] == 0
    assert alpha["projected_shortfall"] == 0


def test_mapping_rejects_non_engine_or_unknown_catalog_components(monkeypatch):
    monkeypatch.setenv("FD001_ENGINE_PART_MAPPING", '{"1":"FP-102"}')
    with pytest.raises(ValueError, match="engine-category"):
        knowledge.fd001_engine_part_mapping()
    monkeypatch.setenv("FD001_ENGINE_PART_MAPPING", '{"1":"NO-SUCH-PART"}')
    with pytest.raises(ValueError, match="engine-category"):
        knowledge.fd001_engine_part_mapping()


def test_mapping_allows_only_explicit_engine_category_override(monkeypatch):
    monkeypatch.setenv("FD001_ENGINE_PART_MAPPING", '{"1":"OE-310"}')
    mapping, source = knowledge.fd001_engine_part_mapping()
    assert mapping == {1: "OE-310"}
    assert source == "environment_configured_demo_assumption"


@pytest.mark.parametrize("horizon", [-1, float("nan"), float("inf"), 10001, True])
def test_invalid_forecast_horizon_is_rejected(horizon):
    with pytest.raises(ValueError, match="horizon_cycles"):
        forecast.forecast_resources(horizon, _state=data.build_seed(), _predictions={})


def test_readonly_forecast_route_is_registered_with_cycle_horizon_query():
    from app.routers.inventory import router

    route = next(route for route in router.routes
                 if getattr(route, "path", None) == "/api/resources/forecast")
    assert "GET" in route.methods
    assert route.endpoint.__name__ == "resources_forecast"


def test_forecast_api_returns_cycle_contract_and_leaves_live_state_unchanged(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    predictions = {
        "A17": _prediction("A17", 1, 30, 10),
        "A19": _prediction("A19", 2, 100, 1),
        "A21": _prediction("A21", 3, 100, 1),
    }
    state = _setup(monkeypatch, predictions=predictions)
    _line(state, "bravo", quantity=2, condition=90)
    live_store()
    before = live_snapshot()

    with TestClient(app) as client:
        response = client.get("/api/resources/forecast?horizon_cycles=30")
        invalid = client.get("/api/resources/forecast?horizon_cycles=10001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["forecast_status"] == "available"
    assert payload["mapping"]["label"] == "assumed mapping for demo"
    assert payload["eligible_prediction_count"] == 1
    assert payload["suggested_horizon_cycles"] is None
    assert payload["mutated_state"] is False
    assert _component(payload, "alpha")["expected_demand"] == pytest.approx(0.5)
    assert invalid.status_code == 422
    assert live_snapshot() == before
