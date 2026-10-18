"""Pure, hand-calculated tests for fleet readiness what-if curves."""

from __future__ import annotations

from copy import deepcopy

from app import data
from app.domain.enums import TransferStatus, WorkOrderStatus
from app.services import impact_service
from app.services import planning_service, resource_service
from app.services import readiness_service
from app.services.readiness_service import simulate_readiness_from_snapshot


def _wo(work_order_id, aircraft_id, component, status, repair_hours):
    return {
        "id": work_order_id,
        "aircraft_id": aircraft_id,
        "base_id": "alpha",
        "required_component": component,
        "status": status,
        "estimated_repair_hours": repair_hours,
    }


def _remote(work_order_id, eta):
    return {
        "work_order_id": work_order_id,
        "allocation_status": "PROPOSED_REMOTE_TRANSFER",
        "recommended": {"eta_hours": eta},
    }


def _readiness_fixture():
    state = {
        "aircraft": [
            {"id": "A1", "base_id": "alpha", "status": "WAITING_FOR_PART"},
            {"id": "A2", "base_id": "bravo", "status": "AVAILABLE"},
            {"id": "A3", "base_id": "alpha", "status": "MAINTENANCE"},
            {"id": "A4", "base_id": "bravo", "status": "WAITING_FOR_PART"},
            {"id": "A5", "base_id": "charlie", "status": "WAITING_FOR_PART"},
        ],
        "work_orders": [
            # Both WOs block A1; finishing only one cannot create availability.
            _wo("WO-A1", "A1", "HP-204", WorkOrderStatus.WAITING_FOR_RESOURCE.value, 2),
            _wo("WO-A2", "A1", "HP-204", WorkOrderStatus.WAITING_FOR_RESOURCE.value, 4),
            # Existing in-progress work is common to every policy.
            _wo("WO-MAINT", "A3", "FP-102", WorkOrderStatus.IN_PROGRESS.value, 2),
            # A pending transfer is not dispatched by any hypothetical policy.
            _wo("WO-PENDING", "A4", "OE-310", WorkOrderStatus.WAITING_FOR_RESOURCE.value, 3),
            # An approved transit transfer is common and arrives at hour 5.
            _wo("WO-TRANSIT", "A5", "AV-077", WorkOrderStatus.WAITING_FOR_RESOURCE.value, 1),
        ],
        "transfers": [
            {"id": "T-PENDING", "work_order_id": "WO-PENDING", "part_number": "OE-310",
             "status": TransferStatus.PENDING_APPROVAL.value, "eta_hours": 1},
            {"id": "T-TRANSIT", "work_order_id": "WO-TRANSIT", "part_number": "AV-077",
             "status": TransferStatus.IN_TRANSIT.value, "eta_hours": 5},
        ],
        "inventory": [],
    }
    predictions = {
        "A1": {"risk_level": "HIGH", "rul": 1, "rul_unit": "cycles",
               "subsystem": "HIGH_PRESSURE", "predicted_issue": "High-pressure subsystem degradation"},
        "A2": {"risk_level": "LOW", "rul": 90, "rul_unit": "cycles"},
        "A3": {"risk_level": "LOW", "rul": 90, "rul_unit": "cycles"},
        "A4": {"risk_level": "HIGH", "rul": 1, "rul_unit": "cycles",
               "subsystem": None, "predicted_issue": None},
        "A5": {"risk_level": "LOW", "rul": 90, "rul_unit": "cycles"},
    }
    common = [
        {"work_order_id": "WO-MAINT", "allocation_status": "IN_PROGRESS_RESOURCE_RESERVED"},
        {"work_order_id": "WO-PENDING", "allocation_status": "EXISTING_PENDING_APPROVAL",
         "transfer_id": "T-PENDING"},
        {"work_order_id": "WO-TRANSIT", "allocation_status": "EXISTING_IN_TRANSIT",
         "transfer_id": "T-TRANSIT"},
    ]
    no_action = {"allocations": deepcopy(common), "inventory_effects": [], "conflicts": []}
    nearest = {"allocations": deepcopy(common) + [_remote("WO-A1", 2), _remote("WO-A2", 3)],
               "inventory_effects": [], "conflicts": []}
    proposed = {"allocations": deepcopy(common) + [_remote("WO-A1", 1), _remote("WO-A2", 2)],
                "inventory_effects": [], "conflicts": []}
    return state, predictions, {
        "no_action": no_action,
        "nearest_feasible": nearest,
        "proposed": proposed,
    }


def _available_aircraft_hours(curve):
    return sum(
        point["available_aircraft"] * (next_point["hours"] - point["hours"])
        for point, next_point in zip(curve, curve[1:])
    )


