"""Maintenance service: predictions, predicted events, work orders, lifecycle.

The separation the spec insists on (sections 3-4) is enforced here:

    prediction  --(ingest)-->  PredictedMaintenanceEvent  --(triage)-->  WorkOrder

A prediction never becomes a work order on its own. `ingest_prediction()`
records the ML output as an event; only `create_work_order_from_event()` —
an explicit human/planner action — commits maintenance effort.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from ..domain import knowledge
from ..domain.enums import (
    MaintenanceEventStatus,
    MaintenanceSource,
    Priority,
    WorkOrderStatus,
)
from ..repositories import (
    AircraftRepository,
    EventRepository,
    InventoryRepository,
    PartRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
    refresh_line_status,
)
from ..repositories.store import state_locked
from . import audit_service
from .ml import get_provider, predict_validated


class MaintenanceTransitionError(ValueError):
    """A requested work-order transition failed its lifecycle prerequisites."""


class ManualWorkOrderValidationError(ValueError):
    """A manually supplied work-order field is outside the domain contract."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Prediction
# --------------------------------------------------------------------------
def get_prediction(aircraft_id: str) -> dict | None:
    """ML prediction plus the knowledge-layer interpretation.

    The `maintenance` block is derived by the knowledge layer, not the model:
    `required_component` is left null when no rule matches.
    """
    if AircraftRepository.get(aircraft_id) is None:
        return None
    pred = predict_validated(get_provider(), aircraft_id)
    knowledge_view = _knowledge_view(pred)
    return {**pred, "maintenance": knowledge_view}


def _knowledge_view(pred: dict) -> dict:
    res = knowledge.resolve(pred.get("subsystem"), pred.get("predicted_issue"))
    return {
        "rule_matched": res.matched,
        "maintenance_action": res.maintenance_action,
        "candidate_components": list(res.candidate_components),
        # Only set when the knowledge layer is confident: the recommendation
        # engine still decides which base actually has the part.
        "required_component": res.candidate_components[0] if res.matched and res.candidate_components else None,
        "reason": res.reason,
    }


def prediction_history(aircraft_id: str) -> list[dict]:
    from ..repositories import PredictionHistoryRepository
    return PredictionHistoryRepository.for_aircraft(aircraft_id)


# --------------------------------------------------------------------------
# Predicted maintenance events
# --------------------------------------------------------------------------
def ingest_prediction(aircraft_id: str, actor: str = "system") -> dict | None:
    """Turn a fresh ML prediction into a predicted maintenance event.

    Idempotent: an unresolved event for the airframe is reused rather than
    duplicated. Records an audit entry for the prediction either way.
    """
    ac = AircraftRepository.get(aircraft_id)
    if ac is None:
        return None

    pred = predict_validated(get_provider(), ac["id"])
    from ..repositories import PredictionHistoryRepository
    history_id = f"PH-{ac['id']}-{pred['model_version']}-{pred['prediction_timestamp']}"
    history_row = PredictionHistoryRepository.append(
        id=history_id,
        aircraft_id=ac["id"], timestamp=pred["prediction_timestamp"],
        health_score=pred["health_score"], risk_level=pred["risk_level"],
        failure_probability=pred["failure_probability"], rul=pred.get("rul"),
        rul_unit=pred.get("rul_unit"), confidence=pred.get("confidence"),
        prediction_horizon_hours=pred["prediction_horizon_hours"],
        model_version=pred["model_version"], source=pred.get("source", "ml-provider"),
        history_source="recorded",
        is_synthetic=bool(pred.get("is_synthetic", str(pred.get("source", "")).startswith("mock-"))),
    )
    history_id = history_row["id"]
    audit_service.prediction_generated(ac["id"], pred, prediction_history_id=history_id)

    if not pred.get("predicted_maintenance"):
        return None

    existing = EventRepository.find_unresolved(ac["id"])
    if existing:
        history_ids = list(existing.get("prediction_history_ids") or [])
        if history_id not in history_ids:
            history_ids.append(history_id)
        EventRepository.update(
            existing["id"],
            risk_level=pred.get("risk_level"),
            rul=pred.get("rul"),
            rul_unit=pred.get("rul_unit"),
            predicted_time=iso_in_rul(pred.get("rul"), rul_unit=pred.get("rul_unit", "flight_hours")),
            confidence=pred.get("confidence"),
            health_score=pred.get("health_score"),
            prediction_history_id=existing.get("prediction_history_id"),
            prediction_history_origin_status=(
                existing.get("prediction_history_origin_status")
                or ("recorded_at_creation" if existing.get("prediction_history_id") else "legacy_unknown")
            ),
            latest_prediction_history_id=history_id,
            prediction_history_ids=history_ids,
            updated_at=_now(),
        )
        return EventRepository.get(existing["id"])

    now = _now()
    event = EventRepository.create(
        aircraft_id=ac["id"],
        prediction_id=f"{ac['id']}@{pred.get('timestamp')}",
        prediction_history_id=history_id,
        prediction_history_origin_status="recorded_at_creation",
        latest_prediction_history_id=history_id,
        prediction_history_ids=[history_id],
        predicted_issue=pred.get("predicted_issue"),
        subsystem=pred.get("subsystem"),
        risk_level=pred.get("risk_level"),
        rul=pred.get("rul"),
        confidence=pred.get("confidence"),
        health_score=pred.get("health_score"),
        predicted_time=iso_in_rul(pred.get("rul"), rul_unit=pred.get("rul_unit", "flight_hours")),
        rul_unit=pred.get("rul_unit"),
        required_resource_type="COMPONENT",
        status=MaintenanceEventStatus.OPEN.value,
        work_order_id=None,
        created_at=now,
        updated_at=now,
    )
    audit_service.maintenance_event_created(event)
    return event


