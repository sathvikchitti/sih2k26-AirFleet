"""Maintenance persistence: predicted maintenance events and work orders.

Two distinct concepts, deliberately not merged (spec sections 3-5):

  PredictedMaintenanceEvent — "the model says this airframe is degrading".
  MaintenanceWorkOrder     — "operations have committed to work on it".

Only a triage action converts one into the other.
"""

from __future__ import annotations

from ..domain.enums import MaintenanceEventStatus, WorkOrderStatus
from .store import lock, next_id, store

OPEN_WORK_ORDER_STATUSES = frozenset({
    WorkOrderStatus.OPEN.value,
    WorkOrderStatus.WAITING_FOR_RESOURCE.value,
    WorkOrderStatus.RESOURCE_AVAILABLE.value,
    WorkOrderStatus.SCHEDULED.value,
    WorkOrderStatus.IN_PROGRESS.value,
})

UNRESOLVED_EVENT_STATUSES = frozenset({
    MaintenanceEventStatus.OPEN.value,
    MaintenanceEventStatus.TRIAGED.value,
})


class EventRepository:
    """Predicted maintenance events."""

    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["predicted_events"])

    @staticmethod
    def get(event_id: str) -> dict | None:
        key = str(event_id).upper()
        return next((e for e in store()["predicted_events"] if e["id"].upper() == key), None)

    @staticmethod
    def find_by_aircraft(aircraft_id: str) -> list[dict]:
        key = str(aircraft_id).upper()
        return [e for e in store()["predicted_events"] if e["aircraft_id"] == key]

    @staticmethod
    def find_unresolved(aircraft_id: str) -> dict | None:
        for e in EventRepository.find_by_aircraft(aircraft_id):
            if e["status"] in UNRESOLVED_EVENT_STATUSES:
                return e
        return None

    @staticmethod
    def create(**fields) -> dict:
        with lock():
            event = {"id": next_id("event_seq", "PM-", 3), **fields}
            store()["predicted_events"].append(event)
            return event

    @staticmethod
    def update(event_id: str, **fields) -> dict | None:
        ev = EventRepository.get(event_id)
        if ev is None:
            return None
        with lock():
            ev.update(fields)
        return ev


class WorkOrderRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["work_orders"])

    @staticmethod
    def get(work_order_id: str) -> dict | None:
        key = str(work_order_id).upper()
        return next((w for w in store()["work_orders"] if w["id"].upper() == key), None)

    @staticmethod
    def list_by_aircraft(aircraft_id: str) -> list[dict]:
        key = str(aircraft_id).upper()
        return [w for w in store()["work_orders"] if w["aircraft_id"] == key]

    @staticmethod
    def open_for_aircraft(aircraft_id: str) -> list[dict]:
        return [w for w in WorkOrderRepository.list_by_aircraft(aircraft_id)
                if w["status"] in OPEN_WORK_ORDER_STATUSES]

    @staticmethod
    def list_open() -> list[dict]:
        return [w for w in store()["work_orders"] if w["status"] in OPEN_WORK_ORDER_STATUSES]

    @staticmethod
    def find_by_component(part_number: str) -> list[dict]:
        key = str(part_number).upper()
        return [w for w in store()["work_orders"]
                if str(w.get("required_component") or "").upper() == key]

    @staticmethod
    def find_by_event(event_id: str) -> dict | None:
        key = str(event_id).upper()
        return next((w for w in store()["work_orders"]
                     if str(w.get("predicted_event_id") or "").upper() == key), None)

    @staticmethod
    def create(**fields) -> dict:
        with lock():
            wo = {"id": next_id("work_order_seq", "WO-", 4), **fields}
            store()["work_orders"].append(wo)
            return wo

    @staticmethod
    def update(work_order_id: str, **fields) -> dict | None:
        wo = WorkOrderRepository.get(work_order_id)
        if wo is None:
            return None
        with lock():
            wo.update(fields)
        return wo