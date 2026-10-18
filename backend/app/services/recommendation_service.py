"""Recommendation service (spec sections 8-12).

Architecture is deliberately optimiser-ready. `evaluate_candidates()` produces
a fully-populated, costed candidate set; `rank_candidates()` then orders it
with a transparent rule-based score. Replacing that score with an OR-Tools
model later means changing one function — the search, feasibility set,
expected-downtime model and explanations stay exactly as they are.

Objective: MINIMISE EXPECTED FLEET DOWNTIME, equivalently MAXIMISE fleet
availability. Urgency sharpens the penalty on transport time, so the engine
transparently trades off "slow but keeps the donor healthy" against "fast and
the airframe flies sooner".
"""

from __future__ import annotations

from ..data import BASES, distance_km, eta_hours
from ..domain.enums import PRIORITY_ORDER
from ..repositories import AircraftRepository, WorkOrderRepository
from . import audit_service
from .ml import get_provider, predict_validated
from .resource_service import search, urgency_weight
from .availability_service import fleet_overview

# Impact bands reported per candidate. Kept coarse and explainable rather than
# pretending to precision the POC cannot support.
IMPACT_VERY_LOW = "VERY LOW"
IMPACT_LOW = "LOW"
IMPACT_MODERATE = "MODERATE"
IMPACT_HIGH = "HIGH"


def _impact_band(value: float, thresholds: tuple[float, float, float]) -> str:
    low, moderate, high = thresholds
    if value <= low:
        return IMPACT_VERY_LOW
    if value <= moderate:
        return IMPACT_LOW
    if value <= high:
        return IMPACT_MODERATE
    return IMPACT_HIGH


def expected_downtime_hours(candidate: dict, work_order: dict) -> float:
    """Expected recovery time from transfer ETA and planned repair duration.

    Component condition is surfaced as a supporting factor, but the POC has no
    measured evidence that condition changes the planned repair duration.
    """
    repair = float(work_order.get("estimated_repair_hours") or 4.0)
    eta = float(candidate.get("eta_hours") or 0.0)
    return round(eta + repair, 1)


def evaluate_candidates(work_order_id: str) -> dict:
    """Search, cost and rank candidates for a work order."""
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        return {"work_order_id": work_order_id, "error": "unknown work order",
                "candidates": [], "recommended": None}

    pred = predict_validated(get_provider(), work_order["aircraft_id"])
    found = search(work_order_id)
    baseline = fleet_overview()
    baseline_downtime = baseline["total"] * (100 - baseline["availability_pct"]) / 100.0
    evaluation = evaluate_candidates_from_snapshot(
        work_order, pred, found, baseline_downtime=baseline_downtime,
    )
    return evaluation


def record_recommendation_evaluation(work_order_id: str, evaluation: dict,
                                     actor: str = "system") -> dict:
    """Record an explicit recommendation decision/evaluation outside GET reads."""
    return audit_service.recommendation_generated(
        work_order_id, len(evaluation.get("candidates", [])),
        evaluation.get("recommended"), actor=actor,
    )


