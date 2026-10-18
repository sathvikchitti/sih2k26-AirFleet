"""Aircraft persistence."""

from __future__ import annotations

from .store import lock, store


class AircraftRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["aircraft"])

    @staticmethod
    def get(aircraft_id: str) -> dict | None:
        key = str(aircraft_id).upper()
        return next((a for a in store()["aircraft"] if a["id"] == key), None)

    @staticmethod
    def list_by_base(base_id: str) -> list[dict]:
        return [a for a in store()["aircraft"] if a["base_id"] == base_id]

    @staticmethod
    def list_by_ids(ids) -> list[dict]:
        wanted = {str(i).upper() for i in ids}
        return [a for a in store()["aircraft"] if a["id"] in wanted]

    @staticmethod
    def update(aircraft_id: str, **fields) -> dict | None:
        ac = AircraftRepository.get(aircraft_id)
        if ac is None:
            return None
        with lock():
            ac.update(fields)
        return ac

    @staticmethod
    def all_ids() -> list[str]:
        return [a["id"] for a in store()["aircraft"]]