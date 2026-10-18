"""Compare the recommendation policy with a nearest-feasible baseline.

This module is deliberately separate from live approval and transfer flows.
All scenarios are deterministic simulations over the same hard-filtered
candidate set. The seeded scenario obtains that set from the production
resource search; the controlled scenarios use small, explicitly simulated
search results to exercise ties and empty-feasible-set behavior.

Run from ``backend`` with ``python -m app.evaluation.recommendation_baseline``.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from ..repositories import WorkOrderRepository, reset
from ..services import recommendation_service, resource_service


def _prepare_feasible(search_result: dict[str, Any], work_order: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the live recovery and tie-break helpers to already-feasible rows."""
    prepared = []
    for candidate in search_result.get("candidates", []):
        row = dict(candidate)
        row["feasible"] = True
        row["expected_downtime_hours"] = recommendation_service.expected_downtime_hours(row, work_order)
        row["donor_impact"] = recommendation_service._donor_impact(row)
        prepared.append(row)
    return prepared


def compare_search_result(
    scenario: str,
    work_order: dict[str, Any],
    search_result: dict[str, Any],
    *,
    simulated: bool,
) -> dict[str, Any]:
    """Compare both policies on the exact same pre-filtered search result.

    The recommendation side uses the production ranker. The baseline sorts
    only the same feasible rows by distance, then ETA and base id. Rejected
    rows remain visible in the result and are never considered by either.
    """
    feasible = _prepare_feasible(search_result, work_order)
    ranked = recommendation_service.rank_candidates(feasible, work_order, urgency=0.0)
    ranked_again = recommendation_service.rank_candidates(
        _prepare_feasible(search_result, work_order), work_order, urgency=0.0
    )
    baseline = sorted(
        feasible,
        key=lambda row: (
            float(row.get("distance_km") or 0.0),
            float(row.get("eta_hours") or 0.0),
            str(row.get("base_id") or ""),
        ),
    )
    recommended = ranked[0] if ranked else None
    nearest = baseline[0] if baseline else None
    rejected = list(search_result.get("infeasible", []))

    def option(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "source_base": row["base_id"],
            "expected_recovery_hours": row["expected_downtime_hours"],
            # One target aircraft is grounded in the scenario; this is an
            # aircraft-hours fleet-downtime estimate. No donor outage is inferred.
            "estimated_target_aircraft_downtime_hours": row["expected_downtime_hours"],
            "estimated_fleet_downtime_aircraft_hours": row["expected_downtime_hours"],
            "distance_km": row.get("distance_km"),
            "eta_hours": row.get("eta_hours"),
            "donor_impact": row.get("donor_impact"),
            "donor_units_after_transfer": row.get("donor_reserve_after_transfer"),
            "donor_minimum_reserve": row.get("minimum_reserve"),
            "explanation": (
                row.get("ranking_explanation")
                if row is recommended
                else "Nearest feasible source by distance; ties break by ETA then base id"
            ),
        }

    recommended_option = option(recommended)
    baseline_option = option(nearest)
    if not recommended_option:
        outcome = "NO_FEASIBLE_SOURCE"
        recovery_delta = None
    else:
        recovery_delta = round(
            baseline_option["expected_recovery_hours"] - recommended_option["expected_recovery_hours"], 1
        )
        outcome = "EQUAL_RECOVERY" if recovery_delta == 0 else (
            "RECOMMENDATION_FASTER" if recovery_delta > 0 else "BASELINE_FASTER"
        )

    return {
        "scenario": scenario,
        "scenario_type": "simulated",
        "simulated": simulated,
        "comparison_inputs": "same hard-filtered feasible candidate set",
        "feasible_source_count": len(feasible),
        "infeasible_source_count": len(rejected),
        "infeasible_reasons": dict(sorted(Counter(str(row.get("reason")) for row in rejected).items())),
        "rejected_sources": [
            {"base_id": row.get("base_id"), "reason": row.get("reason")}
            for row in sorted(rejected, key=lambda row: str(row.get("base_id") or ""))
        ],
        "recommendation_policy": recommended_option,
        "nearest_feasible_baseline": baseline_option,
        "recommendation_selection_stable": (
            [row["base_id"] for row in ranked] == [row["base_id"] for row in ranked_again]
        ),
        "selected_infeasible_options": {"recommendation": 0, "baseline": 0},
        "baseline_minus_recommendation_recovery_hours": recovery_delta,
        "outcome": outcome,
        "selected_reserve_violations": {
            "recommendation": int(bool(recommended and recommended.get("donor_impact") == recommendation_service.IMPACT_HIGH)),
            "baseline": int(bool(nearest and nearest.get("donor_impact") == recommendation_service.IMPACT_HIGH)),
        },
        "assumptions": [
            "Candidate feasibility, including stock, serviceable condition and donor minimum reserve, is decided before ranking.",
            "Recovery estimate is transfer ETA plus the work order's planned repair duration.",
            "Fleet downtime is reported as aircraft-hours for the single target airframe; donor inventory is reported separately.",
            "The nearest-feasible baseline minimizes distance and uses ETA then base id for deterministic ties.",
        ],
    }


