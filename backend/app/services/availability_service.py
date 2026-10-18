"""Fleet availability service — the north-star metric (spec section 13).

Availability is CALCULATED, never stored:

    fleet_availability = available_aircraft / total_aircraft

Only `AVAILABLE` counts as flyable. Because aircraft state is recomputed from
the active work order plus the ML risk band, any workflow transition updates
availability automatically — there is no separate number to keep in sync.
"""

from __future__ import annotations

from ..data import BASES
from ..domain import knowledge
from ..domain.enums import AircraftStatus, WorkOrderStatus
from ..repositories import AircraftRepository, WorkOrderRepository
from ..repositories.maintenance_repository import OPEN_WORK_ORDER_STATUSES
from .ml import get_provider, predict_validated


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def classify_aircraft(aircraft_id: str, ml_risk: str | None = None) -> str:
    """Derive an airframe's operational state from its open work order.

    Precedence matters:

    1. An in-progress repair grounds an aircraft even if the model is happy.
    2. Waiting on a part means not available, whatever the numbers say.
    3. A *recently serviced* airframe is AVAILABLE. This is what closes the
       loop: a risk band describes a predicted future problem, so it must not
       permanently deny airworthiness after the maintenance has been done.
    4. Otherwise fall back to the risk band.
    """
    work_orders = WorkOrderRepository.list_by_aircraft(aircraft_id)
    prediction: dict = {"risk_level": ml_risk}
    if any(w["status"] == WorkOrderStatus.COMPLETED.value for w in work_orders):
        prediction = predict_validated(get_provider(), aircraft_id)
        if ml_risk is not None:
            prediction["risk_level"] = ml_risk
    return classify_aircraft_from_snapshot(
        aircraft_id, work_orders, prediction,
    )


def classify_aircraft_from_snapshot(aircraft_id: str, work_orders: list[dict],
                                    prediction: dict) -> str:
    """Purely classify a supplied aircraft/work-order/prediction snapshot.

    Used by read-only simulations so hypothetical completions share the live
    availability rules without reading or mutating repositories.
    """
    open_wos = [w for w in work_orders if w["status"] in OPEN_WORK_ORDER_STATUSES]
    statuses = {w["status"] for w in open_wos}

    if WorkOrderStatus.IN_PROGRESS.value in statuses:
        return AircraftStatus.MAINTENANCE.value
    if WorkOrderStatus.WAITING_FOR_RESOURCE.value in statuses:
        return AircraftStatus.WAITING_FOR_PART.value

    if _recently_serviced_for_prediction(work_orders, prediction):
        return AircraftStatus.AVAILABLE.value

    ml_risk = prediction.get("risk_level")
    if ml_risk in ("HIGH", "CRITICAL"):
        return AircraftStatus.AT_RISK.value
    if ml_risk == "MEDIUM":
        return AircraftStatus.DEGRADED.value
    return AircraftStatus.AVAILABLE.value


def _recently_serviced(aircraft_id: str, work_orders: list[dict]) -> bool:
    """True when a completed work order addressed the currently-predicted issue."""
    from ..domain import knowledge
    from .ml import get_provider

    pred = predict_validated(get_provider(), aircraft_id)
    return _recently_serviced_for_prediction(work_orders, pred)


def _recently_serviced_for_prediction(work_orders: list[dict], pred: dict) -> bool:
    completed = [w for w in work_orders if w["status"] == WorkOrderStatus.COMPLETED.value]
    if not completed:
        return False
    res = knowledge.resolve(pred.get("subsystem"), pred.get("predicted_issue"))
    if not res.candidate_components:
        return False

    serviced = {str(w.get("required_component") or "").upper() for w in completed}
    return bool(serviced.intersection(c.upper() for c in res.candidate_components))


def sync_aircraft_states() -> list[dict]:
    """Recompute every aircraft state and persist changes.

    Returns the aircraft whose state actually moved, so callers can audit the
    transition (e.g. returned to service).
    """
    provider = get_provider()
    changed: list[dict] = []
    for ac in AircraftRepository.list_all():
        pred = predict_validated(provider, ac["id"])
        desired = classify_aircraft(ac["id"], pred.get("risk_level"))
        if ac.get("status") != desired:
            AircraftRepository.update(ac["id"], status=desired)
            changed.append({"id": ac["id"], "from": ac.get("status"), "to": desired})
    return changed


def fleet_overview() -> dict:
    """Fleet-wide availability plus the same figures per base."""
    provider = get_provider()
    aircraft = AircraftRepository.list_all()
    total = len(aircraft)

    available = sum(1 for a in aircraft if a.get("status") == AircraftStatus.AVAILABLE.value)
    maintenance = sum(1 for a in aircraft if a.get("status") == AircraftStatus.MAINTENANCE.value)
    waiting = sum(1 for a in aircraft if a.get("status") == AircraftStatus.WAITING_FOR_PART.value)
    at_risk = sum(
        1 for a in aircraft
        if a.get("status") in (AircraftStatus.AT_RISK.value, AircraftStatus.DEGRADED.value)
    )
    unavailable = sum(
        1 for a in aircraft
        if a.get("status") == AircraftStatus.UNAVAILABLE.value
    )

    high_risk = sum(
        1 for a in aircraft
        if (predict_validated(provider, a["id"]).get("risk_level") or "LOW") in ("HIGH", "CRITICAL")
    )

    bases = []
    for b in BASES:
        held = [a for a in aircraft if a["base_id"] == b["id"]]
        av = sum(1 for a in held if a.get("status") == AircraftStatus.AVAILABLE.value)
        bases.append({
            "id": b["id"],
            "name": b["name"],
            "aircraft_count": len(held),
            "available": av,
            "availability_pct": _pct(av, len(held)),
            "at_risk": sum(1 for a in held if a.get("status") in (AircraftStatus.AT_RISK.value, AircraftStatus.DEGRADED.value)),
            "maintenance": sum(1 for a in held if a.get("status") == AircraftStatus.MAINTENANCE.value),
            "waiting_for_part": sum(1 for a in held if a.get("status") == AircraftStatus.WAITING_FOR_PART.value),
        })

    return {
        "total": total,
        "available": available,
        "maintenance": maintenance,
        "waiting_for_part": waiting,
        "at_risk": at_risk,
        "unavailable": unavailable,
        "high_risk": high_risk,
        "availability_pct": _pct(available, total),
        "bases": bases,
        # Provenance, so the UI can be honest about what the number means.
        "calculation": "available_aircraft / total_aircraft",
        "generated_by": "availability_service",
    }


def base_overview(base_id: str) -> dict | None:
    overview = fleet_overview()
    return next((b for b in overview["bases"] if b["id"] == base_id), None)