def evaluate_candidates_from_snapshot(work_order: dict, prediction: dict,
                                      found: dict, *, baseline_downtime: float = 0.0) -> dict:
    """Purely score a work order against precomputed prediction/search inputs.

    This keeps scoring, explanations, and ranking identical between live
    single-work-order recommendations and read-only shared-stock planning.
    It deliberately does not query providers, repositories, or append audit.
    """
    work_order_id = str(work_order.get("id") or found.get("work_order_id") or "")
    aircraft_id = work_order.get("aircraft_id")
    risk_level = prediction.get("risk_level")
    rul = prediction.get("rul")
    rul_unit = prediction.get("rul_unit")
    component = found.get("required_component")
    urgency = urgency_weight(work_order, risk_level, rul)

    scored: list[dict] = []
    for cand in found.get("candidates", []):
        downtime = expected_downtime_hours(cand, work_order)
        donor_impact_value = _donor_impact(cand)
        fleet_impact = _fleet_impact(cand, downtime, work_order, baseline_downtime)
        score = _score(cand, work_order, downtime, donor_impact_value, urgency, rul)

        scored.append({
            **cand,
            "feasible": True,
            "source_base": cand["base_id"],
            "destination_base": found["home_base"],
            "score": score,
            "expected_downtime_hours": downtime,
            "donor_impact": donor_impact_value,
            "fleet_impact": fleet_impact,
        })

    ranked = rank_candidates(scored, work_order, urgency)

    for row in ranked:
        row["reasons"] = _explain(row, work_order, risk_level, urgency)

    rejected = [
        {
            "base_id": row["base_id"],
            "source_base": row["base_id"],
            "destination_base": found["home_base"],
            "feasible": False,
            "score": None,
            "status": "REJECTED",
            "reason": row["reason"],
            "detail": row["detail"],
        }
        for row in found.get("infeasible", [])
    ]

    local = found.get("local_available", 0)
    recommended = ranked[0] if ranked else None

    return {
        "work_order_id": work_order_id,
        "aircraft_id": aircraft_id,
        "home_base": found.get("home_base"),
        "required_component": component,
        "part_name": found.get("part_name"),
        "min_condition_pct": found.get("min_condition_pct"),
        "local_available": local,
        "urgency": urgency,
        "risk_level": risk_level,
        "rul": rul,
        "rul_unit": rul_unit,
        "priority": work_order.get("priority"),
        "estimated_repair_hours": work_order.get("estimated_repair_hours"),
        "candidates": ranked,
        "rejected": rejected,
        "infeasible_candidates": rejected,
        "recommended": recommended,
        "objective": "MINIMIZE_EXPECTED_FLEET_DOWNTIME",
        "ranking_policy": "minimum expected recovery hours; ties use donor impact, ETA, distance, then base id",
        "scoring": "supporting comparison score; cannot override expected downtime ranking",
    }


def _donor_impact(candidate: dict) -> str:
    """How much does the donor base lose by giving this unit up?

    Judged against the donor's own minimum reserve, not in absolute terms. A
    base with no reserve policy that empties a line has taken on little
    exposure; a base pushed *below* its minimum reserve has taken on a lot.
    """
    after = int(candidate.get("donor_reserve_after_transfer", 0))
    minimum = int(candidate.get("minimum_reserve", 0))
    if after < minimum:
        return IMPACT_HIGH          # reserve policy violated
    if minimum > 0 and after == minimum:
        return IMPACT_MODERATE       # sitting exactly on the reserve line
    if after <= 0:
        return IMPACT_LOW            # no reserve required, nothing to breach
    return IMPACT_LOW


def _fleet_impact(candidate: dict, downtime: float, work_order: dict,
                  baseline_downtime: float) -> str:
    """Effect on fleet-wide availability if this action is taken."""
    # One airframe returns to service after `downtime`; urgency makes a long
    # grounding more costly to the fleet.
    urgency = urgency_weight(work_order)
    weighted = downtime * (1 + urgency * 0.1)
    if weighted <= 4:
        return IMPACT_LOW
    if weighted <= 9:
        return IMPACT_MODERATE
    if weighted <= 16:
        return IMPACT_HIGH
    return "SEVERE"


# Score weights. Each penalty is normalised into a bounded range before being
# applied, so a single extreme factor can never push the total to zero and
# flatten the ranking. Weights sum to 100 at the top of the scale.
WEIGHT_ETA = 30.0
WEIGHT_DISTANCE = 15.0
WEIGHT_DOWNTIME = 35.0
DURATION_CEILING_ETA_H = 12.0
DURATION_CEILING_DOWNTIME_H = 24.0
DISTANCE_CEILING_KM = 500.0

DONOR_IMPACT_PENALTY = {
    "HIGH": 25.0,
    "MODERATE": 10.0,
    "LOW": 3.0,
}


