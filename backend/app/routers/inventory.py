"""Parts and inventory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..domain import knowledge
from ..domain.enums import Permission, WorkOrderStatus
from ..repositories import InventoryRepository, PartRepository, WorkOrderRepository, refresh_line_status
from ..repositories.store import lock
from ..security import require_demo_permission
from ..services.compatibility import legacy_inventory_row
from ..services import audit_service
from ..services.demand_forecast_service import forecast_resources

router = APIRouter(tags=["inventory", "components"])


@router.get("/api/parts")
def parts():
    return PartRepository.list_all()


@router.get("/api/parts/{part_number}")
def part_detail(part_number: str):
    part = PartRepository.get(part_number)
    if part is None:
        raise HTTPException(404, "unknown component")
    return {
        **part,
        "stock": [
            legacy_inventory_row(i)
            for i in InventoryRepository.find_all_for_part(part_number)
        ],
    }


@router.get("/api/maintenance/knowledge")
def maintenance_knowledge():
    """The issue -> action -> component mapping (spec section 17).

    Exposed so the UI can show *why* a part was chosen without hard-coding it.
    """
    return {"rules": knowledge.rules_as_dicts()}


@router.get("/api/inventory")
def inventory():
    return [legacy_inventory_row(i) for i in InventoryRepository.list_all()]


@router.get("/api/resources/forecast")
def resources_forecast(horizon_cycles: float = Query(default=30.0, ge=0, le=10000)):
    """Indicative read-only cycle-based spares demand forecast."""
    try:
        return forecast_resources(horizon_cycles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class InventoryUpdate(BaseModel):
    quantity: int | None = None
    reserved: int | None = None
    minimum_reserve: int | None = None
    condition_pct: int | None = Field(default=None, ge=0, le=100)

    @field_validator("condition_pct", mode="before")
    @classmethod
    def reject_boolean_condition(cls, value):
        if isinstance(value, bool):
            raise ValueError("condition_pct must be an integer from 0 to 100")
        return value


@router.patch("/api/inventory/{inventory_id}")
def update_inventory(inventory_id: str, body: InventoryUpdate,
                     demo_role: str | None = Header(None, alias="X-Demo-Role"),
                     demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Logistics adjusts stock, condition and reserve."""
    actor = require_demo_permission("logistics", Permission.MANAGE_INVENTORY,
                                    demo_role=demo_role, demo_base=demo_base)
    inv = InventoryRepository.get(inventory_id)
    if inv is None:
        raise HTTPException(404, "unknown inventory line")

    fields = body.model_dump(exclude_none=True)
    with lock():
        current = InventoryRepository.get(inventory_id)
        updated_fields = {**current, **fields}
        for numeric in ("quantity", "reserved", "minimum_reserve", "condition_pct"):
            value = updated_fields.get(numeric, 0)
            if value < 0:
                raise HTTPException(400, f"{numeric} cannot be negative")
        if updated_fields["reserved"] + updated_fields["minimum_reserve"] > updated_fields["quantity"]:
            raise HTTPException(400, "reserved plus minimum_reserve cannot exceed quantity")
        committed = sum(
            1 for work_order in WorkOrderRepository.find_by_component(current["part_number"])
            if work_order.get("base_id") == current["base_id"]
            and work_order.get("resource_reserved")
            and work_order.get("status") not in (
                WorkOrderStatus.COMPLETED.value, WorkOrderStatus.CANCELLED.value,
            )
        )
        if updated_fields["reserved"] < committed:
            raise HTTPException(
                400,
                f"reserved cannot be reduced below {committed} active work-order commitment(s)",
            )
        before = {key: current.get(key) for key in
                  ("quantity", "reserved", "minimum_reserve", "condition_pct", "status")}
        inv = refresh_line_status(InventoryRepository.update(inventory_id, **fields))
        after = {key: inv.get(key) for key in before}
        if before != after:
            audit_service.inventory_updated(inv, before, after, actor=actor)
    return legacy_inventory_row(inv)