def run_evaluation() -> dict[str, Any]:
    """Reset to the seed state, then compare seeded and controlled simulations."""
    reset()
    work_order = WorkOrderRepository.get("WO-1042")
    if work_order is None:
        raise RuntimeError("seeded demo work order WO-1042 is missing")
    seeded_search = resource_service.search(work_order["id"])
    seeded = compare_search_result("seeded_A17_HP-204", work_order, seeded_search, simulated=True)

    # Controlled, synthetic cases share the same candidate-set interface as
    # live search. The explicit rejection is retained and excluded by both.
    controlled_wo = {**work_order, "estimated_repair_hours": 6.0}
    tie_search = {
        "candidates": [
            {"base_id": "near", "distance_km": 100, "eta_hours": 2.0,
             "donor_reserve_after_transfer": 1, "minimum_reserve": 1},
            {"base_id": "far", "distance_km": 200, "eta_hours": 2.0,
             "donor_reserve_after_transfer": 1, "minimum_reserve": 0},
        ],
        "infeasible": [{"base_id": "reserved", "reason": resource_service.INFEASIBLE_RESERVE}],
    }
    tie_case = compare_search_result(
        "controlled_equal_recovery_distance_tradeoff", controlled_wo, tie_search, simulated=True
    )
    scenarios = [seeded, tie_case]

    # A nearest-in-distance donor is reserve-blocked, while a farther
    # feasible source has a shorter simulated route ETA. Both policies see
    # the same remaining feasible rows; only the recommendation ranks by ETA.
    recovery_tradeoff = compare_search_result(
        "controlled_nearest_reserve_rejected_farther_faster", controlled_wo,
        {"candidates": [
            {"base_id": "near", "distance_km": 100, "eta_hours": 5.0,
             "donor_reserve_after_transfer": 0, "minimum_reserve": 0},
            {"base_id": "far", "distance_km": 200, "eta_hours": 2.5,
             "donor_reserve_after_transfer": 1, "minimum_reserve": 0},
        ], "infeasible": [
            {"base_id": "closest", "reason": resource_service.INFEASIBLE_RESERVE},
        ]},
        simulated=True,
    )
    scenarios.append(recovery_tradeoff)

    empty_case = compare_search_result(
        "controlled_no_feasible_source", controlled_wo,
        {"candidates": [], "infeasible": [
            {"base_id": "near", "reason": resource_service.INFEASIBLE_NO_STOCK},
            {"base_id": "far", "reason": resource_service.INFEASIBLE_RESERVE},
        ]},
        simulated=True,
    )
    scenarios.append(empty_case)

    return {
        "evaluation": "recommendation_vs_nearest_feasible_baseline",
        "evaluation_type": "deterministic_simulation",
        "real_operational_performance_claimed": False,
        "scenarios": scenarios,
        "summary": {
            "scenario_count": len(scenarios),
            "recommendation_faster_count": sum(s["outcome"] == "RECOMMENDATION_FASTER" for s in scenarios),
            "equal_recovery_count": sum(s["outcome"] == "EQUAL_RECOVERY" for s in scenarios),
            "baseline_faster_count": sum(s["outcome"] == "BASELINE_FASTER" for s in scenarios),
            "no_feasible_source_count": sum(s["outcome"] == "NO_FEASIBLE_SOURCE" for s in scenarios),
        },
    }


def main() -> None:
    print(json.dumps(run_evaluation(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
