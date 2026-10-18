"""Legacy compatibility layer.

The existing frontend and the 21 original endpoints must keep working
untouched while the new model takes over as the source of truth. Rather than
duplicating logic, the legacy shapes are *projections* of the new entities.

Status vocabulary bridging:

    legacy WAITING_FOR_COMPONENT | AWAITING_DELIVERY -> WAITING_FOR_RESOURCE
    legacy READY_TO_START                              -> RESOURCE_AVAILABLE
    legacy SCHEDULED / IN_PROGRESS / COMPLETED         -> unchanged
    legacy DEGRADED                                    -> aircraft-level, retained
"""

from __future__ import annotations

from ..domain.enums import (
    MaintenanceEventStatus,
    TransferStatus,
    WorkOrderStatus,
)
from ..repositories import (
    AircraftRepository,
    EventRepository,
    InventoryRepository,
    PartRepository,
    PredictionHistoryRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
)
from . import maintenance_service
from .ml import get_provider
from .resource_service import search as resource_search

# New work-order status -> the legacy status the old UI expects.
_LEGACY_WO_STATUS = {
    WorkOrderStatus.OPEN.value: "SCHEDULED",
    WorkOrderStatus.WAITING_FOR_RESOURCE.value: "WAITING_FOR_COMPONENT",
    WorkOrderStatus.RESOURCE_AVAILABLE.value: "READY_TO_START",
    WorkOrderStatus.SCHEDULED.value: "SCHEDULED",
    WorkOrderStatus.IN_PROGRESS.value: "IN_PROGRESS",
    WorkOrderStatus.COMPLETED.value: "COMPLETED",
    WorkOrderStatus.CANCELLED.value: "CANCELLED",
}

# Reverse map used when a legacy endpoint drives a new work order.
_LEGACY_TO_NEW_WO_STATUS = {
    "WAITING_FOR_COMPONENT": WorkOrderStatus.WAITING_FOR_RESOURCE.value,
    "AWAITING_DELIVERY": WorkOrderStatus.WAITING_FOR_RESOURCE.value,
    "READY_TO_START": WorkOrderStatus.RESOURCE_AVAILABLE.value,
    "SCHEDULED": WorkOrderStatus.SCHEDULED.value,
    "OPEN": WorkOrderStatus.OPEN.value,
}


def legacy_work_order_status(status: str) -> str:
    return _LEGACY_WO_STATUS.get(status, status)


def new_status_from_legacy(status: str) -> str:
    return _LEGACY_TO_NEW_WO_STATUS.get(status, status)


# --------------------------------------------------------------------------
# Aircraft
# --------------------------------------------------------------------------
def aircraft_legacy(aircraft: dict) -> dict:
    """`/api/aircraft` row shape.

    `required_component` is retained for the existing UI, but it now comes from
    the maintenance knowledge layer rather than the ML model.
    """
    pred = get_prediction_with_component(aircraft["id"])
    work_orders = WorkOrderRepository.list_by_aircraft(aircraft["id"])
    active = next((w for w in work_orders if w["status"] != WorkOrderStatus.COMPLETED.value), None)
    mx = legacy_maintenance(active) if active else None

    return {
        "id": aircraft["id"],
        "base_id": aircraft["base_id"],
        "type": aircraft["type"],
        "tail": aircraft["tail"],
        "status": aircraft.get("status"),
        "required_component": pred["maintenance"].get("required_component"),
        "required_by_hours": active.get("required_by_flight_hours") if active else None,
        "required_by_rul": active.get("required_by_rul") if active else None,
        "rul_unit": active.get("rul_unit") if active else pred.get("rul_unit"),
        "estimated_recovery_hours": active.get("estimated_repair_hours") if active else 0,
        "priority": active.get("priority") if active else "NONE",
        "health": {**pred, "required_component": pred["maintenance"].get("required_component")},
        "maintenance": mx,
    }


def get_prediction_with_component(aircraft_id: str) -> dict:
    """Prediction for the legacy shape.

    Single source of truth: `maintenance_service.get_prediction` owns the
    knowledge-layer interpretation. The only thing added here is a top-level
    `required_component`, which the original `/api/health` contract exposed and
    the existing UI still reads.
    """
    from . import maintenance_service

    view = maintenance_service.get_prediction(aircraft_id)
    if view is None:
        return {}
    return {**view, "required_component": view["maintenance"].get("required_component")}


def legacy_maintenance(work_order: dict | None) -> dict | None:
    """`/api/maintenance` row shape derived from a work order."""
    if work_order is None:
        return None
    status = legacy_work_order_status(work_order["status"])
    # AWAITING_DELIVERY distinguished "in transit" from "nothing arranged yet".
    if status == "WAITING_FOR_COMPONENT":
        transfer = TransferRepository.active_for_work_order(work_order["id"])
        if transfer and transfer["status"] == TransferStatus.IN_TRANSIT.value:
            status = "AWAITING_DELIVERY"

    return {
        "id": work_order["id"],
        "aircraft_id": work_order["aircraft_id"],
        "component": work_order.get("required_component"),
        "priority": work_order.get("priority"),
        "status": status,
        "estimated_recovery_hours": work_order.get("estimated_repair_hours"),
        "required_by_hours": work_order.get("required_by_flight_hours"),
        "required_by_rul": work_order.get("required_by_rul"),
        "rul_unit": work_order.get("rul_unit"),
        "started": work_order.get("started_at"),
    }


