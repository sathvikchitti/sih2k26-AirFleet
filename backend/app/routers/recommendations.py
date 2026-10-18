"""Recommendation and decision-impact endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..repositories import WorkOrderRepository
from ..domain.enums import Permission
from ..security import require_demo_permission
from ..services import compatibility, impact_service, recommendation_service, transfer_service
from ..services.transfer_service import TransferError

router = APIRouter(tags=["recommendations"])


@router.get("/api/recommendations/{aircraft_id}")
def recommendation_for_aircraft(aircraft_id: str):
    """Legacy shape, keyed by aircraft id (existing UI entry point)."""
    work_order = compatibility.active_work_order_for(aircraft_id)
    if work_order is None:
        return {
            "aircraft_id": aircraft_id.upper(),
            "required_component": None,
            "candidates": [],
            "recommended": None,
        }
    return compatibility._legacy_recommendation(work_order["id"])


@router.get("/api/work-orders/{work_order_id}/recommendation")
def recommendation_for_work_order(work_order_id: str):
    """Full, explainable evaluation for a work order (spec sections 8-11)."""
    if WorkOrderRepository.get(work_order_id) is None:
        raise HTTPException(404, "unknown work order")
    return recommendation_service.evaluate_candidates(work_order_id)


@router.get("/api/work-orders/{work_order_id}/impact")
def impact_preview(work_order_id: str):
    """Expected fleet-availability impact per option (spec section 15)."""
    if WorkOrderRepository.get(work_order_id) is None:
        raise HTTPException(404, "unknown work order")
    return impact_service.preview(work_order_id)


class ApproveRecommendation(BaseModel):
    actor: str = "commander"
    allow_reserve_override: bool = False
    donor_base: str | None = None


@router.post("/api/work-orders/{work_order_id}/recommendation/approve")
def approve(work_order_id: str, body: ApproveRecommendation | None = None,
            demo_role: str | None = Header(None, alias="X-Demo-Role"),
            demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Human approval — creates a real transfer and mutates state."""
    body = body or ApproveRecommendation()
    actor = require_demo_permission(body.actor, Permission.APPROVE_RECOMMENDATION,
                                    demo_role=demo_role, demo_base=demo_base)
    if WorkOrderRepository.get(work_order_id) is None:
        raise HTTPException(404, "unknown work order")
    try:
        return transfer_service.approve_recommendation(
            work_order_id,
            actor=actor,
            allow_reserve_override=body.allow_reserve_override,
            donor_base=body.donor_base,
        )
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc


class RejectRecommendation(BaseModel):
    actor: str = "commander"
    reason: str | None = None


@router.post("/api/recommendations/{aircraft_id}/reject")
def reject_for_aircraft(aircraft_id: str, body: RejectRecommendation | None = None,
                        demo_role: str | None = Header(None, alias="X-Demo-Role"),
                        demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Legacy shape: reject the recommendation for an aircraft."""
    from ..services.audit_service import recommendation_rejected

    body = body or RejectRecommendation()
    actor = require_demo_permission(body.actor, Permission.APPROVE_RECOMMENDATION,
                                    demo_role=demo_role, demo_base=demo_base)
    work_order = compatibility.active_work_order_for(aircraft_id)
    if work_order is None:
        raise HTTPException(404, "no active work order for aircraft")
    recommendation_rejected(work_order["id"], actor=actor, reason=body.reason)
    return {"ok": True, "work_order_id": work_order["id"], "rejected": True}


@router.post("/api/recommendations/{aircraft_id}/approve")
def approve_for_aircraft(aircraft_id: str, body: ApproveRecommendation | None = None,
                         demo_role: str | None = Header(None, alias="X-Demo-Role"),
                         demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Legacy shape: approve by aircraft id, driven by the active work order."""
    body = body or ApproveRecommendation()
    actor = require_demo_permission(body.actor, Permission.APPROVE_RECOMMENDATION,
                                    demo_role=demo_role, demo_base=demo_base)
    work_order = compatibility.active_work_order_for(aircraft_id)
    if work_order is None:
        raise HTTPException(404, "no active work order for aircraft")
    try:
        return transfer_service.approve_recommendation(
            work_order["id"],
            actor=actor,
            allow_reserve_override=body.allow_reserve_override,
            donor_base=body.donor_base,
        )
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc
