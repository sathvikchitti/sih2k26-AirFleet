"""Fleet availability service — the north-star metric (spec section 13).

Availability is CALCULATED, never stored:

    fleet_availability = available_aircraft / total_aircraft

Only `AVAILABLE` counts as flyable. Because aircraft state is recomputed from
the active work order plus the ML risk band, any workflow transition updates
availability automatically — there is no separate number to keep in sync.
"""

from __future__ import annotations

import math
import os

from ..data import BASES
from ..domain import knowledge
from ..domain.enums import AircraftStatus, PRIORITY_ORDER, TransferStatus, WorkOrderStatus
from ..repositories import AircraftRepository, WorkOrderRepository, snapshot, store
from ..repositories.inventory_repository import DEFAULT_MIN_CONDITION_PCT
from ..repositories.maintenance_repository import OPEN_WORK_ORDER_STATUSES
from .ml import get_provider, predict_validated


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def parse_readiness_target(value: str | None) -> float:
    """Parse the configured mission-capable target or fail closed."""
    if value is None:
        return 75.0
    try:
        target = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("READINESS_TARGET_PCT must be a finite number from 0 to 100") from exc
    if not math.isfinite(target) or not 0 <= target <= 100:
        raise RuntimeError("READINESS_TARGET_PCT must be a finite number from 0 to 100")
    return target


READINESS_TARGET_PCT = parse_readiness_target(os.getenv("READINESS_TARGET_PCT"))


