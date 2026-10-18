"""Seeded scale simulation of shared-source maintenance allocation policies.

All generated fleets, failures, stock, routes, repair durations and outcomes
are synthetic. The module never reads or writes live repositories and does not
modify the existing recommendation baseline evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from ..domain.enums import AircraftStatus, Priority, WorkOrderStatus
from ..services.planning_service import allocation_preview
from ..services.readiness_service import _work_order_schedule, simulate_policy_from_snapshot
from ..services.resource_service import ResourceContext

SEED = 20261018
SCENARIO_COUNT = 300
AIRCRAFT_COUNT = 40
ACTIVE_WORK_ORDERS = 12
HORIZON_HOURS = 48.0
PROCUREMENT_LEAD_HOURS = 24.0
BOOTSTRAP_REPLICATES = 1000
GENERATOR_VERSION = "fleet-scale-synthetic-v1"
BASES = tuple((f"sim-base-{i:02d}", f"Simulation Base {i:02d}") for i in range(1, 7))
PARTS = tuple((f"SIM-{i:03d}", f"Synthetic Component {i:03d}", 40 + 3 * ((i - 1) % 6))
              for i in range(1, 9))
POLICIES = {
    "proposed": "Production ranking",
    "nearest_fcfs": "Nearest feasible, first-come-first-served",
    "random_feasible": "Random feasible source",
    "local_only_procurement": "Local stock / procurement only",
}


def _resource_context() -> ResourceContext:
    coordinates = ((0, 0), (120, 45), (310, 60), (450, 210), (230, 360), (40, 260))
    routes = []
    for left in range(len(BASES)):
        for right in range(left + 1, len(BASES)):
            dx = coordinates[left][0] - coordinates[right][0]
            dy = coordinates[left][1] - coordinates[right][1]
            distance = round((dx * dx + dy * dy) ** 0.5)
            routes.append((BASES[left][0], BASES[right][0], distance, round(distance / 60, 1)))
    return ResourceContext(bases=BASES, parts=PARTS, routes=tuple(routes))


RESOURCE_CONTEXT = _resource_context()
RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPORT_JSON_PATH = RESULTS_DIR / "scale_simulation.json"


def _generate_scenario(scenario_index: int) -> tuple[dict[str, Any], dict[str, dict]]:
    """Generate one fully deterministic 40-aircraft/6-base/8-part snapshot."""
    rng = random.Random(SEED + 104729 * scenario_index)
    target_aircraft = rng.sample(range(AIRCRAFT_COUNT), ACTIVE_WORK_ORDERS)
    aircraft = []
    aircraft_base: dict[int, str] = {}
    for index in range(AIRCRAFT_COUNT):
        base_id = BASES[index % len(BASES)][0]
        aircraft_base[index] = base_id
        aircraft.append({
            "id": f"S{scenario_index:03d}-A{index + 1:02d}",
            "base_id": base_id,
            "type": "Synthetic airframe",
            "status": (AircraftStatus.WAITING_FOR_PART.value if index in target_aircraft
                       else AircraftStatus.AVAILABLE.value),
        })

    # Six part types each receive two simultaneous work orders. This fixed
    # contention pattern makes shared-stock scarcity part of every run.
    target_part_numbers = [PARTS[index // 2][0] for index in range(ACTIVE_WORK_ORDERS)]
    work_orders = []
    target_inventory_keys: set[tuple[str, str]] = set()
    for order_index, aircraft_index in enumerate(target_aircraft):
        component = target_part_numbers[order_index]
        base_id = aircraft_base[aircraft_index]
        target_inventory_keys.add((base_id, component))
        work_orders.append({
            "id": f"S{scenario_index:03d}-WO{order_index + 1:02d}",
            "aircraft_id": aircraft[aircraft_index]["id"],
            "base_id": base_id,
            "required_component": component,
            "status": WorkOrderStatus.WAITING_FOR_RESOURCE.value,
            "priority": rng.choice([value.value for value in Priority]),
            "created_at": f"2026-01-{1 + order_index:02d}T08:00:00+00:00",
            "estimated_repair_hours": float(rng.randint(8, 32)),
            "resource_reserved": False,
        })

    parts = [{"part_number": number, "name": name, "min_condition_pct": minimum}
             for number, name, minimum in PARTS]
    inventory = []
    for base_id, _ in BASES:
        for part_number, _name, minimum in PARTS:
            quantity = rng.choices((0, 1, 2, 3, 4), weights=(34, 25, 20, 13, 8))[0]
            reserved = rng.randint(0, min(quantity, 1))
            minimum_reserve = rng.randint(0, min(1, quantity - reserved))
            if quantity == 0:
                condition = 0
            elif (base_id, part_number) in target_inventory_keys:
                # Keep targeted destination pools at or above the catalog
                # threshold so an incoming replenishment cannot mask the
                # pooled-condition lower-bound rule.
                condition = rng.randint(minimum, 100)
            else:
                condition = rng.randint(max(0, minimum - 20), 100)
            inventory.append({
                "id": f"S{scenario_index:03d}-{base_id}-{part_number}",
                "base_id": base_id,
                "part_number": part_number,
                "quantity": quantity,
                "reserved": reserved,
                "minimum_reserve": minimum_reserve,
                "condition_pct": condition,
            })

    state = {
        "aircraft": aircraft,
        "parts": parts,
        "inventory": inventory,
        "work_orders": work_orders,
        "transfers": [],
    }
    predictions = {
        row["id"].upper(): {
            "risk_level": "LOW", "rul": None, "rul_unit": "cycles",
            "failure_probability": None, "subsystem": None, "predicted_issue": None,
            "is_synthetic": True, "model_version": GENERATOR_VERSION,
        }
        for row in aircraft
    }
    return state, predictions


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("quantile needs at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _bootstrap_ci(values: list[float], rng: random.Random) -> dict[str, float | None]:
    if not values:
        return {"lower": None, "upper": None}
    if len(values) == 1:
        return {"lower": round(values[0], 6), "upper": round(values[0], 6)}
    samples = [mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_REPLICATES)]
    samples.sort()
    return {"lower": round(_quantile(samples, 0.025), 6),
            "upper": round(_quantile(samples, 0.975), 6)}


def _summarize_policy(rows: list[dict[str, float]], policy: str) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        return [float(row[key]) for row in rows]

    summary_seed = SEED ^ sum(ord(ch) for ch in policy)
    metric_rng = random.Random(summary_seed)
    availability = values("time_weighted_availability_pct")
    available_hours = values("available_aircraft_hours")
    lost_hours = values("summed_censored_aircraft_hours_lost")
    unserved_count = values("unserved_work_orders")
    unserved_rate = values("unserved_work_order_rate_pct")
    completed = values("completed_work_orders")
    return {
        "label": POLICIES[policy],
        "mean_time_weighted_availability_pct": round(mean(availability), 4),
        "availability_pct_ci95": _bootstrap_ci(availability, metric_rng),
        "mean_available_aircraft_hours": round(mean(available_hours), 4),
        "available_aircraft_hours_ci95": _bootstrap_ci(available_hours, metric_rng),
        "mean_summed_censored_aircraft_hours_lost": round(mean(lost_hours), 4),
        "median_summed_censored_aircraft_hours_lost": round(median(lost_hours), 4),
        "summed_censored_aircraft_hours_lost_ci95": _bootstrap_ci(lost_hours, metric_rng),
        "mean_summed_censored_aircraft_days_lost": round(mean(lost_hours) / 24.0, 4),
        "median_summed_censored_aircraft_days_lost": round(median(lost_hours) / 24.0, 4),
        "mean_completed_work_orders": round(mean(completed), 4),
        "mean_unserved_work_orders": round(mean(unserved_count), 4),
        "unserved_work_order_rate_pct": round(mean(unserved_rate), 4),
        "unserved_rate_ci95": _bootstrap_ci(unserved_rate, metric_rng),
        "scenario_count": len(rows),
    }


def _paired_delta_ci(deltas: list[float], rng: random.Random) -> dict[str, Any]:
    return {
        "mean": round(mean(deltas), 6) if deltas else None,
        "ci95": _bootstrap_ci(deltas, rng),
        "paired_sample_count": len(deltas),
    }


def _scenario_policy_metrics(state: dict[str, Any], predictions: dict[str, dict],
                             plan: dict[str, Any], horizon: float) -> dict[str, float]:
    simulation = simulate_policy_from_snapshot(state, predictions, plan, horizon)
    starts, completions = _work_order_schedule(state, plan)
    work_orders = state["work_orders"]
    orders_by_aircraft: dict[str, list[dict]] = defaultdict(list)
    for order in work_orders:
        orders_by_aircraft[order["aircraft_id"]].append(order)

    # Count one capped time-to-recovery per affected aircraft. Multiple WOs on
    # the same airframe are not added twice; an unserved/unfinished order
    # censors that aircraft's recovery at the horizon.
    lost_hours = 0.0
    for rows in orders_by_aircraft.values():
        times = [completions.get(row["id"]) for row in rows]
        if any(value is None or value > horizon for value in times):
            lost_hours += horizon
        else:
            lost_hours += min(horizon, max(times, default=0.0))

    completed = sum(completions.get(row["id"], horizon + 1) <= horizon for row in work_orders)
    unserved = len(work_orders) - completed
    metrics = simulation["metrics"]
    total = len(state["aircraft"])
    if not math.isclose(
        float(metrics["available_aircraft_hours"]) + lost_hours,
        total * horizon,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise RuntimeError("synthetic affected-aircraft recovery does not reconcile to fleet availability")
    return {
        "time_weighted_availability_pct": float(metrics["time_weighted_average_availability_pct"] or 0.0),
        "available_aircraft_hours": float(metrics["available_aircraft_hours"]),
        "aircraft_downtime_hours": float(metrics["aircraft_downtime_hours"]),
        "summed_censored_aircraft_hours_lost": lost_hours,
        "completed_work_orders": float(completed),
        "unserved_work_orders": float(unserved),
        "unserved_work_order_rate_pct": (unserved / len(work_orders) * 100 if work_orders else 0.0),
        "total_aircraft": float(total),
        "scheduled_work_order_count": float(len(starts)),
    }


def _component_breakdown(state: dict[str, Any], plan: dict[str, Any], horizon: float) -> dict[str, dict]:
    """Report outcomes by each catalog part, including parts with no demand."""
    _starts, completions = _work_order_schedule(state, plan)
    allocations = {row.get("work_order_id"): row for row in plan.get("allocations", [])}
    orders_by_part: dict[str, list[dict]] = defaultdict(list)
    for order in state["work_orders"]:
        orders_by_part[str(order["required_component"]).upper()].append(order)

    breakdown = {}
    for part_number, _name, _minimum in PARTS:
        orders = orders_by_part.get(part_number, [])
        counts = {
            "work_orders": len(orders),
            "completed_by_horizon": 0,
            "unserved_at_horizon": 0,
            "local_allocations": 0,
            "remote_allocations": 0,
            "procurements": 0,
            "no_feasible_source": 0,
            "remote_feasible_candidates_considered": 0,
        }
        for order in orders:
            completed = completions.get(order["id"], horizon + 1) <= horizon
            counts["completed_by_horizon"] += int(completed)
            counts["unserved_at_horizon"] += int(not completed)
            allocation = allocations.get(order["id"], {})
            status = allocation.get("allocation_status")
            counts["local_allocations"] += int(status in {
                "PROPOSED_LOCAL_ALLOCATION", "EXISTING_LOCAL_RESOURCE_EARMARKED",
                "RECEIVED_RESOURCE_EARMARKED", "RECEIVED_RESOURCE_RESERVED",
            })
            counts["remote_allocations"] += int(status == "PROPOSED_REMOTE_TRANSFER")
            counts["procurements"] += int(status == "PROPOSED_LOCAL_PROCUREMENT")
            counts["no_feasible_source"] += int(status == "NO_FEASIBLE_SOURCE")
            counts["remote_feasible_candidates_considered"] += sum(
                bool(candidate.get("feasible")) for candidate in allocation.get("candidates", [])
            )
        breakdown[part_number] = counts
    return breakdown


def _input_scarcity_by_component(state: dict[str, Any]) -> dict[str, dict[str, int | float]]:
    """Measure system-wide stock pressure from the frozen input, before policy allocation."""
    demand: dict[str, int] = defaultdict(int)
    for order in state["work_orders"]:
        demand[str(order["required_component"]).upper()] += 1
    inventory_by_part: dict[str, int] = defaultdict(int)
    for row in state["inventory"]:
        part_number = str(row["part_number"]).upper()
        minimum = RESOURCE_CONTEXT.part_min_condition(part_number)
        if minimum is None or row.get("condition_pct") is None:
            continue
        if float(row["condition_pct"]) < minimum:
            continue
        quantity = max(0, int(row.get("quantity", 0) or 0))
        reserved = max(0, int(row.get("reserved", 0) or 0))
        reserve_floor = max(0, int(row.get("minimum_reserve", 0) or 0))
        inventory_by_part[part_number] += max(0, quantity - reserved - reserve_floor)

    result = {}
    for part_number, _name, _minimum in PARTS:
        needed = demand.get(part_number, 0)
        available = inventory_by_part.get(part_number, 0)
        result[part_number] = {
            "work_orders": needed,
            "serviceable_unreserved_units_systemwide": available,
            "competing_demand": int(needed >= 2),
            "supply_limited_competing_demand": int(needed >= 2 and 0 < available < needed),
            "no_serviceable_supply": int(needed > 0 and available == 0),
        }
    return result


def _allocation_plans(state: dict[str, Any], predictions: dict[str, dict],
                      resource_context: ResourceContext, scenario_index: int) -> dict[str, dict]:
    common = {
        "_state": state,
        "_predictions": predictions,
        "resource_context": resource_context,
        "procurement_lead_hours": PROCUREMENT_LEAD_HOURS,
    }
    return {
        "proposed": allocation_preview(source_policy="proposed", **common),
        "nearest_fcfs": allocation_preview(
            source_policy="nearest_feasible", order_policy="first_come_first_served", **common,
        ),
        "random_feasible": allocation_preview(
            source_policy="random_feasible", _rng=random.Random(SEED + 1_000_003 * scenario_index), **common,
        ),
        "local_only_procurement": allocation_preview(
            source_policy="local_only_procurement", **common,
        ),
    }


def run_scale_simulation(*, scenario_count: int = SCENARIO_COUNT,
                         seed: int = SEED,
                         horizon_hours: float = HORIZON_HOURS) -> dict[str, Any]:
    """Run paired policy simulations over deterministic synthetic snapshots."""
    if scenario_count != SCENARIO_COUNT:
        raise ValueError(f"scenario_count is fixed at {SCENARIO_COUNT} for report comparability")
    if seed != SEED:
        raise ValueError(f"seed is fixed at {SEED} for report comparability")
    if horizon_hours != HORIZON_HOURS:
        raise ValueError(f"horizon_hours is fixed at {HORIZON_HOURS} for report comparability")

    policy_rows: dict[str, list[dict[str, float]]] = {policy: [] for policy in POLICIES}
    component_totals = {
        policy: {part_number: {key: 0 for key in (
            "work_orders", "completed_by_horizon", "unserved_at_horizon", "local_allocations",
            "remote_allocations", "procurements", "no_feasible_source",
            "remote_feasible_candidates_considered", "scenarios_with_demand",
        )} for part_number, _name, _minimum in PARTS}
        for policy in POLICIES
    }
    scenario_results = []
    scarcity_totals = {
        part_number: {
            "scenarios_with_demand": 0,
            "scenarios_with_competing_demand": 0,
            "scenarios_with_supply_limited_competing_demand": 0,
            "scenarios_with_no_serviceable_supply": 0,
            "serviceable_unreserved_units_systemwide_sum": 0,
        }
        for part_number, _name, _minimum in PARTS
    }
    scenario_fingerprint = hashlib.sha256()
    resource_context = RESOURCE_CONTEXT

    for scenario_index in range(SCENARIO_COUNT):
        state, predictions = _generate_scenario(scenario_index)
        plans = _allocation_plans(state, predictions, resource_context, scenario_index)
        input_hash = hashlib.sha256(_canonical_json({
            "state": state,
            "predictions": predictions,
            "resource_context": {
                "bases": resource_context.bases,
                "parts": resource_context.parts,
                "routes": resource_context.routes,
            },
        })).hexdigest()
        scenario_fingerprint.update(bytes.fromhex(input_hash))

        input_scarcity = _input_scarcity_by_component(state)
        for part_number, counts in input_scarcity.items():
            totals = scarcity_totals[part_number]
            totals["scenarios_with_demand"] += int(counts["work_orders"] > 0)
            totals["scenarios_with_competing_demand"] += counts["competing_demand"]
            totals["scenarios_with_supply_limited_competing_demand"] += counts[
                "supply_limited_competing_demand"]
            totals["scenarios_with_no_serviceable_supply"] += counts["no_serviceable_supply"]
            totals["serviceable_unreserved_units_systemwide_sum"] += counts[
                "serviceable_unreserved_units_systemwide"]

        metrics_by_policy = {}
        component_results = {}
        for policy in POLICIES:
            metrics = _scenario_policy_metrics(state, predictions, plans[policy], horizon_hours)
            policy_rows[policy].append(metrics)
            metrics_by_policy[policy] = {key: round(value, 8) for key, value in metrics.items()}
            components = _component_breakdown(state, plans[policy], horizon_hours)
            component_results[policy] = components
            for part_number, values in components.items():
                totals = component_totals[policy][part_number]
                for key in totals:
                    if key == "scenarios_with_demand":
                        continue
                    totals[key] += values[key]
                totals["scenarios_with_demand"] += int(values["work_orders"] > 0)
        scenario_results.append({
            "scenario_index": scenario_index + 1,
            "scenario_fingerprint": input_hash,
            "aircraft_count": AIRCRAFT_COUNT,
            "active_work_order_count": ACTIVE_WORK_ORDERS,
            "policy_metrics": metrics_by_policy,
            "component_outcomes": component_results,
            "input_scarcity": input_scarcity,
        })

    summaries = {policy: _summarize_policy(rows, policy)
                 for policy, rows in policy_rows.items()}
    comparison = {"reference_policy": "proposed", "paired_deltas_vs_proposed": {}}
    for policy_index, policy in enumerate(POLICIES):
        if policy == "proposed":
            continue
        comparison["paired_deltas_vs_proposed"][policy] = {
            "time_weighted_availability_pct_points": _paired_delta_ci(
                [other["time_weighted_availability_pct"] - reference["time_weighted_availability_pct"]
                 for other, reference in zip(policy_rows[policy], policy_rows["proposed"])],
                random.Random(SEED + 2000 + policy_index),
            ),
            "summed_censored_aircraft_hours_lost": _paired_delta_ci(
                [other["summed_censored_aircraft_hours_lost"]
                 - reference["summed_censored_aircraft_hours_lost"]
                 for other, reference in zip(policy_rows[policy], policy_rows["proposed"])],
                random.Random(SEED + 3000 + policy_index),
            ),
            "unserved_work_order_rate_pct_points": _paired_delta_ci(
                [other["unserved_work_order_rate_pct"] - reference["unserved_work_order_rate_pct"]
                 for other, reference in zip(policy_rows[policy], policy_rows["proposed"])],
                random.Random(SEED + 4000 + policy_index),
            ),
        }

    config = {
        "generator_version": GENERATOR_VERSION,
        "scenario_count": SCENARIO_COUNT,
        "seed": SEED,
        "aircraft_count": AIRCRAFT_COUNT,
        "active_work_orders": ACTIVE_WORK_ORDERS,
        "horizon_hours": HORIZON_HOURS,
        "procurement_lead_hours": PROCUREMENT_LEAD_HOURS,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bases": resource_context.bases,
        "parts": resource_context.parts,
        "routes": resource_context.routes,
    }
    config_fingerprint = hashlib.sha256(_canonical_json(config)).hexdigest()
    scarcity_summary = {
        part_number: {
            **totals,
            "mean_serviceable_unreserved_units_systemwide": round(
                totals["serviceable_unreserved_units_systemwide_sum"] / SCENARIO_COUNT, 4,
            ),
        }
        for part_number, totals in scarcity_totals.items()
    }
    return {
        "evaluation_type": "deterministic_synthetic_simulation",
        "simulated": True,
        "real_operational_performance_claimed": False,
        "scenario_count": SCENARIO_COUNT,
        "seed": SEED,
        "horizon_hours": HORIZON_HOURS,
        "horizon_unit": "hours",
        "scenario_fingerprint": scenario_fingerprint.hexdigest(),
        "config_fingerprint": config_fingerprint,
        "generator_version": GENERATOR_VERSION,
        "bootstrap_method": "percentile bootstrap over scenario units; paired deltas resample paired scenario differences",
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "policies": summaries,
        "comparison": comparison,
        "component_summary": component_totals,
        "input_scarcity_summary": scarcity_summary,
        "scenario_results": scenario_results,
        "assumptions": [
            "All scenarios and operational values are synthetic; this result does not measure real fleet performance.",
            "Each scenario has 40 synthetic aircraft across 6 bases, 8 catalog components, and 12 concurrent work orders; six components each have two simultaneous requests and two catalog components have no demand.",
            "Every policy receives the same generated aircraft, work orders, inventory, condition, reserve, catalog, and route snapshot.",
            "The production policy uses the existing recommendation ranker and shared allocation ledger; nearest-FCFS changes source ordering and work-order order only; random-feasible samples only the same shared hard-filtered feasible candidates using a fixed seed.",
            "Local-only/procurement never selects remote donors. The same external procurement fallback is available to other policies only after the shared search finds no feasible source; procurement has a fixed 24-hour lead, meets catalog condition, and replenishes enough to preserve minimum reserve.",
            "Recovery is modeled as transfer/procurement lead plus the work order's planned repair duration. Work orders unfinished by 48 hours are censored at the horizon; affected aircraft are counted once, with multiple work orders represented by the latest completion.",
            "The readiness simulator treats synthetic repair completion as restoring an affected airframe under a fixed LOW-risk scenario prediction. This is an evaluation assumption, not a claim about FD001 predictions or a live maintenance completion.",
            "RUL is not used as a time input; cycle counts are not converted to hours.",
            "Bootstrap intervals describe variation across these generated scenarios only and do not establish external validity or calibrated uncertainty.",
        ],
    }


def render_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Synthetic fleet-scale allocation evaluation",
        "",
        f"Scenarios: {result['scenario_count']} · seed: {result['seed']} · horizon: {result['horizon_hours']} {result['horizon_unit']}",
        f"Scenario fingerprint: `{result['scenario_fingerprint']}`",
        f"Configuration fingerprint: `{result['config_fingerprint']}`",
        "",
        "All results are deterministic simulations over synthetic fleets and are not real operational performance.",
        "",
        "| Policy | Mean availability % (95% CI) | Mean aircraft-days lost (median) | Mean unserved WOs (rate) |",
        "|---|---:|---:|---:|",
    ]
    for policy, summary in result["policies"].items():
        ci = summary["availability_pct_ci95"]
        lines.append(
            f"| {summary['label']} | {summary['mean_time_weighted_availability_pct']:.2f} "
            f"({ci['lower']:.2f}–{ci['upper']:.2f}) | "
            f"{summary['mean_summed_censored_aircraft_days_lost']:.2f} "
            f"({summary['median_summed_censored_aircraft_days_lost']:.2f}) | "
            f"{summary['mean_unserved_work_orders']:.2f} "
            f"({summary['unserved_work_order_rate_pct']:.2f}%) |"
        )
    lines.extend(["", "## Component-level demand and scarcity", "",
                  "Counts are totals across all generated scenarios, by component and policy; all values are synthetic.",
                  "", "| Policy | Component | Requested WOs | Completed by horizon | Unserved at horizon | No feasible source |",
                  "|---|---|---:|---:|---:|---:|"])
    for policy, components in result["component_summary"].items():
        label = result["policies"][policy]["label"]
        for part_number, counts in components.items():
            lines.append(
                f"| {label} | {part_number} | {counts['work_orders']} | "
                f"{counts['completed_by_horizon']} | {counts['unserved_at_horizon']} | "
                f"{counts['no_feasible_source']} |"
            )
    lines.extend(["", "## Input stock scarcity", "",
                  "Before policy allocation, system-wide serviceable unreserved units are summed across all six bases after reserved quantity, minimum reserve, and catalog condition checks. This total is a supply-pressure diagnostic, not a guarantee that stock is route-reachable for every request.",
                  "", "| Component | Scenarios with paired demand | Paired demand with some but insufficient units | Scenarios with no serviceable supply | Mean system-wide serviceable units |",
                  "|---|---:|---:|---:|---:|"])
    for part_number, counts in result["input_scarcity_summary"].items():
        lines.append(
            f"| {part_number} | {counts['scenarios_with_competing_demand']} | "
            f"{counts['scenarios_with_supply_limited_competing_demand']} | "
            f"{counts['scenarios_with_no_serviceable_supply']} | "
            f"{counts['mean_serviceable_unreserved_units_systemwide']:.2f} |"
        )
    lines.extend(["", "## Assumptions and limits", ""])
    lines.extend(f"- {assumption}" for assumption in result["assumptions"])
    lines.append("")
    return "\n".join(lines)


def write_reports(output_dir: Path | None = None) -> tuple[Path, Path]:
    result = run_scale_simulation()
    directory = output_dir or RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "scale_simulation.json"
    markdown_path = directory / "scale_simulation.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8")
    markdown_path.write_text(render_markdown_report(result), encoding="utf-8")
    return json_path, markdown_path


if __name__ == "__main__":
    paths = write_reports()
    print(f"Wrote {paths[0]}")
    print(f"Wrote {paths[1]}")
