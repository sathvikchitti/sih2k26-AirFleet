"""Read-only, target-specific impact estimates for recommendation options."""

from __future__ import annotations

from copy import deepcopy

from ..domain.enums import AircraftStatus, WorkOrderStatus
from ..repositories import OPEN_WORK_ORDER_STATUSES, snapshot
from .availability_service import classify_aircraft_from_snapshot
from .ml import get_provider, predict_validated
from .recommendation_service import evaluate_candidates_from_snapshot
from .resource_service import search_from_snapshot


def _overview(aircraft: list[dict], base_id: str | None = None) -> dict:
    rows = [row for row in aircraft if base_id is None or row.get("base_id") == base_id]
    total = len(rows)
    available = sum(row.get("status") == AircraftStatus.AVAILABLE.value for row in rows)
    return {
        "total": total,
        "available": available,
        "availability_pct": round(available / total * 100, 1) if total else 0.0,
    }


def _projected_base(base_id: str, aircraft: list[dict], recovered: bool) -> dict:
    current = _overview(aircraft, base_id)
    available = min(current["total"], current["available"] + int(recovered))
    return {
        "base_id": base_id,
        "current_available": current["available"],
        "aircraft_count": current["total"],
        "current_availability_pct": current["availability_pct"],
        "projected_available": available,
        "projected_availability_pct": round(available / current["total"] * 100, 1)
        if current["total"] else 0.0,
    }


def _donor_estimate(candidate: dict, work_order_id: str, state: dict) -> dict:
    inv = next((row for row in state.get("inventory", [])
                if row.get("base_id") == candidate["source_base"]
                and row.get("part_number") == candidate.get("part_number")), None)
    transferable = (int(inv.get("quantity", 0)) - int(inv.get("reserved", 0))
                    - int(inv.get("minimum_reserve", 0))) if inv else 0
    after_transfer = max(0, transferable - 1)
    outstanding = sum(
        1 for row in state.get("work_orders", [])
        if row.get("status") in OPEN_WORK_ORDER_STATUSES
        and row.get("id") != work_order_id
        and row.get("base_id") == candidate["source_base"]
        and row.get("required_component") == candidate.get("part_number")
    )
    return {
        "base_id": candidate["source_base"],
        "transferable_units_after": after_transfer,
        "open_work_orders_for_component": outstanding,
        "stockout_risk": "ELEVATED" if outstanding and after_transfer == 0 else "NOT_INDICATED",
        "current_aircraft_availability_unchanged_by_inventory_estimate": True,
    }