def iso_in_rul(rul: float | None, speed: float = 10.0,
               rul_unit: str = "flight_hours") -> str | None:
    """Project flight-hour RUL onto a wall-clock instant (POC assumption).

    Cycle-based predictions do not imply a calendar deadline, so their
    projected timestamp is intentionally unavailable.
    """
    if rul is None or rul_unit != "flight_hours":
        return None
    return (datetime.now(timezone.utc) + timedelta(hours=float(rul) / speed)).isoformat()


@state_locked
def dismiss_event(event_id: str, reason: str | None = None, actor: str = "commander") -> dict | None:
    event = EventRepository.get(event_id)
    if event is None:
        return None
    if event["status"] != MaintenanceEventStatus.OPEN.value:
        return event
    updated = EventRepository.update(
        event_id,
        status=MaintenanceEventStatus.DISMISSED.value,
        updated_at=_now(),
    )
    audit_service.record(
        "MAINTENANCE_EVENT_DISMISSED", "predicted_maintenance_event", event_id,
        f"Maintenance event {event_id} dismissed", actor=actor, reason=reason,
    )
    return updated


# --------------------------------------------------------------------------
# Work orders
# --------------------------------------------------------------------------
@state_locked
def create_work_order_from_event(event_id: str, required_component: str | None = None,
                                 actor: str = "commander") -> dict | None:
    """Triage a predicted event into a committed work order.

    `required_component` may be supplied by the operator. It must exist in the
    part catalogue. If a maintenance rule matched, the selection must also be
    one of that rule's candidates. For an unmatched FD001 RUL event, any
    catalogue part may be selected explicitly; this demo has no aircraft-level
    engineering compatibility/airworthiness data to validate that choice.
    """
    event = EventRepository.get(event_id)
    if event is None:
        return None
    if event["status"] == MaintenanceEventStatus.WORK_ORDER_CREATED.value:
        return WorkOrderRepository.get(event["work_order_id"])
    if event["status"] != MaintenanceEventStatus.OPEN.value:
        return None

    ac = AircraftRepository.get(event["aircraft_id"])
    if ac is None:
        return None

    res = knowledge.resolve(event.get("subsystem"), event.get("predicted_issue"))
    component = (required_component or (res.candidate_components[0] if res.candidate_components else None))
    if component is None:
        # No knowledge rule matched: we cannot infer what to fix. Signal this
        # rather than inventing a part.
        return None
    component = str(component).strip().upper()
    if PartRepository.get(component) is None:
        raise MaintenanceTransitionError(f"unknown component {component!r}; select a catalogued part")
    if res.matched and component not in {str(candidate).upper() for candidate in res.candidate_components}:
        raise MaintenanceTransitionError(
            f"component {component} is not a candidate for the matched maintenance rule"
        )

    now = _now()
    work_order = WorkOrderRepository.create(
        aircraft_id=ac["id"],
        base_id=ac["base_id"],
        priority=str(res.default_priority or knowledge.priority_for_risk(event.get("risk_level"))),
        source=MaintenanceSource.PREDICTED_MAINTENANCE.value,
        predicted_event_id=event["id"],
        issue=event.get("predicted_issue"),
        maintenance_action=res.maintenance_action,
        required_component=component,
        component_source="human_selected" if required_component else "knowledge_rule",
        status=_initial_status(component, ac["base_id"]),
        estimated_repair_hours=res.estimated_repair_hours or 4.0,
        required_by_flight_hours=(event.get("rul") if event.get("rul_unit", "flight_hours") == "flight_hours" else None),
        required_by_rul=event.get("rul"),
        rul_unit=event.get("rul_unit", "flight_hours"),
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )

    EventRepository.update(
        event["id"],
        status=MaintenanceEventStatus.WORK_ORDER_CREATED.value,
        work_order_id=work_order["id"],
        updated_at=now,
    )
    audit_service.work_order_created(work_order, actor=actor)
    from .availability_service import sync_aircraft_states
    sync_aircraft_states()
    return work_order


