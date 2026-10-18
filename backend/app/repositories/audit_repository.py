"""Prediction-history and audit-log persistence (spec sections 16 and 18)."""

from __future__ import annotations

from .store import lock, next_id, store


class PredictionHistoryRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["prediction_history"])

    @staticmethod
    def for_aircraft(aircraft_id: str) -> list[dict]:
        key = str(aircraft_id).upper()
        rows = [p for p in store()["prediction_history"] if p["aircraft_id"] == key]
        return sorted(rows, key=lambda p: p["timestamp"])

    @staticmethod
    def latest(aircraft_id: str) -> dict | None:
        rows = PredictionHistoryRepository.for_aircraft(aircraft_id)
        return rows[-1] if rows else None

    @staticmethod
    def append(**fields) -> dict:
        with lock():
            for existing in store()["prediction_history"]:
                if (existing.get("aircraft_id") == fields.get("aircraft_id")
                        and existing.get("timestamp") == fields.get("timestamp")
                        and existing.get("model_version") == fields.get("model_version")):
                    return existing
            store()["prediction_history"].append(fields)
        return fields


class AuditRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["audit"])

    @staticmethod
    def append(**fields) -> dict:
        with lock():
            row = {"id": next_id("audit_seq", "AE-", 4), **fields}
            store()["audit"].append(row)
            return row

    @staticmethod
    def query(entity_id: str | None = None, event_type: str | None = None,
              entity_type: str | None = None, limit: int | None = None) -> list[dict]:
        rows = AuditRepository.list_all()
        if entity_id:
            rows = [r for r in rows if r.get("entity_id") == entity_id]
        if entity_type:
            rows = [r for r in rows if r.get("entity_type") == entity_type]
        if event_type:
            rows = [r for r in rows if r.get("event_type") == event_type]
        rows = sorted(rows, key=lambda r: (r.get("occurred_at") or "", r.get("id") or ""))
        return rows[-limit:] if limit else rows
