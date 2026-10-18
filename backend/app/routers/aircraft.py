"""Aircraft endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..repositories import AircraftRepository, EventRepository, WorkOrderRepository
from ..services import compatibility, maintenance_service
from ..services.case_timeline_service import maintenance_case_timeline
from ..services.ml import get_provider
from ..domain.enums import AuditEventType, Permission
from ..security import require_demo_permission

router = APIRouter(tags=["aircraft"])


@router.get("/api/aircraft")
def aircraft_list():
    return [compatibility.aircraft_legacy(a) for a in AircraftRepository.list_all()]


@router.get("/api/aircraft/{aircraft_id}")
def aircraft_detail(aircraft_id: str):
    detail = compatibility.aircraft_detail(aircraft_id)
    if detail is None:
        raise HTTPException(404, "unknown aircraft")
    return detail


@router.get("/api/aircraft/{aircraft_id}/trend")
def trend(aircraft_id: str):
    """Provider trend for the detail chart, with its data semantics labeled.

    Recorded prediction history is available separately at
    `/api/predictions/{id}/history`.
    """
    if AircraftRepository.get(aircraft_id) is None:
        raise HTTPException(404, "unknown aircraft")
    key = aircraft_id.upper()
    provider = get_provider()
    return {
        "aircraft_id": key,
        "trend": provider.degradation_trend(key),
        "trend_source": getattr(provider, "trend_source", "illustrative_provider_curve"),
    }


@router.post("/api/aircraft/{aircraft_id}/predict")
def regenerate_prediction(aircraft_id: str,
                          demo_role: str | None = Header(None, alias="X-Demo-Role"),
                          demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Run the ML provider now and record a predicted maintenance event.

    Separates 'the model has spoken' from 'work has been committed'.
    """
    aircraft = AircraftRepository.get(aircraft_id)
    if aircraft is None:
        raise HTTPException(404, "unknown aircraft")
    require_demo_permission("base", Permission.REQUEST_RESOURCE,
                            demo_role=demo_role, demo_base=demo_base,
                            resource_base=aircraft["base_id"])
    event = maintenance_service.ingest_prediction(aircraft_id)
    return {
        "aircraft_id": aircraft_id.upper(),
        "prediction": maintenance_service.get_prediction(aircraft_id),
        "predicted_maintenance_event": event,
        "work_order_created": False,
        "note": (
            "A prediction creates a predicted maintenance event only. Triage it via "
            "POST /api/maintenance/events/{event_id}/work-order to commit a work order."
        ),
    }


@router.get("/api/aircraft/{aircraft_id}/predicted-events")
def predicted_events(aircraft_id: str):
    if AircraftRepository.get(aircraft_id) is None:
        raise HTTPException(404, "unknown aircraft")
    return EventRepository.find_by_aircraft(aircraft_id)


@router.get("/api/aircraft/{aircraft_id}/work-orders")
def work_orders(aircraft_id: str):
    if AircraftRepository.get(aircraft_id) is None:
        raise HTTPException(404, "unknown aircraft")
    return WorkOrderRepository.list_by_aircraft(aircraft_id)


@router.get("/api/aircraft/{aircraft_id}/maintenance-timeline")
def maintenance_timeline(aircraft_id: str, work_order_id: str | None = None):
    """Read-only, ID-linked maintenance history for an aircraft or one case."""
    result = maintenance_case_timeline(aircraft_id, work_order_id=work_order_id)
    if result is None:
        raise HTTPException(404, "unknown aircraft")
    if result.get("error"):
        raise HTTPException(404, result["error"])
    return result