def _readiness_kpis_from_snapshot(state: dict, target_pct: float) -> dict[str, dict]:
    """Calculate fleet/base KPI counts from one immutable repository snapshot.

    NMCS is a demo resource-shortage proxy: a non-AVAILABLE airframe counts
    once if an open, catalogued component work order cannot claim serviceable
    local stock. In-transit/pending shipments are not on-hand stock; receipt
    affects the result only after inventory is actually credited. Known
    reservations are already excluded from the free-quantity calculation.
    """
    aircraft = list(state.get("aircraft", []))
    by_aircraft = {str(row.get("id", "")).upper(): row for row in aircraft}
    inventory = [dict(row) for row in state.get("inventory", [])]
    inventory_by_key = {
        (str(row.get("base_id", "")).lower(), str(row.get("part_number", "")).upper()): row
        for row in inventory
    }
    parts = {
        str(row.get("part_number", "")).upper(): row
        for row in state.get("parts", [])
    }
    totals: dict[str, dict[str, set[str] | int]] = {
        base["id"]: {"available": set(), "maintenance_down": set(), "nmcs": set()}
        for base in BASES
    }
    fleet: dict[str, set[str] | int] = {
        "available": set(), "maintenance_down": set(), "nmcs": set(),
    }
    reserved_claims: dict[tuple[str, str], int] = {}

    # A pending outgoing shipment has not changed physical on-hand quantity,
    # but the allocator treats it as a provisional claim. Keep it unavailable
    # to other work orders in this deterministic snapshot projection.
    for transfer in sorted(
        state.get("transfers", []),
        key=lambda row: (str(row.get("created") or row.get("created_at") or ""),
                         str(row.get("id") or "")),
    ):
        if transfer.get("status") != TransferStatus.PENDING_APPROVAL.value:
            continue
        key = (str(transfer.get("source_base", "")).lower(),
               str(transfer.get("part_number", "")).upper())
        line = inventory_by_key.get(key)
        if line is not None:
            line["quantity"] = int(line.get("quantity", 0)) - int(transfer.get("quantity", 1))

    for aircraft_row in aircraft:
        aircraft_id = str(aircraft_row.get("id", "")).upper()
        base_id = str(aircraft_row.get("base_id", "")).lower()
        status = aircraft_row.get("status")
        if status == AircraftStatus.AVAILABLE.value:
            fleet["available"].add(aircraft_id)
            if base_id in totals:
                totals[base_id]["available"].add(aircraft_id)
        if status in (AircraftStatus.MAINTENANCE.value, AircraftStatus.WAITING_FOR_PART.value):
            fleet["maintenance_down"].add(aircraft_id)
            if base_id in totals:
                totals[base_id]["maintenance_down"].add(aircraft_id)

    def order(row: dict) -> tuple:
        priority = PRIORITY_ORDER.get(row.get("priority"), 0)
        return (-int(priority), str(row.get("created_at") or ""), str(row.get("id") or ""))

    open_orders = sorted(
        (row for row in state.get("work_orders", [])
         if row.get("status") in OPEN_WORK_ORDER_STATUSES),
        key=order,
    )
    for work_order in open_orders:
        aircraft_id = str(work_order.get("aircraft_id", "")).upper()
        aircraft_row = by_aircraft.get(aircraft_id)
        component = str(work_order.get("required_component") or "").upper()
        part = parts.get(component)
        if (aircraft_row is None or not component or part is None):
            continue

        base_id = str(work_order.get("base_id") or aircraft_row.get("base_id") or "").lower()
        line = inventory_by_key.get((base_id, component))
        minimum_condition = int(part.get("min_condition_pct", DEFAULT_MIN_CONDITION_PCT))

        # A reserved unit is already committed to this work order. It is not
        # a shortage when the current pooled line still meets the catalog
        # threshold and the aggregate inventory row reflects the reservation.
        # Per-unit condition is not represented in this POC.
        if work_order.get("resource_reserved"):
            key = (base_id, component)
            used_reserved = reserved_claims.get(key, 0)
            try:
                reserved_unit_serviceable = (
                    line is not None
                    and int(line.get("quantity", 0)) > used_reserved
                    and int(line.get("reserved", 0)) > used_reserved
                    and int(line.get("condition_pct")) >= minimum_condition
                )
            except (TypeError, ValueError, OverflowError):
                reserved_unit_serviceable = False
            if reserved_unit_serviceable:
                reserved_claims[key] = used_reserved + 1
                continue
            has_local_unit = False
        elif line is None:
            has_local_unit = False
        else:
            available = (
                int(line.get("quantity", 0))
                - int(line.get("reserved", 0))
                - int(line.get("minimum_reserve", 0))
            )
            try:
                condition = int(line.get("condition_pct", 0))
            except (TypeError, ValueError, OverflowError):
                condition = -1
            has_local_unit = available > 0 and condition >= minimum_condition

        if has_local_unit:
            # Claim from a cloned ledger in deterministic priority order so
            # two work orders cannot both count the same physical unit.
            line["quantity"] = int(line.get("quantity", 0)) - 1
            continue

        if aircraft_row.get("status") == AircraftStatus.AVAILABLE.value:
            continue
        fleet["nmcs"].add(aircraft_id)
        if str(aircraft_row.get("base_id", "")).lower() in totals:
            totals[str(aircraft_row["base_id"]).lower()]["nmcs"].add(aircraft_id)

    def fields(counts: dict[str, set[str] | int], denominator: int) -> dict:
        rate = _pct(len(counts["available"]), denominator)
        return {
            "mission_capable_rate_pct": rate,
            "readiness_target_pct": target_pct,
            "gap_to_target_pct": round(max(0.0, target_pct - rate), 1),
            "nmcs_count": len(counts["nmcs"]),
            "aircraft_down_for_maintenance": len(counts["maintenance_down"]),
        }

    result = {"fleet": fields(fleet, len(aircraft))}
    result["bases"] = {
        base_id: fields(counts, sum(
            str(row.get("base_id", "")).lower() == base_id for row in aircraft
        ))
        for base_id, counts in totals.items()
    }
    return result


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
    """Fleet-wide availability and readiness KPIs from one state snapshot."""
    provider = get_provider()
    # `snapshot()` is intentionally non-initializing; preserve repository
    # bootstrap behavior for direct service callers before FastAPI startup.
    store()
    state = snapshot()
    aircraft = state.get("aircraft", [])
    total = len(aircraft)
    kpis = _readiness_kpis_from_snapshot(state, READINESS_TARGET_PCT)

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
            **kpis["bases"][b["id"]],
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
        **kpis["fleet"],
        "bases": bases,
        # Provenance, so the UI can be honest about what the number means.
        "calculation": "available_aircraft / total_aircraft",
        "generated_by": "availability_service",
    }


def base_overview(base_id: str) -> dict | None:
    overview = fleet_overview()
    return next((b for b in overview["bases"] if b["id"] == base_id), None)
