"""Transfer and allocation service (spec sections 9 and 14).

Owns the physical side of the closed loop: approving a recommendation creates
a real transfer, reserving donor stock, and driving the work order through
WAITING_FOR_RESOURCE -> RESOURCE_AVAILABLE as the part moves.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..data import eta_hours
from ..domain.enums import AuditEventType, TransferStatus, WorkOrderStatus
from ..repositories import (
    AircraftRepository,
    InventoryRepository,
    PartRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
    refresh_line_status,
)
from ..repositories.store import state_locked
from . import audit_service


class TransferError(Exception):
    """Rejected mutation — surfaced to the API as a 4xx."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@state_locked
def create_transfer(part_number: str, source_base: str, dest_base: str,
                    quantity: int = 1, for_aircraft: str | None = None,
                    work_order_id: str | None = None,
                    status: str = TransferStatus.PENDING_APPROVAL.value,
                    condition_pct: int | None = None,
                    actor: str = "logistics") -> dict:
    """Raise a transfer request. Stock is only reserved once it is approved."""
    if source_base == dest_base:
        raise TransferError("source and destination must be different bases")
    from ..data import BASES
    base_ids = {base["id"] for base in BASES}
    if source_base not in base_ids or dest_base not in base_ids:
        raise TransferError("source or destination base is invalid")
    if status != TransferStatus.PENDING_APPROVAL.value:
        raise TransferError("new transfers must begin pending approval")
    if quantity < 1:
        raise TransferError("quantity must be at least 1")
    if PartRepository.get(part_number) is None:
        raise TransferError(f"unknown component {part_number}")
    if work_order_id:
        _validated_work_order({
            "work_order_id": work_order_id,
            "part_number": part_number,
            "dest_base": dest_base,
            "for_aircraft": for_aircraft,
        })
        if TransferRepository.active_for_work_order(work_order_id):
            raise TransferError("an active transfer already exists for this work order")

    transfer = TransferRepository.create(
        part_number=str(part_number).upper(),
        source_base=source_base,
        dest_base=dest_base,
        quantity=int(quantity),
        status=status,
        eta_hours=eta_hours(source_base, dest_base),
        created=_now(),
        started_at=_now() if status == TransferStatus.IN_TRANSIT.value else None,
        received_at=None,
        for_aircraft=str(for_aircraft).upper() if for_aircraft else None,
        work_order_id=work_order_id,
        condition_pct=condition_pct if condition_pct is not None else _source_condition(source_base, part_number),
    )
    audit_service.transfer_created(transfer, actor=actor)
    return transfer


def _source_condition(source_base: str, part_number: str) -> int:
    inv = InventoryRepository.find(source_base, part_number)
    return int(inv.get("condition_pct", 0)) if inv else 0


