"""Read-only fleet readiness what-if comparisons over one frozen snapshot."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from ..domain.enums import AircraftStatus, WorkOrderStatus
from ..repositories import snapshot
from .availability_service import classify_aircraft_from_snapshot
from .ml import get_provider, predict_validated
from .planning_service import allocation_preview

_POLICIES = ("no_action", "nearest_feasible", "proposed")


def _merge_plan(common: dict, selected: dict) -> dict:
    """Overlay selected hypothetical allocations on common existing commitments."""
    merged = deepcopy(common)
    by_id = {row["work_order_id"]: row for row in merged.get("allocations", [])}
    for row in selected.get("allocations", []):
        by_id[row["work_order_id"]] = row
    selected_order = [row["work_order_id"] for row in common.get("allocations", [])]
    merged["allocations"] = [by_id[work_order_id] for work_order_id in selected_order
                             if work_order_id in by_id]
    merged["inventory_effects"] = selected.get("inventory_effects", common.get("inventory_effects", []))
    merged["conflicts"] = list(common.get("conflicts", []))
    for conflict in selected.get("conflicts", []):
        if conflict not in merged["conflicts"]:
            merged["conflicts"].append(conflict)
    merged["unknown_work_order_ids"] = selected.get("unknown_work_order_ids", [])
    merged["selected_work_order_ids"] = selected.get("selected_work_order_ids", [])
    return merged


def _work_order_schedule(state: dict, plan: dict) -> tuple[dict[str, float], dict[str, float]]:
    """Build hypothetical start/completion times for eligible work orders."""
    work_orders = {row["id"]: row for row in state.get("work_orders", [])}
    transfers = {row.get("id"): row for row in state.get("transfers", [])}
    allocations = {row.get("work_order_id"): row for row in plan.get("allocations", [])}
    starts: dict[str, float] = {}
    completions: dict[str, float] = {}

    for work_order_id, work_order in work_orders.items():
        status = work_order.get("status")
        if status in (WorkOrderStatus.COMPLETED.value, WorkOrderStatus.CANCELLED.value):
            continue
        allocation = allocations.get(work_order_id, {})
        allocation_status = allocation.get("allocation_status")
        repair = max(0.0, float(work_order.get("estimated_repair_hours") or 4.0))
        transfer_eta = 0.0

        if status == WorkOrderStatus.IN_PROGRESS.value:
            # Elapsed progress is not recorded; simulate the full planned
            # repair duration from the frozen snapshot in every policy, but
            # only when its resource is actually reserved/serviceable.
            if allocation_status not in {"IN_PROGRESS_RESOURCE_RESERVED",
                                          "IN_PROGRESS_LOCAL_EARMARKED"}:
                continue
            starts[work_order_id] = 0.0
            completions[work_order_id] = repair
            continue

        if allocation_status in {"EXISTING_IN_TRANSIT", "EXISTING_PENDING_APPROVAL"}:
            if allocation_status == "EXISTING_PENDING_APPROVAL":
                # A pending transfer is a request, not an approved dispatch.
                continue
            if allocation.get("can_start_on_arrival") is False:
                # An existing dispatch can arrive physically while remaining
                # unusable under the same destination reserve/condition rules
                # that maintenance start applies. Do not count a repair that
                # cannot actually begin.
                continue
            transfer = transfers.get(allocation.get("transfer_id"), {})
            transfer_eta = max(0.0, float(transfer.get("eta_hours") or 0.0))
        elif allocation_status in {"RECEIVED_RESOURCE_EARMARKED", "RECEIVED_RESOURCE_RESERVED",
                                   "EXISTING_LOCAL_RESOURCE_EARMARKED"}:
            transfer_eta = 0.0
        elif allocation_status == "PROPOSED_LOCAL_ALLOCATION":
            transfer_eta = 0.0
        elif allocation_status == "PROPOSED_LOCAL_PROCUREMENT":
            transfer_eta = max(0.0, float(allocation.get("procurement_eta_hours") or 0.0))
        elif allocation_status == "PROPOSED_REMOTE_TRANSFER":
            recommendation = allocation.get("recommended") or {}
            transfer_eta = max(0.0, float(recommendation.get("eta_hours") or 0.0))
        else:
            # Open WOs without a serviceable local unit, approved transfer, or
            # feasible proposal remain blocked for this what-if.
            continue

        starts[work_order_id] = transfer_eta
        completions[work_order_id] = transfer_eta + repair
    return starts, completions


def _curve_for_policy(state: dict, predictions: dict[str, dict], plan: dict,
                      horizon_hours: float) -> list[dict]:
    aircraft_rows = deepcopy(state.get("aircraft", []))
    work_orders = deepcopy(state.get("work_orders", []))
    starts, completions = _work_order_schedule(state, plan)
    affected_aircraft = {wo["aircraft_id"] for wo in work_orders if wo["id"] in starts}
    times = {0.0, float(horizon_hours)}
    times.update(time for time in starts.values() if 0.0 < time < horizon_hours)
    times.update(time for time in completions.values() if 0.0 < time < horizon_hours)
    ordered_times = sorted(times)
    curve = []
    cumulative_available_hours = 0.0
    previous_hour: float | None = None
    previous_available = 0

    for hour in ordered_times:
        if previous_hour is not None:
            cumulative_available_hours += previous_available * (hour - previous_hour)
        hypothetical = deepcopy(work_orders)
        completed_ids = {work_order_id for work_order_id, done_at in completions.items()
                         if done_at <= hour}
        started_ids = {work_order_id for work_order_id, start_at in starts.items()
                       if start_at <= hour}
        for row in hypothetical:
            if row["id"] in completed_ids:
                row["status"] = WorkOrderStatus.COMPLETED.value
            elif row["id"] in started_ids:
                row["status"] = WorkOrderStatus.IN_PROGRESS.value
        grouped: dict[str, list[dict]] = {}
        for row in hypothetical:
            grouped.setdefault(row["aircraft_id"], []).append(row)

        statuses: dict[str, str] = {}
        for aircraft in aircraft_rows:
            aircraft_id = aircraft["id"]
            status = aircraft.get("status", AircraftStatus.UNAVAILABLE.value)
            if aircraft_id in affected_aircraft and aircraft_id in predictions:
                status = classify_aircraft_from_snapshot(
                    aircraft_id, grouped.get(aircraft_id, []), predictions[aircraft_id],
                )
            statuses[aircraft_id] = status

        available = sum(status == AircraftStatus.AVAILABLE.value for status in statuses.values())
        breakdown: dict[str, int] = {}
        for status in statuses.values():
            breakdown[status] = breakdown.get(status, 0) + 1
        total = len(aircraft_rows)
        curve.append({
            "hours": round(hour, 8),
            "available_aircraft": available,
            "total_aircraft": total,
            "availability_pct": round(available / total * 100, 1) if total else 0.0,
            "aircraft_by_status": breakdown,
            "completed_work_order_ids": sorted(completed_ids),
            "started_work_order_ids": sorted(started_ids),
            "cumulative_available_aircraft_hours": round(cumulative_available_hours, 8),
        })
        previous_hour = hour
        previous_available = available
    return curve


def simulate_policy_from_snapshot(state_snapshot: dict[str, Any],
                                  prediction_map: dict[str, dict],
                                  plan: dict, horizon_hours: float = 48.0) -> dict[str, Any]:
    """Return one pure policy curve and metrics for isolated evaluations."""
    horizon = float(horizon_hours)
    if not math.isfinite(horizon) or horizon < 0 or horizon > 168:
        raise ValueError("horizon_hours must be finite and between 0 and 168")
    curve = _curve_for_policy(state_snapshot, prediction_map, plan, horizon)
    area = float(curve[-1]["cumulative_available_aircraft_hours"])
    total = int(curve[-1]["total_aircraft"])
    return {
        "curve": curve,
        "metrics": {
            "available_aircraft_hours": round(area, 8),
            "aircraft_downtime_hours": round(max(0.0, total * horizon - area), 8),
            "time_weighted_average_availability_pct": round(area / (total * horizon) * 100, 4)
            if total and horizon > 0 else None,
            "work_orders_completed_by_horizon": len(curve[-1]["completed_work_order_ids"]),
        },
    }


def simulate_readiness_from_snapshot(state_snapshot: dict[str, Any],
                                     prediction_map: dict[str, dict],
                                     plans: dict[str, dict],
                                     horizon_hours: float = 48.0) -> dict[str, Any]:
    """Pure simulation over provided, frozen data and allocation plans."""
    horizon = float(horizon_hours)
    if not math.isfinite(horizon) or horizon < 0 or horizon > 168:
        raise ValueError("horizon_hours must be finite and between 0 and 168")
    missing = set(_POLICIES) - set(plans)
    if missing:
        raise ValueError(f"missing allocation plans: {', '.join(sorted(missing))}")

    policies: dict[str, dict] = {}
    for name in _POLICIES:
        plan = plans[name]
        policies[name] = {
            "policy": name,
            "label": {"no_action": "No new allocations", "nearest_feasible": "Nearest feasible",
                      "proposed": "Proposed ranking"}[name],
            "new_allocations_enabled": name != "no_action",
            "curve": _curve_for_policy(state_snapshot, prediction_map, plan, horizon),
            "allocations": deepcopy(plan.get("allocations", [])),
            "inventory_effects": deepcopy(plan.get("inventory_effects", [])),
            "conflicts": deepcopy(plan.get("conflicts", [])),
        }

    times = sorted({point["hours"] for policy in policies.values() for point in policy["curve"]})
    comparison = []
    for hour in times:
        row = {"hours": hour}
        no_action_point = max((point for point in policies["no_action"]["curve"]
                               if point["hours"] <= hour), key=lambda point: point["hours"])
        baseline_pct = no_action_point["availability_pct"]
        for name in _POLICIES:
            point = max((point for point in policies[name]["curve"] if point["hours"] <= hour),
                        key=lambda item: item["hours"])
            row[name] = {
                "available_aircraft": point["available_aircraft"],
                "availability_pct": point["availability_pct"],
                "delta_vs_no_action_pct_points": round(point["availability_pct"] - baseline_pct, 1),
            }
        comparison.append(row)

    initial_available = sum(row.get("status") == AircraftStatus.AVAILABLE.value
                            for row in state_snapshot.get("aircraft", []))
    total = len(state_snapshot.get("aircraft", []))
    policy_metrics = {}
    for name, policy in policies.items():
        area = float(policy["curve"][-1]["cumulative_available_aircraft_hours"])
        total = int(policy["curve"][-1]["total_aircraft"])
        policy_metrics[name] = {
            "available_aircraft_hours": round(area, 8),
            "aircraft_downtime_hours": round(max(0.0, total * horizon - area), 8),
            "time_weighted_average_availability_pct": round(area / (total * horizon) * 100, 4)
            if total and horizon > 0 else None,
            "work_orders_completed_by_horizon": len(policy["curve"][-1]["completed_work_order_ids"]),
        }
        policy["metrics"] = policy_metrics[name]

    return {
        "snapshot_type": "frozen_read_only_fleet_snapshot",
        "horizon_hours": horizon,
        "horizon_unit": "hours",
        "current_available_aircraft": initial_available,
        "total_aircraft": total,
        "current_availability_pct": round(initial_available / total * 100, 1) if total else 0.0,
        "policies": policies,
        "policy_metrics": policy_metrics,
        "comparison": comparison,
        "mutated_state": False,
        "assumptions": [
            "All policies use one fleet, inventory, work-order, transfer, and prediction snapshot.",
            "Already IN_TRANSIT arrivals and resource-available/in-progress maintenance are common to every policy.",
            "A nearest/proposed new allocation is assumed approved immediately; maintenance starts on local availability or at remote arrival. No-action makes no new allocations but allows common existing work to progress.",
            "Saved transfer ETA is treated as remaining from the snapshot; elapsed travel is not inferred.",
            "Elapsed maintenance progress is not recorded, so full planned repair duration is simulated from the snapshot.",
            "PENDING_APPROVAL transfers remain unapproved in every policy and do not complete a work order.",
            "Nearest feasible ranks the shared feasible candidates by distance, then ETA, then base ID.",
            "Proposed uses the existing shared-stock allocation and recommendation ranking policy.",
            "RUL values in cycles are not converted to hours; completion uses transfer ETA and planned repair duration only.",
            "Completion changes status only through the existing classifier and fixed prediction; no telemetry or recovery is fabricated.",
            "This is a scenario estimate, not a live state change or operational flight-release decision.",
        ],
    }


def readiness_simulation(work_order_ids: list[str] | None = None,
                         horizon_hours: float = 48.0) -> dict[str, Any]:
    """Build three policy plans against one snapshot and simulate them purely."""
    state = snapshot()
    provider = get_provider()
    predictions = {
        row["id"].upper(): predict_validated(provider, row["id"])
        for row in state.get("aircraft", [])
    }
    common = allocation_preview(None, allocate_new=False, _state=state,
                                _predictions=predictions)
    plans = {"no_action": common}
    for name, source_policy in (("nearest_feasible", "nearest_feasible"),
                                ("proposed", "proposed")):
        selected = allocation_preview(work_order_ids, source_policy=source_policy,
                                      _state=state, _predictions=predictions)
        plans[name] = _merge_plan(common, selected)
    return simulate_readiness_from_snapshot(state, predictions, plans, horizon_hours)