def _initial_status(component: str | None, base_id: str) -> str:
    """A work order starts WAITING_FOR_RESOURCE only if the part isn't on hand."""
    if not component:
        return WorkOrderStatus.OPEN.value
    inv = InventoryRepository.find(base_id, component)
    if (inv and available_for_transfer(inv) > 0
            and int(inv.get("condition_pct", 0)) >= PartRepository.min_condition_pct(component)):
        return WorkOrderStatus.RESOURCE_AVAILABLE.value
    return WorkOrderStatus.WAITING_FOR_RESOURCE.value


@state_locked
def create_manual_work_order(aircraft_id: str, component: str | None,
                             issue: str = "Manually raised work order",
                             estimated_repair_hours: float = 4.0,
                             priority: str = Priority.MEDIUM.value,
                             actor: str = "base") -> dict | None:
    """Raise a work order not derived from a prediction."""
    normalized_component = None
    if component is not None:
        normalized_component = str(component).strip().upper()
        if not normalized_component or PartRepository.get(normalized_component) is None:
            raise ManualWorkOrderValidationError(
                f"unknown component {component!r}; select a catalogued part"
            )

    normalized_priority = str(priority).strip().upper()
    if normalized_priority not in {item.value for item in Priority}:
        allowed = ", ".join(item.value for item in Priority)
        raise ManualWorkOrderValidationError(f"priority must be one of: {allowed}")

    if isinstance(estimated_repair_hours, bool):
        raise ManualWorkOrderValidationError("estimated_repair_hours must be finite and positive")
    try:
        repair_hours = float(estimated_repair_hours)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ManualWorkOrderValidationError(
            "estimated_repair_hours must be finite and positive"
        ) from exc
    if not math.isfinite(repair_hours) or repair_hours <= 0:
        raise ManualWorkOrderValidationError("estimated_repair_hours must be finite and positive")

    ac = AircraftRepository.get(aircraft_id)
    if ac is None:
        return None
    now = _now()
    work_order = WorkOrderRepository.create(
        aircraft_id=ac["id"],
        base_id=ac["base_id"],
        priority=normalized_priority,
        source=MaintenanceSource.MANUAL.value,
        predicted_event_id=None,
        issue=issue,
        maintenance_action=issue,
        required_component=normalized_component,
        component_source="human_selected" if normalized_component else "unselected",
        status=_initial_status(normalized_component, ac["base_id"]),
        estimated_repair_hours=repair_hours,
        required_by_flight_hours=None,
        required_by_rul=None,
        rul_unit=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    audit_service.work_order_created(work_order, actor=actor)
    from .availability_service import sync_aircraft_states
    sync_aircraft_states()
    return work_order


def set_status(work_order_id: str, status: str, actor: str = "system") -> dict | None:
    """Transition a work order and keep the aircraft state in step."""
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        return None
    previous = work_order["status"]
    if previous == status:
        return work_order
    updated = WorkOrderRepository.update(work_order_id, status=status, updated_at=_now())
    audit_service.work_order_status_changed(updated, previous, actor=actor)
    from .availability_service import sync_aircraft_states
    sync_aircraft_states()
    return updated


@state_locked
def start_maintenance(work_order_id: str, actor: str = "base") -> dict | None:
    """Begin the repair. Requires the resource to have arrived."""
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        return None
    if work_order["status"] == WorkOrderStatus.IN_PROGRESS.value:
        return work_order
    if work_order["status"] not in (
        WorkOrderStatus.RESOURCE_AVAILABLE.value, WorkOrderStatus.SCHEDULED.value
    ):
        raise MaintenanceTransitionError(
            f"work order is {work_order['status']}; required resource must arrive first"
        )
    previous_status = work_order["status"]
    component = work_order.get("required_component")
    reserved_inventory = None
    if component:
        inv = InventoryRepository.find(work_order["base_id"], component)
        if not inv or available_for_transfer(inv) <= 0:
            raise MaintenanceTransitionError("required component is not available at the work location")
        minimum_condition = PartRepository.min_condition_pct(component)
        if int(inv.get("condition_pct", 0)) < minimum_condition:
            raise MaintenanceTransitionError(
                f"required component condition is below the {minimum_condition}% minimum"
            )
        reserved_inventory = InventoryRepository.update(
            inv["id"], reserved=int(inv.get("reserved", 0)) + 1
        )
        refresh_line_status(reserved_inventory)

    updated = WorkOrderRepository.update(
        work_order_id,
        status=WorkOrderStatus.IN_PROGRESS.value,
        started_at=_now(),
        updated_at=_now(),
        resource_reserved=bool(reserved_inventory),
    )
    AircraftRepository.update(work_order["aircraft_id"], status="MAINTENANCE")
    audit_service.maintenance_started(updated, actor=actor)
    audit_service.work_order_status_changed(updated, previous_status, actor=actor)
    from .availability_service import sync_aircraft_states
    sync_aircraft_states()
    return updated


@state_locked
def complete_maintenance(work_order_id: str, actor: str = "base") -> dict | None:
    """Sign the work off and return the airframe to service."""
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        return None
    if work_order["status"] == WorkOrderStatus.COMPLETED.value:
        return work_order
    if work_order["status"] != WorkOrderStatus.IN_PROGRESS.value:
        raise MaintenanceTransitionError("maintenance must be started before it can be completed")
    previous_status = work_order["status"]
    component = work_order.get("required_component")
    inv = InventoryRepository.find(work_order["base_id"], component) if component else None
    has_reserved_resource = bool(work_order.get("resource_reserved"))
    if component and (not inv or int(inv.get("quantity", 0)) < 1
                      or (has_reserved_resource and int(inv.get("reserved", 0)) < 1)
                      or (not has_reserved_resource and available_for_transfer(inv) <= 0)):
        raise MaintenanceTransitionError("required component is unavailable for consumption")

    updated = WorkOrderRepository.update(
        work_order_id,
        status=WorkOrderStatus.COMPLETED.value,
        completed_at=_now(),
        updated_at=_now(),
    )

    # The resource is consumed by the repair.
    if component:
        if inv:
            InventoryRepository.update(
                inv["id"], quantity=int(inv["quantity"]) - 1,
                reserved=max(0, int(inv.get("reserved", 0)) - int(has_reserved_resource)),
            )
            refresh_line_status(InventoryRepository.get(inv["id"]))

    event = EventRepository.get(work_order.get("predicted_event_id") or "")
    if event:
        EventRepository.update(event["id"], status=MaintenanceEventStatus.RESOLVED.value, updated_at=_now())

    audit_service.maintenance_completed(updated, actor=actor)
    audit_service.work_order_status_changed(updated, previous_status, actor=actor)

    aircraft_id = work_order["aircraft_id"]
    # Only return to service if nothing else is still open on the airframe.
    remaining = WorkOrderRepository.open_for_aircraft(aircraft_id)
    from .availability_service import sync_aircraft_states
    changed = sync_aircraft_states()
    if not remaining and AircraftRepository.get(aircraft_id)["status"] == "AVAILABLE":
        audit_service.aircraft_returned_to_service(aircraft_id, actor=actor)
    return updated


def work_order_summary(work_order: dict) -> dict:
    """Denormalised view used by list endpoints."""
    transfer = TransferRepository.active_for_work_order(work_order["id"])
    inv = InventoryRepository.find(work_order["base_id"], work_order.get("required_component") or "")
    on_hand = available_for_transfer(inv) if inv else 0
    return {
        **work_order,
        "component_name": PartRepository.name(work_order.get("required_component") or ""),
        "required_resource_available": on_hand > 0,
        "active_transfer_id": transfer["id"] if transfer else None,
    }