def test_three_policies_share_one_frozen_snapshot_and_match_hand_calculated_hours():
    state, predictions, plans = _readiness_fixture()
    state_before = deepcopy(state)
    predictions_before = deepcopy(predictions)
    plans_before = deepcopy(plans)

    result = simulate_readiness_from_snapshot(state, predictions, plans, 48)

    assert state == state_before
    assert predictions == predictions_before
    assert plans == plans_before
    assert result["mutated_state"] is False
    assert result["snapshot_type"] == "frozen_read_only_fleet_snapshot"
    assert result["horizon_hours"] == 48
    assert result["horizon_unit"] == "hours"
    policies = result["policies"]
    assert all(policy["curve"][0]["hours"] == 0 for policy in policies.values())
    assert all(policy["curve"][-1]["hours"] == 48 for policy in policies.values())

    no_action = policies["no_action"]["curve"]
    nearest = policies["nearest_feasible"]["curve"]
    proposed = policies["proposed"]["curve"]
    assert [point["hours"] for point in proposed] == [0, 1, 2, 3, 5, 6, 48]
    assert [point["hours"] for point in nearest] == [0, 2, 3, 4, 5, 6, 7, 48]
    # At the first A1 completion only one of its two blocking WOs is done.
    assert next(point for point in proposed if point["hours"] == 3)["available_aircraft"] == 2
    # Shared in-progress and transit completions occur identically for all plans.
    assert next(point for point in no_action if point["hours"] == 2)["available_aircraft"] == 2
    assert next(point for point in no_action if point["hours"] == 6)["available_aircraft"] == 3
    assert next(point for point in proposed if point["hours"] == 6)["available_aircraft"] == 4
    assert next(point for point in nearest if point["hours"] == 6)["available_aircraft"] == 3
    assert next(point for point in nearest if point["hours"] == 7)["available_aircraft"] == 4

    # A2 contributes 48h, A3 contributes 46h, and A5 contributes 42h under all
    # plans. A1 contributes only after both repairs: 42h proposed or 41h nearest.
    assert _available_aircraft_hours(no_action) == 136
    assert _available_aircraft_hours(proposed) == 178
    assert _available_aircraft_hours(nearest) == 177
    assert policies["no_action"]["metrics"]["available_aircraft_hours"] == 136
    assert policies["proposed"]["metrics"]["available_aircraft_hours"] == 178
    assert policies["nearest_feasible"]["metrics"]["available_aircraft_hours"] == 177
    assert policies["proposed"]["metrics"]["time_weighted_average_availability_pct"] == 74.1667
    assert proposed[-1]["cumulative_available_aircraft_hours"] == 178
    assert proposed[-1]["aircraft_by_status"]["AVAILABLE"] == 4
    assert proposed[-1]["aircraft_by_status"]["WAITING_FOR_PART"] == 1
    # The pending request remains blocked in every policy.
    assert "WO-PENDING" not in proposed[-1]["completed_work_order_ids"]
    assert result["policies"]["no_action"]["new_allocations_enabled"] is False
    assert result["policies"]["nearest_feasible"]["new_allocations_enabled"] is True
    assert result["policies"]["proposed"]["new_allocations_enabled"] is True


def test_cycles_never_become_hours_and_fd001_completion_does_not_clear_model_risk():
    state, predictions, plans = _readiness_fixture()
    # The high-risk prediction is representative of fixed FD001 output: cycle
    # RUL is recorded, but it has no subsystem match that maintenance can clear.
    predictions["A1"].update(subsystem=None, predicted_issue=None, rul=0.25, rul_unit="cycles")

    result = simulate_readiness_from_snapshot(state, predictions, plans, 48)

    proposed = result["policies"]["proposed"]["curve"]
    assert [point["hours"] for point in proposed] == [0, 1, 2, 3, 5, 6, 48]
    assert proposed[-1]["completed_work_order_ids"] == ["WO-A1", "WO-A2", "WO-MAINT", "WO-TRANSIT"]
    assert proposed[-1]["aircraft_by_status"].get("AT_RISK") == 1
    assert proposed[-1]["available_aircraft"] == 3


