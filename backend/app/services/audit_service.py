"""Audit trail (spec section 18).

A generic, append-only event log. Callers record *what* happened and the
services decide *why it matters*; nothing here is UI-specific, so the same log
can drive an operator timeline, a compliance export, or an analytics pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain.enums import AuditEventType
from ..repositories import AuditRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(event_type: str | AuditEventType, entity_type: str, entity_id: str,
           summary: str, actor: str = "system", **details) -> dict:
    """Append one audit event. Returns the stored row."""
    kind = event_type.value if isinstance(event_type, AuditEventType) else str(event_type)
    return AuditRepository.append(
        event_type=kind,
        occurred_at=_now(),
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        actor=actor,
        details=details or {},
    )


def prediction_generated(aircraft_id: str, prediction: dict, actor: str = "ml-service",
                        prediction_history_id: str | None = None) -> dict:
    return record(
        AuditEventType.PREDICTION_GENERATED, "aircraft", aircraft_id,
        f"Prediction generated for {aircraft_id} ({prediction.get('source', 'ml')})",
        actor=actor,
        health_score=prediction.get("health_score"),
        risk_level=prediction.get("risk_level"),
        rul=prediction.get("rul"),
        subsystem=prediction.get("subsystem"),
        prediction_history_id=prediction_history_id,
    )


def maintenance_event_created(event: dict, actor: str = "system") -> dict:
    return record(
        AuditEventType.MAINTENANCE_EVENT_CREATED, "predicted_maintenance_event", event["id"],
        f"Maintenance event created for {event['aircraft_id']} from prediction",
        actor=actor, risk_level=event.get("risk_level"), subsystem=event.get("subsystem"),
        prediction_history_id=event.get("prediction_history_id"),
    )


def work_order_created(work_order: dict, actor: str = "system") -> dict:
    requires = work_order.get("required_component") or "no component"
    return record(
        AuditEventType.WORK_ORDER_CREATED, "work_order", work_order["id"],
        f"Work order {work_order['id']} created for {work_order['aircraft_id']} — requires {requires}",
        actor=actor,
        predicted_event_id=work_order.get("predicted_event_id"),
        source=work_order.get("source"),
        required_component=work_order.get("required_component"),
        component_source=work_order.get("component_source"),
    )


def work_order_status_changed(work_order: dict, previous: str, actor: str = "system") -> dict:
    return record(
        AuditEventType.WORK_ORDER_STATUS_CHANGED, "work_order", work_order["id"],
        f"Work order {work_order['id']} moved {previous} -> {work_order['status']}",
        actor=actor, previous_status=previous, status=work_order["status"],
    )


def recommendation_generated(work_order_id: str, candidates: int,
                             recommended: dict | bool, actor: str = "system") -> dict:
    recommended_candidate = None
    if isinstance(recommended, dict):
        recommended_candidate = {
            key: recommended.get(key)
            for key in ("source_base", "destination_base", "part_number", "eta_hours",
                        "expected_downtime_hours", "score")
        }
    return record(
        AuditEventType.RECOMMENDATION_GENERATED, "work_order", work_order_id,
        f"Recommendation generated for {work_order_id}",
        actor=actor, candidates=candidates,
        has_recommendation=bool(recommended), recommended_candidate=recommended_candidate,
    )


def recommendation_approved(work_order_id: str, transfer_id: str, actor: str = "commander", **extra) -> dict:
    return record(
        AuditEventType.RECOMMENDATION_APPROVED, "work_order", work_order_id,
        f"Commander approved transfer {transfer_id} for {work_order_id}",
        actor=actor, transfer_id=transfer_id, **extra,
    )


def recommendation_rejected(work_order_id: str, actor: str = "commander", reason: str | None = None) -> dict:
    return record(
        AuditEventType.RECOMMENDATION_REJECTED, "work_order", work_order_id,
        f"Recommendation for {work_order_id} rejected",
        actor=actor, reason=reason,
    )


def inventory_updated(inventory: dict, before: dict, after: dict,
                      actor: str = "logistics") -> dict:
    changed_fields = {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in ("quantity", "reserved", "minimum_reserve", "condition_pct", "status")
        if before.get(key) != after.get(key)
    }
    return record(
        AuditEventType.INVENTORY_UPDATED, "inventory", inventory["id"],
        f"Inventory {inventory['part_number']} at {inventory['base_id']} updated",
        actor=actor, base_id=inventory["base_id"], part_number=inventory["part_number"],
        changed_fields=changed_fields,
    )


def transfer_created(transfer: dict, actor: str = "logistics") -> dict:
    return record(
        AuditEventType.TRANSFER_CREATED, "transfer", transfer["id"],
        f"Transfer {transfer['id']} created: {transfer['part_number']} "
        f"{transfer['source_base']} -> {transfer['dest_base']}",
        actor=actor, status=transfer.get("status"), work_order_id=transfer.get("work_order_id"),
    )


def transfer_started(transfer: dict, actor: str = "logistics") -> dict:
    return record(
        AuditEventType.TRANSFER_STARTED, "transfer", transfer["id"],
        f"{transfer['part_number']} marked IN_TRANSIT ({transfer['source_base']} -> {transfer['dest_base']})",
        actor=actor, work_order_id=transfer.get("work_order_id"),
    )


def transfer_received(transfer: dict, actor: str = "logistics") -> dict:
    return record(
        AuditEventType.TRANSFER_RECEIVED, "transfer", transfer["id"],
        f"{transfer['part_number']} received at {transfer['dest_base']}",
        actor=actor, work_order_id=transfer.get("work_order_id"),
    )


def maintenance_started(work_order: dict, actor: str = "base") -> dict:
    return record(
        AuditEventType.MAINTENANCE_STARTED, "work_order", work_order["id"],
        f"Maintenance started on {work_order['aircraft_id']}",
        actor=actor, aircraft_id=work_order["aircraft_id"],
    )


def maintenance_completed(work_order: dict, actor: str = "base") -> dict:
    return record(
        AuditEventType.MAINTENANCE_COMPLETED, "work_order", work_order["id"],
        f"Maintenance completed on {work_order['aircraft_id']}",
        actor=actor, aircraft_id=work_order["aircraft_id"],
    )


def aircraft_returned_to_service(aircraft_id: str, actor: str = "system") -> dict:
    return record(
        AuditEventType.AIRCRAFT_RETURNED_TO_SERVICE, "aircraft", aircraft_id,
        f"{aircraft_id} returned to AVAILABLE",
        actor=actor,
    )


def reserve_override(
    work_order_id: str,
    donor_base: str,
    actor: str = "commander",
    *,
    transfer_id: str | None = None,
    inventory_id: str | None = None,
    source_base: str | None = None,
    destination_base: str | None = None,
    quantity_requested: int | None = None,
    quantity_before: int | None = None,
    unreserved_before: int | None = None,
    available_for_transfer_before: int | None = None,
    reserved_quantity: int | None = None,
    minimum_reserve: int | None = None,
    quantity_after: int | None = None,
    unreserved_after: int | None = None,
    available_for_transfer_after: int | None = None,
    reserve_floor_crossed: bool = True,
    decision_outcome: str = "APPROVED",
    resulting_transfer_status: str = "IN_TRANSIT",
) -> dict:
    """Record a successful minimum-reserve override with dispatch context.

    The actor is the role resolved by the API boundary (or the explicit actor
    passed by a trusted internal workflow). This event is emitted only for a
    successful dispatch that crosses the configured reserve floor.
    """
    return record(
        AuditEventType.RESERVE_OVERRIDE_APPLIED, "work_order", work_order_id,
        f"Minimum reserve overridden at {donor_base} by authorised human",
        actor=actor,
        actor_role=actor,
        donor_base=donor_base,
        transfer_id=transfer_id,
        inventory_id=inventory_id,
        source_base=source_base,
        destination_base=destination_base,
        quantity_requested=quantity_requested,
        quantity_before=quantity_before,
        unreserved_before=unreserved_before,
        available_for_transfer_before=available_for_transfer_before,
        reserved_quantity=reserved_quantity,
        minimum_reserve=minimum_reserve,
        quantity_after=quantity_after,
        unreserved_after=unreserved_after,
        available_for_transfer_after=available_for_transfer_after,
        reserve_floor_crossed=reserve_floor_crossed,
        decision_outcome=decision_outcome,
        resulting_transfer_status=resulting_transfer_status,
    )


def demo_reset(actor: str = "system") -> dict:
    return record(AuditEventType.DEMO_RESET, "system", "demo", "Demo state reset", actor=actor)


def timeline(entity_id: str | None = None, limit: int | None = None) -> list[dict]:
    """Chronological audit feed, oldest first."""
    return AuditRepository.query(entity_id=entity_id, limit=limit)
