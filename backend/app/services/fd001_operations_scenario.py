"""Opt-in, synthetic operations fixture layered over the FD001 predictions.

This module is deliberately separate from prediction/maintenance business
logic. It builds one demo state through repositories and the same authorized
services used by the API. It does not modify sensor histories or model output.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain.enums import Permission
from ..repositories import (
    AircraftRepository,
    EventRepository,
    InventoryRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
    refresh_line_status,
    store,
)
from ..security import require_demo_permission
from . import maintenance_service, recommendation_service, transfer_service

SCENARIO_ID = "fd001_operations_v1"
SCENARIO_LABEL = "FD001 synthetic operations scenarios"


def _authorized(role: str, permission: Permission, base_id: str | None = None) -> str:
    return require_demo_permission(
        role,
        permission,
        demo_role=role,
        demo_base=base_id if role == "base" else None,
        resource_base=base_id if role == "base" else None,
    )


def _set_initial_reserve(base_id: str, part_number: str, minimum_reserve: int) -> None:
    """Configure fixture reserve policy before any fixture transaction."""
    inventory = InventoryRepository.find(base_id, part_number)
    if inventory is None:
        raise RuntimeError(f"fixture requires inventory line {base_id}/{part_number}")
    InventoryRepository.update(inventory["id"], minimum_reserve=int(minimum_reserve))
    refresh_line_status(InventoryRepository.get(inventory["id"]))


def initialize_fd001_operations_scenario() -> dict:
    """Create the deterministic A–F operations fixture over clean FD001 state.

    Inventory quantities are never assigned here. Seed reserve policy is set
    before business actions; subsequent stock movement only uses transfer,
    receipt, maintenance-start and maintenance-completion services.
    """
    state = store()

    # The clean FD001 initializer removes the mock work orders but retains the
    # seed inventory. This reservation belonged to a removed mock work order,
    # so normalize it before the new scenario's transactions begin.
    alpha_fp = InventoryRepository.find("alpha", "FP-102")
    if alpha_fp and int(alpha_fp.get("reserved", 0)):
        InventoryRepository.update(alpha_fp["id"], reserved=0)
        refresh_line_status(InventoryRepository.get(alpha_fp["id"]))

    # C: Bravo's single HP-204 is protected at its minimum reserve; Charlie is
    # the remaining feasible donor. D: both remote OE-310 quantities are held
    # at reserve, so the actual recommendation has no feasible candidate.
    _set_initial_reserve("bravo", "HP-204", 1)
    _set_initial_reserve("alpha", "OE-310", 2)
    _set_initial_reserve("charlie", "OE-310", 3)

    def triage(aircraft_id: str, component: str) -> dict:
        aircraft = AircraftRepository.get(aircraft_id)
        if aircraft is None:
            raise RuntimeError(f"fixture aircraft {aircraft_id} is missing")
        event = next(
            (row for row in EventRepository.find_by_aircraft(aircraft_id)
             if row.get("status") == "OPEN"),
            None,
        )
        if event is None:
            raise RuntimeError(f"FD001 prediction for {aircraft_id} did not create an open event")
        actor = _authorized("base", Permission.REQUEST_RESOURCE, aircraft["base_id"])
        order = maintenance_service.create_work_order_from_event(
            event["id"], required_component=component, actor=actor
        )
        if order is None:
            raise RuntimeError(f"could not triage FD001 event {event['id']} for {aircraft_id}")
        WorkOrderRepository.update(order["id"], component_source="human_selected")
        return order

    # A: A17's model-derived LOW signal remains unconstrained by an operational
    # fixture work order. B: A32's HIGH model signal gets a human-selected
    # catalog component and an open predictive work order.
    b_order = triage("A32", "FP-102")

    # C: A21's CRITICAL prediction is triaged with a human-selected HP-204.
    # The Commander-authorized recommendation creates a real in-transit
    # transfer from Charlie and decrements Charlie stock via existing services.
    c_order = triage("A21", "HP-204")
    c_recommendation = recommendation_service.evaluate_candidates(c_order["id"])
    if c_recommendation.get("recommended", {}).get("source_base") != "charlie":
        raise RuntimeError("fixture C must recommend Charlie after Bravo reserve is applied")
    commander = _authorized("commander", Permission.APPROVE_RECOMMENDATION)
    c_result = transfer_service.approve_recommendation(c_order["id"], actor=commander)
    c_transfer = c_result["transfer"]

    # D: A28 is at Bravo, which has no OE-310. Alpha and Charlie stock remain
    # physically present but their full quantities are protected by reserve.
    d_actor = _authorized("base", Permission.REQUEST_RESOURCE, "bravo")
    d_order = maintenance_service.create_manual_work_order(
        "A28", "OE-310", issue="Reserve-protected OE-310 inspection scenario",
        estimated_repair_hours=4.0, actor=d_actor,
    )
    if d_order is None:
        raise RuntimeError("fixture D could not create its manual inspection work order")
    WorkOrderRepository.update(d_order["id"], component_source="fixture_scenario")
    d_evaluation = recommendation_service.evaluate_candidates(d_order["id"])
    if d_evaluation.get("recommended") is not None or d_evaluation.get("candidates"):
        raise RuntimeError("fixture D unexpectedly has a feasible OE-310 transfer")
    recommendation_service.record_recommendation_evaluation(
        d_order["id"], d_evaluation, actor="fixture-scenario",
    )

    # E: A26 has one local FP-102. The Base Manager starts maintenance through
    # the service, which reserves that physical unit against this work order.
    e_actor = _authorized("base", Permission.REQUEST_RESOURCE, "bravo")
    e_order = maintenance_service.create_manual_work_order(
        "A26", "FP-102", issue="Scheduled synthetic maintenance-in-progress scenario",
        estimated_repair_hours=3.0, actor=e_actor,
    )
    if e_order is None:
        raise RuntimeError("fixture E could not create its maintenance work order")
    WorkOrderRepository.update(e_order["id"], component_source="fixture_scenario")
    e_order = maintenance_service.start_maintenance(e_order["id"], actor=e_actor)

    # F: A24's manual AV-077 work order receives a real catalogued transfer at
    # Bravo, then reserves and consumes the received unit through maintenance.
    f_actor = _authorized("base", Permission.REQUEST_RESOURCE, "bravo")
    f_order = maintenance_service.create_manual_work_order(
        "A24", "AV-077", issue="Completed synthetic AV-077 maintenance scenario",
        estimated_repair_hours=5.0, actor=f_actor,
    )
    if f_order is None:
        raise RuntimeError("fixture F could not create its completed work order")
    WorkOrderRepository.update(f_order["id"], component_source="fixture_scenario")
    commander = _authorized("commander", Permission.APPROVE_RECOMMENDATION)
    f_result = transfer_service.approve_recommendation(f_order["id"], actor=commander)
    f_transfer = f_result["transfer"]
    logistics = _authorized("logistics", Permission.MANAGE_TRANSFERS)
    transfer_service.receive_transfer(f_transfer["id"], actor=logistics)
    f_order = maintenance_service.start_maintenance(f_order["id"], actor=f_actor)
    f_order = maintenance_service.complete_maintenance(f_order["id"], actor=f_actor)

    manifest = {
        "scenario_id": SCENARIO_ID,
        "label": SCENARIO_LABEL,
        "operational_data_synthetic": True,
        "operational_data_source": "fd001_operations_fixture",
        "model_provider": "fd001-random-forest",
        "model_version": "cmapss-fd001-rf-v1",
        "scenarios": [
            {
                "id": "A", "name": "Normal operations", "aircraft_id": "A17",
                "operational_state_source": "model_prediction", "work_order_id": None,
                "next_action": "none",
            },
            {
                "id": "B", "name": "Predictive maintenance", "aircraft_id": "A32",
                "event_id": b_order["predicted_event_id"], "work_order_id": b_order["id"],
                "component_selection_source": "human_selected",
                "next_action": "review_resource_recommendation",
            },
            {
                "id": "C", "name": "Cross-base shortage", "aircraft_id": "A21",
                "event_id": c_order["predicted_event_id"], "work_order_id": c_order["id"],
                "transfer_id": c_transfer["id"], "component_selection_source": "human_selected",
                "next_action": "receive_in_transit_transfer",
            },
            {
                "id": "D", "name": "No feasible transfer", "aircraft_id": "A28",
                "work_order_id": d_order["id"], "component_selection_source": "fixture_scenario",
                "next_action": "review_infeasible_donors",
            },
            {
                "id": "E", "name": "Maintenance in progress", "aircraft_id": "A26",
                "work_order_id": e_order["id"], "component_selection_source": "fixture_scenario",
                "next_action": "complete_maintenance",
            },
            {
                "id": "F", "name": "Completed maintenance", "aircraft_id": "A24",
                "work_order_id": f_order["id"], "transfer_id": f_transfer["id"],
                "component_selection_source": "fixture_scenario",
                "next_action": "review_completed_work_order",
            },
        ],
        "initialized_at": datetime.now(timezone.utc).isoformat(),
    }
    state["demo_scenario"] = manifest
    return manifest


def scenario_manifest() -> dict:
    """Return fixture metadata, without synthesizing dashboard values."""
    scenario = store().get("demo_scenario")
    if scenario:
        return scenario
    return {
        "scenario_id": None,
        "label": None,
        "operational_data_synthetic": True,
        "operational_data_source": None,
        "model_provider": None,
        "model_version": None,
        "scenarios": [],
    }
