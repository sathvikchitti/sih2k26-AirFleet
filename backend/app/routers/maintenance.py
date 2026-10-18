"""Maintenance endpoints: predicted events, work orders, lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, field_validator

from ..data import BASES
from ..domain.enums import Permission, WorkOrderStatus
from ..repositories import AircraftRepository, EventRepository, WorkOrderRepository
from ..security import require_demo_permission
from ..services import compatibility, maintenance_service, resource_service
from ..services.maintenance_service import ManualWorkOrderValidationError
from ..services.transfer_service import TransferError

router = APIRouter(tags=["maintenance"])


# ---- Predicted maintenance events -----------------------------------------
@router.get("/api/maintenance/events")
def list_events():
    return EventRepository.list_all()


@router.get("/api/maintenance/events/{event_id}")
def get_event(event_id: str):
    event = EventRepository.get(event_id)
    if event is None:
        raise HTTPException(404, "unknown maintenance event")
    return event


class TriageRequest(BaseModel):
    required_component: str | None = None
    actor: str = "base"


@router.post("/api/maintenance/events/{event_id}/work-order")
def create_work_order(event_id: str, body: TriageRequest,
                      demo_role: str | None = Header(None, alias="X-Demo-Role"),
                      demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """The explicit step that turns a prediction into committed maintenance.

    A predicted event existing does NOT imply a work order exists.
    """
    event = EventRepository.get(event_id)
    if event is None:
        raise HTTPException(404, "unknown maintenance event")
    aircraft = AircraftRepository.get(event["aircraft_id"])
    actor = require_demo_permission(body.actor, Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=aircraft.get("base_id") if aircraft else None)

    work_order = maintenance_service.create_work_order_from_event(
        event_id, required_component=body.required_component, actor=actor
    )
    if work_order is None:
        raise HTTPException(
            400,
            "no maintenance rule matched this prediction, so the required resource "
            "cannot be inferred; raise a manual work order instead",
        )
    return work_order


@router.post("/api/maintenance/events/{event_id}/dismiss")
def dismiss_event(event_id: str, reason: str | None = None, actor: str = "commander",
                  demo_role: str | None = Header(None, alias="X-Demo-Role"),
                  demo_base: str | None = Header(None, alias="X-Demo-Base")):
    event = EventRepository.get(event_id)
    if event is None:
        raise HTTPException(404, "unknown maintenance event")
    aircraft = AircraftRepository.get(event["aircraft_id"])
    actor = require_demo_permission(actor, Permission.REQUEST_RESOURCE, Permission.APPROVE_RECOMMENDATION,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=aircraft.get("base_id") if aircraft else None)
    if EventRepository.get(event_id) is None:
        raise HTTPException(404, "unknown maintenance event")
    return maintenance_service.dismiss_event(event_id, reason=reason, actor=actor)


# ---- Work orders -----------------------------------------------------------
@router.get("/api/maintenance/work-orders")
def list_work_orders():
    return [maintenance_service.work_order_summary(w) for w in WorkOrderRepository.list_all()]


@router.get("/api/maintenance/work-orders/{work_order_id}")
def get_work_order(work_order_id: str):
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        raise HTTPException(404, "unknown work order")
    return {
        **maintenance_service.work_order_summary(work_order),
        "local_resource": resource_service.local_availability(work_order),
    }


class ManualWorkOrder(BaseModel):
    component: str | None = None
    issue: str = "Manually raised work order"
    # The domain validator returns a sanitized error for NaN/Infinity too;
    # Pydantic's default request error includes the offending float, which is
    # not JSON-serializable in FastAPI's error response.
    estimated_repair_hours: float = 4.0
    priority: str = "MEDIUM"
    actor: str = "base"

    @field_validator("estimated_repair_hours", mode="before")
    @classmethod
    def reject_boolean_repair_duration(cls, value):
        if isinstance(value, bool):
            raise ValueError("estimated_repair_hours must be finite and positive")
        return value


@router.post("/api/maintenance/work-orders")
def create_manual_work_order(aircraft_id: str, body: ManualWorkOrder,
                             demo_role: str | None = Header(None, alias="X-Demo-Role"),
                             demo_base: str | None = Header(None, alias="X-Demo-Base")):
    aircraft = AircraftRepository.get(aircraft_id)
    actor = require_demo_permission(body.actor, Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=aircraft.get("base_id") if aircraft else None)
    try:
        work_order = maintenance_service.create_manual_work_order(
            aircraft_id,
            component=body.component,
            issue=body.issue,
            estimated_repair_hours=body.estimated_repair_hours,
            priority=body.priority,
            actor=actor,
        )
    except ManualWorkOrderValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if work_order is None:
        raise HTTPException(404, "unknown aircraft")
    return work_order


@router.post("/api/maintenance/work-orders/{work_order_id}/start")
def start_work_order(work_order_id: str, actor: str = "base",
                     demo_role: str | None = Header(None, alias="X-Demo-Role"),
                     demo_base: str | None = Header(None, alias="X-Demo-Base")):
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        raise HTTPException(404, "unknown work order")
    actor = require_demo_permission(actor, Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=work_order["base_id"])
    if work_order["status"] not in (
        WorkOrderStatus.RESOURCE_AVAILABLE.value, WorkOrderStatus.SCHEDULED.value
    ):
        raise HTTPException(
            400,
            f"work order is {work_order['status']}; the required resource must arrive first",
        )
    return maintenance_service.start_maintenance(work_order_id, actor=actor)


@router.post("/api/maintenance/work-orders/{work_order_id}/complete")
def complete_work_order(work_order_id: str, actor: str = "base",
                        demo_role: str | None = Header(None, alias="X-Demo-Role"),
                        demo_base: str | None = Header(None, alias="X-Demo-Base")):
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        raise HTTPException(404, "unknown work order")
    actor = require_demo_permission(actor, Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=work_order["base_id"])
    return maintenance_service.complete_maintenance(work_order_id, actor=actor)


# ---- Cross-base resource search -------------------------------------------
@router.get("/api/resources/search/{work_order_id}")
def search_resources(work_order_id: str):
    """Search every base for a work order's required component (spec section 7)."""
    if WorkOrderRepository.get(work_order_id) is None:
        raise HTTPException(404, "unknown work order")
    return resource_service.search(work_order_id)