def _score(candidate: dict, work_order: dict, downtime: float,
           donor_impact_value: str, urgency: float, rul: float | None) -> float:
    """Transparent weighted score, higher is better.

    Every term maps to one of the twelve factors the spec lists. Kept additive
    and bounded so an optimiser can replace this function wholesale while the
    surrounding contract (inputs, factors, explanation) stays identical.
    """
    eta = float(candidate.get("eta_hours") or 0.0)
    distance = float(candidate.get("distance_km") or 0.0)
    condition = int(candidate.get("condition_pct") or 0)
    min_cond = int(candidate.get("min_condition_pct") or 0)
    quantity = int(candidate.get("quantity_available") or 0)

    # 1-3. Urgency, risk and required-by time amplify transport cost.
    eta_ratio = min(1.0, eta / DURATION_CEILING_ETA_H)
    eta_penalty = WEIGHT_ETA * eta_ratio * (0.5 + urgency / 10.0)

    # 6-7. Distance is a secondary tiebreak, capped lower than ETA.
    distance_penalty = WEIGHT_DISTANCE * min(1.0, distance / DISTANCE_CEILING_KM)

    # 10-12. Expected downtime is the primary objective.
    downtime_penalty = WEIGHT_DOWNTIME * min(1.0, downtime / DURATION_CEILING_DOWNTIME_H)

    # 8-9. Donor stock position and reserve policy.
    donor_penalty = DONOR_IMPACT_PENALTY.get(donor_impact_value, 0.0)

    # 4-5. Availability depth and condition are bounded bonuses.
    availability_bonus = min(quantity, 2) * 2.5
    condition_bonus = max(0.0, min(100, condition - min_cond)) / 100.0 * 8.0

    score = (
        100.0
        - eta_penalty
        - distance_penalty
        - downtime_penalty
        - donor_penalty
        + availability_bonus
        + condition_bonus
    )
    return round(max(0.0, min(100.0, score)), 1)


def rank_candidates(scored: list[dict], work_order: dict, urgency: float) -> list[dict]:
    """Minimize expected aircraft downtime; apply deterministic tie breaks.

    Feasibility is decided by resource search before ranking. Score remains a
    supporting comparison signal for the UI and audit, never an override of
    the stated downtime objective.
    """
    def key(row: dict):
        donor_impact_order = {IMPACT_VERY_LOW: 0, IMPACT_LOW: 1,
                              IMPACT_MODERATE: 2, IMPACT_HIGH: 3}
        return (
            row["expected_downtime_hours"],
            donor_impact_order.get(row.get("donor_impact"), 4),
            row["eta_hours"],
            float(row.get("distance_km") or 0),
            row["base_id"],
        )
    ranked = sorted((row for row in scored if row.get("feasible", True)), key=key)
    for index, row in enumerate(ranked):
        row["feasible"] = True
        row["rank"] = index + 1
        if index == 0:
            row.setdefault("ranking_explanation", "Lowest expected aircraft downtime among feasible options")
        else:
            row.setdefault("ranking_explanation", "Ranked by expected downtime, then ETA, distance, and source base")
    return ranked


def _explain(candidate: dict, work_order: dict, risk_level: str | None,
             urgency: float) -> list[str]:
    """Why this candidate, in plain language (spec section 11)."""
    reasons = [
        f"Aircraft {work_order['aircraft_id']} is {str(risk_level or 'at risk').lower()} priority "
        f"({work_order.get('priority')})",
        f"{candidate['part_number']} is available at {candidate['base_name']} "
        f"({candidate['quantity_available']} unit(s) transferable)",
    ]

    min_cond = candidate.get("min_condition_pct") or 0
    reasons.append(
        f"Component condition {candidate['condition_pct']}% satisfies the {min_cond}% minimum"
    )

    reasons.append(
        f"{candidate['eta_hours']}-hour transport over {candidate['distance_km']} km "
        f"(expected downtime {candidate['expected_downtime_hours']}h)"
    )

    minimum = candidate.get("minimum_reserve", 0)
    after = candidate.get("donor_reserve_after_transfer", 0)
    impact = candidate.get("donor_impact")

    if impact == IMPACT_HIGH:
        reasons.append(
            f"WARNING: taking this unit leaves {candidate['base_name']} below its minimum "
            f"reserve of {minimum} — would require an authorised override"
        )
    elif minimum > 0 and after == minimum:
        reasons.append(
            f"{candidate['base_name']} falls exactly to its minimum reserve of {minimum} — accept with care"
        )
    elif minimum == 0:
        reasons.append(
            f"{candidate['base_name']} holds no reserve requirement, so no policy is breached"
        )
    else:
        reasons.append(
            f"Donor base retains {after} unit(s), above its minimum reserve of {minimum}"
        )

    reasons.append(f"Estimated donor-base impact: {candidate['donor_impact']}")
    reasons.append(f"Estimated fleet impact: {candidate['fleet_impact']}")

    return reasons