def preview(work_order_id: str) -> dict:
    """Estimate a single work order without writing recommendation audit data.

    Availability increases only when completing the target work order would
    make that aircraft AVAILABLE under the same classifier used by live state
    synchronization. A completed FD001 maintenance order alone does not erase
    its current model risk because its model output has no subsystem mapping.
    """
    state = snapshot()
    aircraft_rows = deepcopy(state.get("aircraft", []))
    work_order = next((row for row in state.get("work_orders", [])
                       if str(row.get("id", "")).upper() == str(work_order_id).upper()), None)
    baseline = _overview(aircraft_rows)
    if work_order is None:
        return {"work_order_id": work_order_id, "options": [], "recommended": None,
                "current_fleet_availability_pct": baseline["availability_pct"],
                "current_available": baseline["available"], "total": baseline["total"],
                "projection_type": "estimate", "assumptions": ["Unknown work order"]}

    aircraft_id = work_order["aircraft_id"]
    provider = get_provider()
    prediction = predict_validated(provider, aircraft_id)
    found = search_from_snapshot(work_order, state.get("inventory", []))
    baseline_downtime = baseline["total"] - baseline["available"]
    evaluation = evaluate_candidates_from_snapshot(
        work_order, prediction, found, baseline_downtime=baseline_downtime,
    )

    hypothetical_work_orders = deepcopy(state.get("work_orders", []))
    target = next(row for row in hypothetical_work_orders if row["id"] == work_order["id"])
    target["status"] = WorkOrderStatus.COMPLETED.value
    post_completion_status = classify_aircraft_from_snapshot(
        aircraft_id, [row for row in hypothetical_work_orders if row["aircraft_id"] == aircraft_id],
        prediction,
    )
    target_recovered = bool(
        next((row for row in aircraft_rows if row["id"] == aircraft_id), {}).get("status")
        != AircraftStatus.AVAILABLE.value
        and post_completion_status == AircraftStatus.AVAILABLE.value
    )

    options = []
    for candidate in evaluation.get("candidates", []):
        recovery_hours = float(candidate["expected_downtime_hours"])
        fleet_available = min(baseline["total"], baseline["available"] + int(target_recovered))
        projected_pct = round(fleet_available / baseline["total"] * 100, 1) if baseline["total"] else 0.0
        destination = _projected_base(work_order["base_id"], aircraft_rows, target_recovered)
        source = _projected_base(candidate["source_base"], aircraft_rows, False)
        options.append({
            "source_base": candidate["source_base"],
            "destination_base": candidate["destination_base"],
            "part_number": candidate.get("part_number"),
            "feasible": True,
            "rank": candidate.get("rank"),
            "ranking_explanation": candidate.get("ranking_explanation"),
            "score": candidate.get("score"),
            "eta_hours": candidate.get("eta_hours"),
            "expected_downtime_hours": recovery_hours,
            "work_order_completion_estimate_hours": recovery_hours,
            "time_to_available_hours": recovery_hours if target_recovered else None,
            "projected_at_hours": recovery_hours,
            "projection_event": "work_order_completion",
            "component_condition": candidate.get("condition_pct"),
            "donor_impact": candidate.get("donor_impact"),
            "fleet_impact": candidate.get("fleet_impact"),
            "current_fleet_availability_pct": baseline["availability_pct"],
            "projected_fleet_availability_pct": projected_pct,
            "projected_availability_pct": projected_pct,
            "expected_fleet_availability_pct": projected_pct,
            "delta_pct": round(projected_pct - baseline["availability_pct"], 1),
            "target_aircraft_returns_to_service": target_recovered,
            "target_aircraft_status_after_completion": post_completion_status,
            "destination_base_projection": destination,
            "source_base_projection": source,
            "donor_base_projection": _donor_estimate(candidate, work_order_id, state),
            "assumptions": [
                "Work-order completion is estimated at transfer ETA plus planned repair duration; this is not a return-to-service time unless the shared classifier returns AVAILABLE.",
                "Only this target work order is completed in the projection; other work orders retain their snapshot status.",
                "Post-completion availability uses the same classifier and frozen prediction as the current snapshot.",
                "Inventory loss is reported as stock risk, not converted into aircraft downtime.",
            ],
        })

    recommended = evaluation.get("recommended")
    selected = next((row for row in options
                     if recommended and row["source_base"] == recommended["source_base"]), None)
    return {
        "work_order_id": work_order_id,
        "aircraft_id": evaluation.get("aircraft_id"),
        "current_fleet_availability_pct": baseline["availability_pct"],
        "current_available": baseline["available"],
        "total": baseline["total"],
        "options": options,
        "recommended": ({
            "source_base": selected["source_base"],
            "destination_base": selected["destination_base"],
            "expected_fleet_availability_pct": selected["projected_fleet_availability_pct"],
            "projected_at_hours": selected["projected_at_hours"],
            "expected_downtime_hours": selected["expected_downtime_hours"],
            "work_order_completion_estimate_hours": selected["work_order_completion_estimate_hours"],
            "time_to_available_hours": selected["time_to_available_hours"],
            "target_aircraft_returns_to_service": selected["target_aircraft_returns_to_service"],
        } if selected else None),
        "rejected": evaluation.get("rejected", []),
        "projection_type": "estimate",
        "method": "target-specific availability after hypothetical work-order completion; no state is changed",
        "assumptions": [
            "Legacy expected_downtime_hours/projected_at_hours fields describe estimated work-order completion, not guaranteed aircraft recovery.",
            "time_to_available_hours is null unless the target is projected AVAILABLE under the shared classifier.",
            "The target receives no availability uplift unless the shared live classifier returns AVAILABLE after completion.",
            "Donor inventory constraints are surfaced separately; no unsupported donor aircraft outage is assumed.",
            "Actual availability changes only when aircraft and work-order state changes.",
        ],
    }