@router.get("/api/resources/demand")
def resource_demand(base_id: str | None = None):
    """Demand versus supply across bases (spec sections 7 and 9).

    The UI renders this instead of computing shortfalls itself.
    """
    if base_id and not any(b["id"] == base_id for b in BASES):
        raise HTTPException(404, "unknown base")
    return resource_service.demand_summary(base_id)


@router.get("/api/resources/allocation-preview")
def allocation_preview(work_order_ids: list[str] | None = Query(default=None)):
    """Read-only shared-stock planning; query may repeat work_order_ids."""
    from ..services.planning_service import allocation_preview as build_preview
    return build_preview(work_order_ids=work_order_ids)


# ---- Legacy surface preserved for the existing UI -------------------------
@router.get("/api/maintenance")
def legacy_maintenance():
    return compatibility.legacy_maintenance_list()


@router.post("/api/maintenance/{aircraft_id}/start")
def legacy_start(aircraft_id: str,
                 demo_role: str | None = Header(None, alias="X-Demo-Role"),
                 demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Legacy shape: start maintenance by aircraft id."""
    work_order = compatibility.active_work_order_for(aircraft_id)
    if work_order is None:
        raise HTTPException(404, "no active work order for aircraft")
    actor = require_demo_permission("base", Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=work_order["base_id"])
    return maintenance_service.start_maintenance(work_order["id"], actor=actor)


@router.post("/api/maintenance/{aircraft_id}/complete")
def legacy_complete(aircraft_id: str,
                    demo_role: str | None = Header(None, alias="X-Demo-Role"),
                    demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Legacy shape: complete maintenance by aircraft id."""
    work_order = compatibility.active_work_order_for(aircraft_id)
    if work_order is None:
        raise HTTPException(404, "no active work order for aircraft")
    actor = require_demo_permission("base", Permission.REQUEST_RESOURCE,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=work_order["base_id"])
    return maintenance_service.complete_maintenance(work_order["id"], actor=actor)