def test_local_repair_start_grounds_initially_available_aircraft_for_repair_duration():
    state = {
        "aircraft": [{"id": "A1", "base_id": "alpha", "status": "AVAILABLE"}],
        "work_orders": [_wo("WO-LOCAL", "A1", "HP-204",
                             WorkOrderStatus.WAITING_FOR_RESOURCE.value, 2)],
        "transfers": [], "inventory": [],
    }
    predictions = {"A1": {"risk_level": "LOW", "rul": 100, "rul_unit": "cycles"}}
    plans = {
        "no_action": {"allocations": [], "inventory_effects": [], "conflicts": []},
        "nearest_feasible": {"allocations": [{
            "work_order_id": "WO-LOCAL", "allocation_status": "PROPOSED_LOCAL_ALLOCATION",
        }], "inventory_effects": [], "conflicts": []},
        "proposed": {"allocations": [{
            "work_order_id": "WO-LOCAL", "allocation_status": "PROPOSED_LOCAL_ALLOCATION",
        }], "inventory_effects": [], "conflicts": []},
    }

    result = simulate_readiness_from_snapshot(state, predictions, plans, 10)

    no_action = result["policies"]["no_action"]
    proposed = result["policies"]["proposed"]
    assert no_action["metrics"]["available_aircraft_hours"] == 10
    assert proposed["curve"][0]["aircraft_by_status"] == {"MAINTENANCE": 1}
    assert proposed["curve"][0]["started_work_order_ids"] == ["WO-LOCAL"]
    assert proposed["curve"][1]["hours"] == 2
    assert proposed["curve"][1]["aircraft_by_status"] == {"AVAILABLE": 1}
    assert proposed["metrics"]["available_aircraft_hours"] == 8
    assert proposed["metrics"]["time_weighted_average_availability_pct"] == 80.0


def test_fractional_completion_uses_full_precision_at_reported_event_time():
    state = {
        "aircraft": [{"id": "A1", "base_id": "alpha", "status": "AVAILABLE"}],
        "work_orders": [_wo("WO-FRACTIONAL", "A1", "HP-204",
                             WorkOrderStatus.WAITING_FOR_RESOURCE.value, 0.2)],
        "transfers": [], "inventory": [],
    }
    predictions = {"A1": {"risk_level": "LOW", "rul": 0.1, "rul_unit": "cycles"}}
    plans = {
        "no_action": {"allocations": [], "inventory_effects": [], "conflicts": []},
        "nearest_feasible": {"allocations": [{
            "work_order_id": "WO-FRACTIONAL", "allocation_status": "PROPOSED_REMOTE_TRANSFER",
            "recommended": {"eta_hours": 0.1},
        }], "inventory_effects": [], "conflicts": []},
        "proposed": {"allocations": [{
            "work_order_id": "WO-FRACTIONAL", "allocation_status": "PROPOSED_REMOTE_TRANSFER",
            "recommended": {"eta_hours": 0.1},
        }], "inventory_effects": [], "conflicts": []},
    }

    result = simulate_readiness_from_snapshot(state, predictions, plans, 1)

    curve = result["policies"]["proposed"]["curve"]
    completion = next(point for point in curve if point["hours"] == 0.3)
    assert completion["completed_work_order_ids"] == ["WO-FRACTIONAL"]
    assert completion["aircraft_by_status"] == {"AVAILABLE": 1}
    # The waiting work order grounds the aircraft until the 0.1 h arrival;
    # it returns at 0.1 + 0.2 h, leaving 0.7 available hours in this horizon.
    assert result["policies"]["proposed"]["metrics"]["available_aircraft_hours"] == 0.7


