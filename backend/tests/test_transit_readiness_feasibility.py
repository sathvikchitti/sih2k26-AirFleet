"""Existing in-transit work only completes in what-if plans if arrival is usable."""

from copy import deepcopy

import pytest

from app.repositories import reset, snapshot
from app.services import planning_service, readiness_service


@pytest.fixture(autouse=True)
def initialized_catalog():
    reset()


def _transit_case(*, destination_qty=0, destination_reserved=0,
                  destination_minimum=0, destination_condition=0,
                  incoming_condition=42):
    state = snapshot()
    aircraft = next(row for row in state["aircraft"] if row["id"] == "A21")
    state["aircraft"] = [aircraft]
    aircraft["status"] = "WAITING_FOR_PART"
    inventory = next(row for row in state["inventory"]
                     if row["base_id"] == "alpha" and row["part_number"] == "HP-204")
    inventory.update(quantity=destination_qty, reserved=destination_reserved,
                     minimum_reserve=destination_minimum,
                     condition_pct=destination_condition)
    state["inventory"] = [inventory]
    state["work_orders"] = [{
        "id": "WO-TRANSIT-1", "aircraft_id": "A21", "base_id": "alpha",
        "required_component": "HP-204", "priority": "HIGH",
        "status": "WAITING_FOR_RESOURCE", "estimated_repair_hours": 2,
        "created_at": "2026-01-01T00:00:00+00:00", "resource_reserved": False,
    }]
    state["transfers"] = [{
        "id": "T-TRANSIT-1", "work_order_id": "WO-TRANSIT-1",
        "part_number": "HP-204", "source_base": "bravo", "dest_base": "alpha",
        "quantity": 1, "status": "IN_TRANSIT", "eta_hours": 5,
        "condition_pct": incoming_condition,
    }]
    return state


def _plans(state):
    predictions = {"A21": {"risk_level": "LOW", "health_score": 90,
                           "rul": 90, "rul_unit": "flight_hours",
                           "subsystem": None, "predicted_issue": None}}
    common = planning_service.allocation_preview(
        None, allocate_new=False, _state=state, _predictions=predictions,
    )
    plans = {"no_action": common}
    for name, policy in (("nearest_feasible", "nearest_feasible"), ("proposed", "proposed")):
        plans[name] = readiness_service._merge_plan(
            common,
            planning_service.allocation_preview(
                ["WO-TRANSIT-1"], source_policy=policy, _state=state,
                _predictions=predictions,
            ),
        )
    return predictions, plans


@pytest.mark.parametrize("destination, incoming", [
    ({"destination_qty": 1, "destination_condition": 35}, 42),  # conservative merge keeps line below min
    ({"destination_qty": 0, "destination_minimum": 1}, 42),  # arrival remains at reserve floor
    ({"destination_qty": 0}, 35),  # dispatched condition itself is below component min
])
def test_in_transit_arrival_that_cannot_be_started_is_not_simulated_as_completed(destination, incoming):
    state = _transit_case(**destination, incoming_condition=incoming)
    before = deepcopy(state)
    predictions, plans = _plans(state)

    plan_row = plans["proposed"]["allocations"][0]
    assert plan_row["allocation_status"] == "EXISTING_IN_TRANSIT"
    assert plan_row["can_start_on_arrival"] is False
    assert plan_row["arrival_block_reason"] in {
        "DESTINATION_CONDITION_BELOW_MINIMUM", "NO_TRANSFERABLE_DESTINATION_STOCK",
    }

    result = readiness_service.simulate_readiness_from_snapshot(state, predictions, plans, 48)
    assert "WO-TRANSIT-1" not in result["policies"]["proposed"]["curve"][-1]["completed_work_order_ids"]
    assert state == before


def test_usable_in_transit_arrival_keeps_eta_schedule_and_completion():
    state = _transit_case(incoming_condition=42)
    before = deepcopy(state)
    predictions, plans = _plans(state)

    plan_row = plans["proposed"]["allocations"][0]
    assert plan_row["allocation_status"] == "EXISTING_IN_TRANSIT"
    assert plan_row["can_start_on_arrival"] is True
    result = readiness_service.simulate_readiness_from_snapshot(state, predictions, plans, 48)
    curve = result["policies"]["proposed"]["curve"]
    assert "WO-TRANSIT-1" in next(point for point in curve if point["hours"] == 7)["completed_work_order_ids"]
    assert state == before


@pytest.mark.parametrize("transfer_update", [
    {"part_number": "FP-102"},
    {"dest_base": "charlie"},
    {"for_aircraft": "A32"},
])
def test_in_transit_transfer_relinked_to_different_work_order_is_not_projected_as_serviceable(transfer_update):
    state = _transit_case()
    state["transfers"][0].update(transfer_update)
    before = deepcopy(state)
    predictions, plans = _plans(state)

    plan_row = plans["proposed"]["allocations"][0]
    assert plan_row["allocation_status"] == "EXISTING_IN_TRANSIT"
    assert plan_row["can_start_on_arrival"] is False
    assert plan_row["arrival_block_reason"] == "TRANSFER_WORK_ORDER_MISMATCH"
    result = readiness_service.simulate_readiness_from_snapshot(state, predictions, plans, 48)
    assert "WO-TRANSIT-1" not in result["policies"]["proposed"]["curve"][-1]["completed_work_order_ids"]
    assert state == before
