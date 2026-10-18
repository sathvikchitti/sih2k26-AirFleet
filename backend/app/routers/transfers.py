"""Transfer endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..repositories import TransferRepository
from ..domain.enums import Permission
from ..security import require_demo_permission
from ..services import compatibility, transfer_service
from ..services.transfer_service import TransferError

router = APIRouter(tags=["transfers"])


@router.get("/api/transfers")
def transfers():
    return [transfer_service.transfer_summary(t) for t in TransferRepository.list_all()]


@router.get("/api/transfers/{transfer_id}")
def transfer_detail(transfer_id: str):
    transfer = TransferRepository.get(transfer_id)
    if transfer is None:
        raise HTTPException(404, "unknown transfer")
    return transfer_service.transfer_summary(transfer)


class TransferCreate(BaseModel):
    part_number: str
    source_base: str
    dest_base: str
    quantity: int = 1
    for_aircraft: str | None = None
    work_order_id: str | None = None
    actor: str = "logistics"


@router.post("/api/transfers")
def create_transfer(body: TransferCreate,
                    demo_role: str | None = Header(None, alias="X-Demo-Role"),
                    demo_base: str | None = Header(None, alias="X-Demo-Base")):
    actor = require_demo_permission(body.actor, Permission.REQUEST_RESOURCE, Permission.MANAGE_TRANSFERS,
                                    demo_role=demo_role, demo_base=demo_base,
                                    resource_base=body.dest_base)
    try:
        return transfer_service.create_transfer(
            part_number=body.part_number,
            source_base=body.source_base,
            dest_base=body.dest_base,
            quantity=body.quantity,
            for_aircraft=body.for_aircraft,
            work_order_id=body.work_order_id,
            actor=actor,
        )
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc


class ApproveTransfer(BaseModel):
    allow_reserve_override: bool = False
    actor: str = "logistics"


@router.post("/api/transfers/{transfer_id}/approve")
def approve(transfer_id: str, body: ApproveTransfer | None = None,
            demo_role: str | None = Header(None, alias="X-Demo-Role"),
            demo_base: str | None = Header(None, alias="X-Demo-Base")):
    body = body or ApproveTransfer()
    actor = require_demo_permission(body.actor, Permission.MANAGE_TRANSFERS,
                                    demo_role=demo_role, demo_base=demo_base)
    try:
        return transfer_service.approve_transfer(
            transfer_id,
            actor=actor,
            allow_reserve_override=body.allow_reserve_override,
        )
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/transfers/{transfer_id}/receive")
def receive(transfer_id: str, actor: str = "logistics",
            demo_role: str | None = Header(None, alias="X-Demo-Role"),
            demo_base: str | None = Header(None, alias="X-Demo-Base")):
    actor = require_demo_permission(actor, Permission.MANAGE_TRANSFERS,
                                    demo_role=demo_role, demo_base=demo_base)
    try:
        return transfer_service.receive_transfer(transfer_id, actor=actor)
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/transfers/{transfer_id}/cancel")
def cancel(transfer_id: str, reason: str | None = None, actor: str = "logistics",
           demo_role: str | None = Header(None, alias="X-Demo-Role"),
           demo_base: str | None = Header(None, alias="X-Demo-Base")):
    actor = require_demo_permission(actor, Permission.MANAGE_TRANSFERS,
                                    demo_role=demo_role, demo_base=demo_base)
    try:
        return transfer_service.cancel_transfer(transfer_id, reason=reason, actor=actor)
    except TransferError as exc:
        raise HTTPException(400, str(exc)) from exc
