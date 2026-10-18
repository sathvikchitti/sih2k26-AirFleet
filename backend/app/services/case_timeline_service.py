"""Read-only maintenance case assembly using explicit stored identifiers."""

from __future__ import annotations

from datetime import datetime, timezone

from ..repositories.store import snapshot


DECISION_TYPES = {"RECOMMENDATION_APPROVED", "RECOMMENDATION_REJECTED"}


def _event_time(row: dict) -> str | None:
    value = row.get("occurred_at") or row.get("timestamp") or row.get("created_at")
    return str(value) if value else None


def _sort_time(value: str | None) -> tuple[int, datetime, str]:
    if not value:
        return (1, datetime.max.replace(tzinfo=timezone.utc), "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (0, parsed.astimezone(timezone.utc), value)
    except (TypeError, ValueError):
        return (1, datetime.max.replace(tzinfo=timezone.utc), value)


def maintenance_case_timeline(aircraft_id: str, work_order_id: str | None = None) -> dict | None:
    """Return records related by IDs; do not infer links from timestamp proximity."""
    state = snapshot()
    key = str(aircraft_id).upper()
    aircraft = next((row for row in state.get("aircraft", []) if row.get("id") == key), None)
    if aircraft is None:
        return None

    all_work_orders = [row for row in state.get("work_orders", [])
                       if row.get("aircraft_id") == aircraft["id"]]
    if work_order_id:
        selected = next((row for row in state.get("work_orders", [])
                         if str(row.get("id", "")).upper() == str(work_order_id).upper()), None)
        if selected is None or selected.get("aircraft_id") != aircraft["id"]:
            return {"error": "unknown or mismatched work order"}
        work_orders = [selected]
        work_order_id = selected["id"]
    else:
        work_orders = all_work_orders
    wo_ids = {row["id"] for row in work_orders}

    aircraft_events = [row for row in state.get("predicted_events", [])
                       if row.get("aircraft_id") == aircraft["id"]]
    linked_event_ids = {
        row.get("predicted_event_id") for row in work_orders if row.get("predicted_event_id")
    }
    events = [row for row in aircraft_events if (
        not work_order_id or row.get("work_order_id") in wo_ids or row.get("id") in linked_event_ids
    )]
    event_ids = {row["id"] for row in events}

    all_history = sorted(
        [row for row in state.get("prediction_history", []) if row.get("aircraft_id") == aircraft["id"]],
        key=lambda row: (row.get("timestamp") or "", row.get("id") or ""),
    )
    linked_history_ids: set[str] = set()
    for row in events:
        linked_history_ids.update(str(value) for value in row.get("prediction_history_ids", []) if value)
        for key in ("prediction_history_id", "latest_prediction_history_id"):
            if row.get(key):
                linked_history_ids.add(str(row[key]))
    if not work_order_id:
        # A broad aircraft timeline may include its own prediction observations;
        # this is an aircraft-scoped link, not a causal event association.
        linked_history_ids.update(str(row["id"]) for row in all_history if row.get("id"))
        prediction_history = all_history
    else:
        prediction_history = [row for row in all_history if row.get("id") in linked_history_ids]

    transfers = [row for row in state.get("transfers", []) if row.get("work_order_id") in wo_ids]
    transfer_ids = {row["id"] for row in transfers}
    audits = state.get("audit", [])
    related_audits = []
    for row in audits:
        details = row.get("details") or {}
        entity_type, entity_id = row.get("entity_type"), row.get("entity_id")
        explicitly_linked = (
            (entity_type == "work_order" and entity_id in wo_ids)
            or (entity_type == "predicted_maintenance_event" and entity_id in event_ids)
            or (entity_type == "transfer" and entity_id in transfer_ids)
            or details.get("work_order_id") in wo_ids
            or details.get("transfer_id") in transfer_ids
            or details.get("prediction_history_id") in linked_history_ids
        )
        if explicitly_linked:
            related_audits.append({**row, "link_status": "linked"})

    # Aircraft-scoped prediction audits without a history ID are exposed as
    # unlinked evidence, never attached to a particular event by timestamp.
    unlinked_observations = [
        {**row, "link_status": "unlinked"}
        for row in audits
        if row.get("entity_type") == "aircraft"
        and row.get("entity_id") == aircraft["id"]
        and row.get("event_type") == "PREDICTION_GENERATED"
        and not (row.get("details") or {}).get("prediction_history_id")
    ]

    recommendations = [row for row in related_audits
                       if row.get("event_type") == "RECOMMENDATION_GENERATED"]
    decisions = [row for row in related_audits if row.get("event_type") in DECISION_TYPES]

    timeline: list[dict] = []
    for kind, rows in (("prediction_history", prediction_history), ("event", events),
                       ("work_order", work_orders), ("transfer", transfers),
                       ("audit", related_audits), ("audit", unlinked_observations)):
        for row in rows:
            link_status = row.get("link_status", (
                "aircraft_scoped" if kind == "prediction_history"
                and not any(row.get("id") in (
                    event.get("prediction_history_ids") or [event.get("prediction_history_id")]
                ) for event in events)
                else "linked"
            ))
            time_semantics = None
            if kind in {"work_order", "transfer"}:
                time_semantics = "created_at; status is current snapshot state"
            item = {
                **row,
                "record_type": kind,
                "record_id": row.get("id"),
                "occurred_at": _event_time(row),
                "link_status": link_status,
                "time_semantics": time_semantics,
                "record": row,
            }
            timeline.append(item)
    timeline.sort(key=lambda row: (*_sort_time(row["occurred_at"]), str(row["record_id"] or "")))

    linked_event_history = sum(bool(
        row.get("prediction_history_id") or row.get("prediction_history_ids")
    ) for row in events)
    unknown_origin_event_ids = [row["id"] for row in events if (
        not row.get("prediction_history_id")
        and row.get("prediction_history_origin_status") == "legacy_unknown"
    )]
    return {
        "aircraft_id": aircraft["id"],
        "work_order_id": work_order_id,
        "linkage": {
            "linked_event_count": linked_event_history,
            "unlinked_event_ids": [row["id"] for row in events if not (
                row.get("prediction_history_id") or row.get("prediction_history_ids")
            )],
            "unknown_origin_event_ids": unknown_origin_event_ids,
            "unlinked_prediction_audit_ids": [row["id"] for row in unlinked_observations],
            "method": "explicit stored IDs only; legacy time-based inference is not performed",
        },
        "prediction_history": prediction_history,
        "events": events,
        "work_orders": work_orders,
        "recommendations": recommendations,
        "decisions": decisions,
        "transfers": transfers,
        "timeline": timeline,
        "mutated_state": False,
    }