def legacy_maintenance_list() -> list[dict]:
    """All legacy maintenance rows, in the order the old UI expects."""
    rows = []
    for wo in WorkOrderRepository.list_all():
        row = legacy_maintenance(wo)
        if row:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def legacy_inventory_row(inv: dict) -> dict:
    """`/api/inventory` row shape.

    `reserved` is kept for the old UI; `reserved_quantity` and
    `minimum_reserve` are added so the new field names in the spec are also
    exposed. `available_for_transfer` is the fleet-aware figure.
    """
    return {
        **inv,
        "reserved": int(inv.get("reserved", 0)),
        "reserved_quantity": int(inv.get("reserved", 0)),
        "minimum_reserve": int(inv.get("minimum_reserve", 0)),
        "available_for_transfer": max(0, available_for_transfer(inv)),
        "condition": round(int(inv.get("condition_pct", 0)) / 100.0, 2),
    }


# --------------------------------------------------------------------------
# Aircraft detail
# --------------------------------------------------------------------------
def aircraft_detail(aircraft_id: str) -> dict | None:
    """`/api/aircraft/{id}` shape: record + prediction + resources + rec."""
    aircraft = AircraftRepository.get(aircraft_id)
    if aircraft is None:
        return None

    pred = get_prediction_with_component(aircraft["id"])
    work_orders = WorkOrderRepository.list_by_aircraft(aircraft["id"])
    active = next((w for w in work_orders if w["status"] != WorkOrderStatus.COMPLETED.value), None)

    stock: list[dict] = []
    recommendation = None
    component = pred.get("required_component")
    if component:
        for inv in InventoryRepository.find_all_for_part(component):
            stock.append({
                **legacy_inventory_row(inv),
                "distance_km": _distance(aircraft["base_id"], inv["base_id"]),
                "eta_hours": _eta(aircraft["base_id"], inv["base_id"]),
            })
        if active:
            recommendation = _legacy_recommendation(active["id"])

    history = PredictionHistoryRepository.for_aircraft(aircraft["id"])
    has_synthetic = any(row.get("is_synthetic", False) for row in history)
    has_recorded = any(row.get("history_source") in ("recorded", "recorded_synthetic") for row in history)
    history_source = ("mixed_synthetic_and_recorded" if has_synthetic and has_recorded
                      else "illustrative" if has_synthetic else "recorded")
    provider = get_provider()
    return {
        **aircraft_legacy(aircraft),
        "trend": provider.degradation_trend(aircraft["id"]),
        "trend_source": getattr(provider, "trend_source", "illustrative_provider_curve"),
        "maintenance": legacy_maintenance(active),
        "resource_availability": stock,
        "recommendation": recommendation,
        # New-model extras, additive only.
        "work_orders": WorkOrderRepository.list_by_aircraft(aircraft["id"]),
        "predicted_events": EventRepository.find_by_aircraft(aircraft["id"]),
        "prediction_history": history,
        "history_source": pred.get("history_source") or history_source,
        "is_synthetic": bool(pred.get("is_synthetic", has_synthetic)),
    }


def _distance(a: str, b: str) -> int:
    from ..data import distance_km
    return distance_km(a, b)


def _eta(a: str, b: str) -> float:
    from ..data import eta_hours
    return eta_hours(a, b)


def _legacy_recommendation(work_order_id: str) -> dict | None:
    """The old `/api/recommendations/{id}` shape, from the new engine."""
    from .recommendation_service import evaluate_candidates

    evaluation = evaluate_candidates(work_order_id)
    if evaluation.get("error"):
        return None

    candidates = [
        {
            "donor_base": c["source_base"],
            "quantity_available": c["quantity_available"],
            "condition_pct": c["condition_pct"],
            "distance_km": c["distance_km"],
            "eta_hours": c["eta_hours"],
            "retains_reserve": c["donor_reserve_after_transfer"] > c["minimum_reserve"],
            "reserve_violation": c["donor_reserve_after_transfer"] <= 0,
            "expected_downtime_hours": c["expected_downtime_hours"],
            "score": c["score"],
        }
        for c in evaluation.get("candidates", [])
    ]

    recommended = evaluation.get("recommended")
    rec = None
    if recommended:
        rec = {
            "donor_base": recommended["source_base"],
            "quantity_available": recommended["quantity_available"],
            "condition_pct": recommended["condition_pct"],
            "distance_km": recommended["distance_km"],
            "eta_hours": recommended["eta_hours"],
            "expected_downtime_hours": recommended["expected_downtime_hours"],
            "score": recommended["score"],
            "reasons": recommended["reasons"],
        }

    return {
        "aircraft_id": evaluation.get("aircraft_id"),
        "home_base": evaluation.get("home_base"),
        "required_component": evaluation.get("required_component"),
        "urgency": evaluation.get("urgency"),
        "risk_level": evaluation.get("risk_level"),
        "rul": evaluation.get("rul"),
        "candidates": candidates,
        "recommended": rec,
        "work_order_id": work_order_id,
    }


# --------------------------------------------------------------------------
# Resolution helpers: find the work order behind an aircraft
# --------------------------------------------------------------------------
def active_work_order_for(aircraft_id: str) -> dict | None:
    for wo in WorkOrderRepository.list_by_aircraft(aircraft_id):
        if wo["status"] != WorkOrderStatus.COMPLETED.value:
            return wo
    return None


def resources_for_aircraft(aircraft_id: str) -> dict:
    """Cross-base search driven off an aircraft id (legacy entry point)."""
    work_order = active_work_order_for(aircraft_id)
    if work_order is None:
        return {"candidates": [], "infeasible": []}
    return resource_search(work_order["id"])


def ingest_and_report(aircraft_id: str) -> dict | None:
    """Ingest a prediction and report the resulting event (if any)."""
    return maintenance_service.ingest_prediction(aircraft_id)