def _validate_transfer_structure(transfer: dict) -> tuple[str, str, str, int]:
    """Validate current shipment identity before dispatch or receipt effects."""
    from ..data import BASES

    source_base = transfer.get("source_base")
    dest_base = transfer.get("dest_base")
    part_number = str(transfer.get("part_number") or "").upper()
    known_bases = {base["id"] for base in BASES}
    try:
        quantity = int(transfer.get("quantity"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise TransferError("transfer quantity is invalid") from exc
    if (source_base not in known_bases or dest_base not in known_bases
            or source_base == dest_base):
        raise TransferError("transfer source or destination is invalid")
    if PartRepository.get(part_number) is None:
        raise TransferError(f"unknown component {part_number}")
    if quantity < 1:
        raise TransferError("transfer quantity must be at least 1")
    return source_base, dest_base, part_number, quantity


def _validated_work_order(transfer: dict, *, reject_unusable: bool = True) -> dict | None:
    """Return an intact linked work order, rejecting unusable links as needed."""
    work_order_id = transfer.get("work_order_id")
    if not work_order_id:
        return None
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        if reject_unusable:
            raise TransferError("unknown work order")
        return None
    if str(work_order.get("required_component") or "").upper() != str(transfer.get("part_number") or "").upper():
        if reject_unusable:
            raise TransferError("component does not match the work order requirement")
        return None
    if work_order.get("base_id") != transfer.get("dest_base"):
        if reject_unusable:
            raise TransferError("destination base does not match the work order base")
        return None
    aircraft_id = transfer.get("for_aircraft")
    if aircraft_id and str(aircraft_id).upper() != str(work_order.get("aircraft_id") or "").upper():
        if reject_unusable:
            raise TransferError("aircraft does not match the work order")
        return None
    if reject_unusable and (
        work_order.get("status") in {
            WorkOrderStatus.IN_PROGRESS.value,
            WorkOrderStatus.COMPLETED.value,
            WorkOrderStatus.CANCELLED.value,
        }
        or bool(work_order.get("resource_reserved"))
    ):
        raise TransferError("linked work order is no longer eligible for a resource transfer")
    return work_order


@state_locked
def approve_transfer(transfer_id: str, actor: str = "logistics",
                     allow_reserve_override: bool = False) -> dict:
    """Release the donor's stock and put the transfer in transit.

    The minimum-reserve constraint is enforced here. An override is possible
    but must be explicit and is written to the audit trail (spec section 9).
    """
    transfer = TransferRepository.get(transfer_id)
    if transfer is None:
        raise TransferError("unknown transfer")
    if transfer["status"] != TransferStatus.PENDING_APPROVAL.value:
        raise TransferError(f"transfer {transfer_id} is {transfer['status']}, not pending approval")
    source_base, dest_base, part_number, quantity = _validate_transfer_structure(transfer)
    if transfer.get("work_order_id"):
        _validated_work_order(transfer)
        active = TransferRepository.active_for_work_order(transfer["work_order_id"])
        if active and active["id"] != transfer_id:
            raise TransferError("another active transfer already exists for this work order")

    inv = InventoryRepository.find(source_base, part_number)
    if inv is None:
        raise TransferError(f"{source_base} holds no {part_number}")

    try:
        condition = int(inv.get("condition_pct", 0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise TransferError(f"{source_base} has an invalid {part_number} condition") from exc
    min_condition = PartRepository.min_condition_pct(part_number)
    if condition < 0 or condition > 100:
        raise TransferError(f"{source_base} has an invalid {part_number} condition")
    if condition < min_condition:
        raise TransferError(
            f"{source_base} holds {part_number} at {condition}% condition; "
            f"the minimum serviceable condition is {min_condition}%"
        )

    quantity_before = int(inv["quantity"])
    after = quantity_before - quantity
    reserved = int(inv.get("reserved", 0))
    minimum = int(inv.get("minimum_reserve", 0))

    if quantity > int(inv["quantity"]) - reserved:
        raise TransferError(f"{source_base} does not have {quantity} unreserved unit(s)")

    # Minimum reserve is stock that remains transferable only after active
    # work-order reservations have been protected. Do not let an override
    # consume units already committed to maintenance.
    if after - reserved < minimum and not allow_reserve_override:
        raise TransferError(
            f"transfer would leave {source_base} with {after - reserved} "
            f"unreserved unit(s), below its minimum reserve of {minimum}; "
            "an authorised override is required"
        )
    InventoryRepository.update(inv["id"], quantity=after)
    refresh_line_status(InventoryRepository.get(inv["id"]))

    updated = TransferRepository.update(
        transfer_id, status=TransferStatus.IN_TRANSIT.value,
        started_at=_now(), condition_pct=condition,
    )
    if after - reserved < minimum:
        unreserved_before = quantity_before - reserved
        audit_service.reserve_override(
            transfer.get("work_order_id") or transfer["id"],
            source_base,
            actor=actor,
            transfer_id=transfer["id"],
            inventory_id=inv["id"],
            source_base=source_base,
            destination_base=dest_base,
            quantity_requested=quantity,
            quantity_before=quantity_before,
            unreserved_before=unreserved_before,
            available_for_transfer_before=max(0, unreserved_before - minimum),
            reserved_quantity=reserved,
            minimum_reserve=minimum,
            quantity_after=after,
            unreserved_after=after - reserved,
            available_for_transfer_after=max(0, after - reserved - minimum),
            reserve_floor_crossed=True,
            decision_outcome="APPROVED",
            resulting_transfer_status=TransferStatus.IN_TRANSIT.value,
        )
    audit_service.transfer_started(updated, actor=actor)

    return updated


@state_locked
def receive_transfer(transfer_id: str, actor: str = "logistics") -> dict:
    """Land the component at the destination and unblock the work order."""
    transfer = TransferRepository.get(transfer_id)
    if transfer is None:
        raise TransferError("unknown transfer")
    if transfer["status"] != TransferStatus.IN_TRANSIT.value:
        raise TransferError(f"transfer {transfer_id} is {transfer['status']}, not in transit")

    # Validate the shipment before creating or changing destination inventory.
    source_base, dest_base, part_number, quantity = _validate_transfer_structure(transfer)
    try:
        condition = int(transfer.get("condition_pct"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise TransferError("transfer dispatched condition is invalid") from exc
    if condition < 0 or condition > 100:
        raise TransferError("transfer dispatched condition is invalid")

    # A stale/closed linked order does not invalidate physical stock already
    # dispatched. Validate its relationship first, then avoid advancing it.
    linked_order = _validated_work_order(transfer, reject_unusable=False)
    dest_inv = InventoryRepository.find(dest_base, part_number)
    existing_quantity = int(dest_inv.get("quantity", 0)) if dest_inv else 0
    if dest_inv:
        try:
            existing_condition = int(dest_inv.get("condition_pct"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise TransferError("destination inventory condition is invalid") from exc
        if existing_condition < 0 or existing_condition > 100:
            raise TransferError("destination inventory condition is invalid")
        pooled_condition = min(existing_condition, condition) if existing_quantity > 0 else condition
    else:
        pooled_condition = condition

    if dest_inv is None:
        dest_inv = InventoryRepository.ensure_line(dest_base, part_number)
    InventoryRepository.set_quantity(
        dest_inv["id"], existing_quantity + quantity, condition_pct=pooled_condition,
    )

    updated = TransferRepository.update(transfer_id, status=TransferStatus.RECEIVED.value, received_at=_now())
    audit_service.transfer_received(updated, actor=actor)

    if updated.get("work_order_id"):
        work_order = WorkOrderRepository.get(updated["work_order_id"]) if linked_order else None
        if work_order and work_order["status"] in (
            WorkOrderStatus.WAITING_FOR_RESOURCE.value, WorkOrderStatus.SCHEDULED.value
        ):
            current_destination = InventoryRepository.find(dest_base, part_number)
            if (not current_destination
                    or available_for_transfer(current_destination) < 1
                    or int(current_destination.get("condition_pct", 0))
                    < PartRepository.min_condition_pct(part_number)):
                return updated
            previous_status = work_order["status"]
            new_status = WorkOrderStatus.RESOURCE_AVAILABLE.value
            changed = WorkOrderRepository.update(updated["work_order_id"], status=new_status, updated_at=_now())
            audit_service.work_order_status_changed(changed, previous_status, actor=actor)
            from .availability_service import sync_aircraft_states
            sync_aircraft_states()

    return updated


@state_locked
def cancel_transfer(transfer_id: str, reason: str | None = None, actor: str = "logistics") -> dict:
    transfer = TransferRepository.get(transfer_id)
    if transfer is None:
        raise TransferError("unknown transfer")
    if transfer["status"] == TransferStatus.CANCELLED.value:
        return transfer
    if transfer["status"] != TransferStatus.PENDING_APPROVAL.value:
        raise TransferError("only a pending transfer can be cancelled; in-transit stock has already left the source")
    updated = TransferRepository.update(transfer_id, status=TransferStatus.CANCELLED.value)
    audit_service.record(
        "TRANSFER_CANCELLED", "transfer", transfer_id,
        f"Transfer {transfer_id} cancelled", actor=actor, reason=reason,
    )
    return updated


@state_locked
def approve_recommendation(work_order_id: str, actor: str = "commander",
                           allow_reserve_override: bool = False,
                           donor_base: str | None = None) -> dict:
    """Human approval: turn the top recommendation into a real transfer.

    This is the point where the closed loop actually mutates state.
    """
    from . import recommendation_service
    from .recommendation_service import evaluate_candidates

    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        raise TransferError("unknown work order")
    received_transfer = next(
        (transfer for transfer in TransferRepository.list_for_work_order(work_order_id)
         if transfer.get("status") == TransferStatus.RECEIVED.value),
        None,
    )
    if received_transfer:
        raise TransferError("the work order's required resource has already arrived or maintenance has started")

    existing = TransferRepository.active_for_work_order(work_order_id)
    if existing:
        if existing["status"] == TransferStatus.IN_TRANSIT.value:
            evaluation = evaluate_candidates(work_order_id)
            return {"transfer": existing, "recommendation": evaluation, "work_order": work_order}
        raise TransferError("a transfer is already pending approval for this work order")

    if work_order.get("status") not in {
        WorkOrderStatus.OPEN.value,
        WorkOrderStatus.WAITING_FOR_RESOURCE.value,
    }:
        raise TransferError("the work order is no longer eligible for another resource transfer")

    evaluation = evaluate_candidates(work_order_id)

    recommended = evaluation.get("recommended")
    if not recommended:
        raise TransferError(
            f"no feasible source for {evaluation.get('required_component')} — "
            "the work order cannot be resourced"
        )

    source = donor_base or recommended["source_base"]
    selected = next((row for row in evaluation["candidates"] if row["base_id"] == source), None)
    if selected is None:
        raise TransferError("selected donor is not a feasible recommendation candidate")
    inv = InventoryRepository.find(source, evaluation["required_component"])
    if inv is None or int(inv["quantity"]) - int(inv.get("reserved", 0)) < 1:
        raise TransferError(f"{source} no longer has an unreserved unit available")
    if (int(inv["quantity"]) - 1 < int(inv.get("minimum_reserve", 0))
            and not allow_reserve_override):
        raise TransferError(f"{source} cannot transfer without an authorised reserve override")

    transfer = create_transfer(
        part_number=evaluation["required_component"],
        source_base=source,
        dest_base=evaluation["home_base"],
        quantity=1,
        for_aircraft=work_order["aircraft_id"],
        work_order_id=work_order_id,
        # A commander-approved recommendation is authorised to move.
        status=TransferStatus.PENDING_APPROVAL.value,
        condition_pct=selected.get("condition_pct"),
        actor=actor,
    )

    # Approval implies release: move it straight into transit.
    approved = approve_transfer(transfer["id"], actor=actor,
                                allow_reserve_override=allow_reserve_override)
    recommendation_service.record_recommendation_evaluation(
        work_order_id, evaluation, actor=actor,
    )
    audit_service.recommendation_approved(
        work_order_id, transfer["id"], actor=actor,
        source_base=source, destination_base=evaluation["home_base"],
        expected_downtime_hours=selected.get("expected_downtime_hours"),
        score=selected.get("score"),
    )
    return {"transfer": approved, "recommendation": evaluation,
            "work_order": WorkOrderRepository.get(work_order_id)}


def transfer_summary(transfer: dict) -> dict:
    inv = InventoryRepository.find(transfer["source_base"], transfer["part_number"])
    return {
        **transfer,
        "part_name": PartRepository.name(transfer["part_number"]),
        "source_available_after": available_for_transfer(inv) if inv else 0,
        "source_minimum_reserve": int(inv.get("minimum_reserve", 0)) if inv else 0,
    }
