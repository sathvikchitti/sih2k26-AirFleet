"""Transfer persistence."""

from __future__ import annotations

from ..domain.enums import TransferStatus
from .store import lock, next_id, store

ACTIVE_TRANSFER_STATUSES = frozenset({
    TransferStatus.PENDING_APPROVAL.value,
    TransferStatus.IN_TRANSIT.value,
})


class TransferRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["transfers"])

    @staticmethod
    def get(transfer_id: str) -> dict | None:
        key = str(transfer_id).upper()
        return next((t for t in store()["transfers"] if t["id"].upper() == key), None)

    @staticmethod
    def list_for_work_order(work_order_id: str) -> list[dict]:
        return [t for t in store()["transfers"] if t.get("work_order_id") == work_order_id]

    @staticmethod
    def active_for_work_order(work_order_id: str) -> dict | None:
        """The transfer currently moving a work order's resource, if any."""
        for t in TransferRepository.list_for_work_order(work_order_id):
            if t["status"] in ACTIVE_TRANSFER_STATUSES:
                return t
        return None

    @staticmethod
    def active_for_aircraft(aircraft_id: str) -> dict | None:
        key = str(aircraft_id).upper()
        for t in store()["transfers"]:
            if t.get("for_aircraft") == key and t["status"] in ACTIVE_TRANSFER_STATUSES:
                return t
        return None

    @staticmethod
    def create(**fields) -> dict:
        with lock():
            t = {"id": next_id("transfer_seq", "T-", 3), **fields}
            store()["transfers"].append(t)
            return t

    @staticmethod
    def update(transfer_id: str, **fields) -> dict | None:
        t = TransferRepository.get(transfer_id)
        if t is None:
            return None
        with lock():
            t.update(fields)
        return t