def test_nearest_policy_uses_actual_allocator_with_distance_first_feasible_candidates(monkeypatch):
    state = data.build_seed()
    state["work_orders"] = [_wo("WO-CHOICE", "A17", "FP-102",
                                 WorkOrderStatus.WAITING_FOR_RESOURCE.value, 2)]
    state["transfers"] = []
    for row in state["inventory"]:
        if row["part_number"] == "FP-102":
            row.update(quantity=0, reserved=0, minimum_reserve=0, condition_pct=0)
    state["inventory"].extend([
        {"id": "near-fp", "base_id": "bravo", "part_number": "FP-102",
         "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 90},
        {"id": "far-fp", "base_id": "charlie", "part_number": "FP-102",
         "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 90},
    ])
    predictions = {"A17": {"risk_level": "HIGH", "rul": 1, "rul_unit": "cycles"}}
    monkeypatch.setattr(planning_service, "snapshot", lambda: state)
    monkeypatch.setattr(resource_service, "distance_km", lambda _home, donor: {
        "bravo": 120, "charlie": 380,
    }[donor])
    monkeypatch.setattr(resource_service, "eta_hours", lambda _home, donor: {
        "bravo": 5.0, "charlie": 1.0,
    }[donor])

    nearest = planning_service.allocation_preview(
        ["WO-CHOICE"], source_policy="nearest_feasible", _state=state,
        _predictions=predictions,
    )
    proposed = planning_service.allocation_preview(
        ["WO-CHOICE"], source_policy="proposed", _state=state,
        _predictions=predictions,
    )

    nearest_row = nearest["allocations"][0]
    proposed_row = proposed["allocations"][0]
    assert nearest_row["allocation_status"] == proposed_row["allocation_status"] == "PROPOSED_REMOTE_TRANSFER"
    assert {row["source_base"] for row in nearest_row["candidates"]} == {
        row["source_base"] for row in proposed_row["candidates"]
    } == {"bravo", "charlie"}
    assert nearest_row["recommended"]["source_base"] == "bravo"
    assert nearest_row["recommended"]["distance_km"] < proposed_row["recommended"]["distance_km"]
    assert proposed_row["recommended"]["source_base"] == "charlie"


def test_public_simulation_builds_every_policy_from_one_snapshot_and_prediction_map(monkeypatch):
    state, predictions, plans = _readiness_fixture()
    snapshot_calls = []
    prediction_calls = []
    planner_calls = []
    provider = object()
    predictions_from_service = None

    def snapshot_once():
        snapshot_calls.append(True)
        return state

    def plan_from_same_inputs(work_order_ids=None, **kwargs):
        nonlocal predictions_from_service
        planner_calls.append((work_order_ids, kwargs))
        assert kwargs["_state"] is state
        if predictions_from_service is None:
            predictions_from_service = kwargs["_predictions"]
        assert kwargs["_predictions"] is predictions_from_service
        if kwargs.get("allocate_new") is False:
            return plans["no_action"]
        if kwargs["source_policy"] == "nearest_feasible":
            return plans["nearest_feasible"]
        return plans["proposed"]

    def build_predictions(_provider, aircraft_id):
        prediction_calls.append(aircraft_id)
        return predictions[aircraft_id]

    monkeypatch.setattr(readiness_service, "snapshot", snapshot_once)
    monkeypatch.setattr(readiness_service, "get_provider", lambda: provider)
    monkeypatch.setattr(readiness_service, "predict_validated", build_predictions)
    monkeypatch.setattr(readiness_service, "allocation_preview", plan_from_same_inputs)

    result = readiness_service.readiness_simulation(horizon_hours=48)

    assert len(snapshot_calls) == 1
    assert sorted(prediction_calls) == ["A1", "A2", "A3", "A4", "A5"]
    assert len(planner_calls) == 3
    assert {kwargs.get("source_policy", "no_action") for _, kwargs in planner_calls} == {
        "no_action", "nearest_feasible", "proposed",
    }
    assert result["mutated_state"] is False


def test_impact_preview_does_not_claim_gain_for_an_already_available_target(monkeypatch):
    state = {
        "aircraft": [
            {"id": "A1", "base_id": "alpha", "status": "AVAILABLE"},
            {"id": "A2", "base_id": "bravo", "status": "AT_RISK"},
        ],
        "work_orders": [
            _wo("WO-OPEN", "A1", "HP-204", WorkOrderStatus.OPEN.value, 4),
        ],
        "inventory": [
            {"base_id": "bravo", "part_number": "HP-204", "quantity": 1,
             "reserved": 0, "minimum_reserve": 0, "condition_pct": 90},
        ],
    }
    candidate = {
        "source_base": "bravo", "destination_base": "alpha", "part_number": "HP-204",
        "expected_downtime_hours": 5.0, "eta_hours": 1.0, "condition_pct": 90,
        "rank": 1, "ranking_explanation": "test", "score": 90,
        "donor_impact": "LOW", "fleet_impact": "LOW",
    }
    monkeypatch.setattr(impact_service, "snapshot", lambda: deepcopy(state))
    monkeypatch.setattr(impact_service, "get_provider", lambda: object())
    monkeypatch.setattr(impact_service, "predict_validated", lambda *_args: {
        "risk_level": "HIGH", "rul": 1, "rul_unit": "cycles",
        "subsystem": None, "predicted_issue": None,
    })
    monkeypatch.setattr(impact_service, "search_from_snapshot", lambda *_args: {})
    monkeypatch.setattr(impact_service, "evaluate_candidates_from_snapshot", lambda *_args, **_kwargs: {
        "aircraft_id": "A1", "candidates": [candidate], "recommended": candidate, "rejected": [],
    })
    before = deepcopy(state)

    result = impact_service.preview("WO-OPEN")

    option = result["options"][0]
    assert result["current_available"] == 1
    assert result["current_fleet_availability_pct"] == 50.0
    assert option["target_aircraft_returns_to_service"] is False
    assert option["target_aircraft_status_after_completion"] == "AT_RISK"
    assert option["projected_fleet_availability_pct"] == 50.0
    assert option["delta_pct"] == 0.0
    assert state == before

