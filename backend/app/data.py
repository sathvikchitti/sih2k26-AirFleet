"""Deterministic demo dataset — the SEED layer.

DATA SOURCE PHILOSOPHY (spec section 20) — keep these two streams distinct:

  * PUBLIC DATA  -> the ML provider (services/ml). Real degradation models will
    be trained on public C-MAPSS-style datasets.
  * SIMULATED CONTEXT -> everything in this file: bases, aircraft, inventory,
    distances, transport, operational state.

Nothing in this module comes from a public dataset, and nothing here should
ever be presented as real telemetry.

The dataset is intentionally small and fully deterministic: `reset()` restores
it byte-for-byte, so the A17 demo scenario (spec section 25) always replays
identically.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .domain.enums import (
    AircraftStatus,
    InventoryStatus,
    MaintenanceEventStatus,
    MaintenanceSource,
    Priority,
    TransferStatus,
    WorkOrderStatus,
)

# Demo clock: fixed so seeded records carry stable, reproducible timestamps.
# Actions taken at runtime use the real clock (see services/audit.py).
DEMO_EPOCH = datetime(2026, 10, 6, 8, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------
# Simulated operational context
# --------------------------------------------------------------------------
BASES = [
    {"id": "alpha", "name": "Base Alpha", "location": "Northern Sector", "lat": 28.61, "lon": 77.20},
    {"id": "bravo", "name": "Base Bravo", "location": "Western Sector", "lat": 27.90, "lon": 76.10},
    {"id": "charlie", "name": "Base Charlie", "location": "Central Sector", "lat": 26.50, "lon": 77.80},
]

# Symmetric ground distances between bases.
DISTANCES_KM = {
    ("alpha", "bravo"): 120,
    ("alpha", "charlie"): 380,
    ("bravo", "charlie"): 260,
}

# Average ground transport speed, used to derive ETA.
AVG_SPEED_KMH = 60


def distance_km(a: str, b: str) -> int:
    if a == b:
        return 0
    return DISTANCES_KM.get((a, b), DISTANCES_KM.get((b, a), 200))


def eta_hours(a: str, b: str) -> float:
    return round(distance_km(a, b) / AVG_SPEED_KMH, 1)


# `subsystem` is what the ML model reports. It is NOT a part number — the
# knowledge layer turns it into a part (see domain/knowledge.py).
AIRCRAFT = [
    {"id": "A17", "base_id": "alpha", "type": "Fighter Mk-II", "tail": "A17", "status": AircraftStatus.AT_RISK.value},
    {"id": "A19", "base_id": "alpha", "type": "Fighter Mk-II", "tail": "A19", "status": AircraftStatus.AVAILABLE.value},
    {"id": "A21", "base_id": "alpha", "type": "Transport H-4", "tail": "A21", "status": AircraftStatus.DEGRADED.value},
    {"id": "A23", "base_id": "alpha", "type": "Fighter Mk-II", "tail": "A23", "status": AircraftStatus.AVAILABLE.value},
    {"id": "A24", "base_id": "bravo", "type": "Fighter Mk-II", "tail": "A24", "status": AircraftStatus.DEGRADED.value},
    {"id": "A26", "base_id": "bravo", "type": "Transport H-4", "tail": "A26", "status": AircraftStatus.AVAILABLE.value},
    {"id": "A28", "base_id": "bravo", "type": "Fighter Mk-II", "tail": "A28", "status": AircraftStatus.MAINTENANCE.value},
    {"id": "A32", "base_id": "charlie", "type": "Transport H-4", "tail": "A32", "status": AircraftStatus.AVAILABLE.value},
    {"id": "A33", "base_id": "charlie", "type": "Fighter Mk-II", "tail": "A33", "status": AircraftStatus.AVAILABLE.value},
    {"id": "A35", "base_id": "charlie", "type": "Fighter Mk-II", "tail": "A35", "status": AircraftStatus.DEGRADED.value},
]

PARTS = [
    {"id": "HP-204", "part_number": "HP-204", "name": "High-Pressure Turbine Module", "category": "Engine", "min_condition_pct": 40},
    {"id": "FP-102", "part_number": "FP-102", "name": "Fuel Pump Assembly", "category": "Fuel", "min_condition_pct": 35},
    {"id": "OE-310", "part_number": "OE-310", "name": "Oil Cooler / Heat Exchanger", "category": "Engine", "min_condition_pct": 35},
    {"id": "AV-077", "part_number": "AV-077", "name": "Avionics LRU", "category": "Avionics", "min_condition_pct": 50},
]

# `minimum_reserve` is the stock a base keeps for itself. Available-for-transfer
# = quantity - reserved - minimum_reserve (spec section 9).
INVENTORY = [
    {"id": "inv-01", "base_id": "alpha", "part_number": "HP-204", "quantity": 0, "reserved": 0, "minimum_reserve": 0, "condition_pct": 0, "status": InventoryStatus.STOCKOUT.value},
    {"id": "inv-02", "base_id": "bravo", "part_number": "HP-204", "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 42, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-03", "base_id": "charlie", "part_number": "HP-204", "quantity": 2, "reserved": 0, "minimum_reserve": 0, "condition_pct": 84, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-04", "base_id": "alpha", "part_number": "FP-102", "quantity": 4, "reserved": 1, "minimum_reserve": 1, "condition_pct": 91, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-05", "base_id": "bravo", "part_number": "FP-102", "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 66, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-06", "base_id": "charlie", "part_number": "OE-310", "quantity": 3, "reserved": 0, "minimum_reserve": 1, "condition_pct": 78, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-07", "base_id": "bravo", "part_number": "OE-310", "quantity": 0, "reserved": 0, "minimum_reserve": 0, "condition_pct": 0, "status": InventoryStatus.STOCKOUT.value},
    {"id": "inv-08", "base_id": "alpha", "part_number": "OE-310", "quantity": 2, "reserved": 0, "minimum_reserve": 0, "condition_pct": 88, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-09", "base_id": "alpha", "part_number": "AV-077", "quantity": 2, "reserved": 0, "minimum_reserve": 0, "condition_pct": 95, "status": InventoryStatus.AVAILABLE.value},
    {"id": "inv-10", "base_id": "charlie", "part_number": "AV-077", "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 61, "status": InventoryStatus.LOW_STOCK.value},
]

# Seed work orders, keyed to the work orders that the legacy work-order
# statuses were seeded with. `predicted_event_id` links to PM-* events below.
WORK_ORDERS = [
    {
        "id": "WO-1042",
        "aircraft_id": "A17",
        "base_id": "alpha",
        "priority": Priority.CRITICAL.value,
        "source": MaintenanceSource.PREDICTED_MAINTENANCE.value,
        "predicted_event_id": "PM-001",
        "issue": "High-pressure subsystem degradation",
        "maintenance_action": "Inspect / replace high-pressure turbine module",
        "required_component": "HP-204",
        "status": WorkOrderStatus.WAITING_FOR_RESOURCE.value,
        "estimated_repair_hours": 6.0,
        "required_by_flight_hours": 8,
        "created_at": iso(DEMO_EPOCH + timedelta(hours=2)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=2)),
        "started_at": None,
        "completed_at": None,
    },
    {
        "id": "WO-1043",
        "aircraft_id": "A28",
        "base_id": "bravo",
        "priority": Priority.LOW.value,
        "source": MaintenanceSource.PREDICTED_MAINTENANCE.value,
        "predicted_event_id": "PM-004",
        "issue": "Fuel system pressure loss",
        "maintenance_action": "Inspect / replace fuel pump assembly",
        "required_component": "FP-102",
        "status": WorkOrderStatus.IN_PROGRESS.value,
        "estimated_repair_hours": 3.0,
        "required_by_flight_hours": None,
        "created_at": iso(DEMO_EPOCH + timedelta(hours=6)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=6)),
        "started_at": iso(DEMO_EPOCH + timedelta(hours=6)),
        "completed_at": None,
    },
    {
        "id": "WO-1044",
        "aircraft_id": "A21",
        "base_id": "alpha",
        "priority": Priority.MEDIUM.value,
        "source": MaintenanceSource.PREDICTED_MAINTENANCE.value,
        "predicted_event_id": "PM-002",
        "issue": "Fuel system pressure loss",
        "maintenance_action": "Inspect / replace fuel pump assembly",
        "required_component": "FP-102",
        "status": WorkOrderStatus.SCHEDULED.value,
        "estimated_repair_hours": 4.0,
        "required_by_flight_hours": 30,
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "started_at": None,
        "completed_at": None,
    },
    {
        "id": "WO-1045",
        "aircraft_id": "A24",
        "base_id": "bravo",
        "priority": Priority.MEDIUM.value,
        "source": MaintenanceSource.PREDICTED_MAINTENANCE.value,
        "predicted_event_id": "PM-003",
        "issue": "Oil cooling capacity degradation",
        "maintenance_action": "Inspect / replace oil cooler / heat exchanger",
        "required_component": "OE-310",
        "status": WorkOrderStatus.SCHEDULED.value,
        "estimated_repair_hours": 5.0,
        "required_by_flight_hours": 36,
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "started_at": None,
        "completed_at": None,
    },
]

# Predicted maintenance events: the bridge between a prediction and operations
# (spec sections 3-4). A prediction alone never creates a work order.
PREDICTED_EVENTS = [
    {
        "id": "PM-001", "aircraft_id": "A17", "prediction_id": "A17",
        "predicted_issue": "High-pressure subsystem degradation", "subsystem": "HIGH_PRESSURE",
        "risk_level": "CRITICAL", "rul": 12, "confidence": 0.91, "health_score": 41,
        "predicted_time": iso(DEMO_EPOCH + timedelta(hours=12)),
        "required_resource_type": "COMPONENT",
        "status": MaintenanceEventStatus.WORK_ORDER_CREATED.value,
        "work_order_id": "WO-1042",
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=2)),
    },
    {
        "id": "PM-002", "aircraft_id": "A21", "prediction_id": "A21",
        "predicted_issue": "Fuel system pressure loss", "subsystem": "FUEL_SYSTEM",
        "risk_level": "MEDIUM", "rul": 38, "confidence": 0.88, "health_score": 76,
        "predicted_time": iso(DEMO_EPOCH + timedelta(hours=30)),
        "required_resource_type": "COMPONENT",
        "status": MaintenanceEventStatus.WORK_ORDER_CREATED.value,
        "work_order_id": "WO-1044",
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=1)),
    },
    {
        "id": "PM-003", "aircraft_id": "A24", "prediction_id": "A24",
        "predicted_issue": "Oil cooling capacity degradation", "subsystem": "COOLING",
        "risk_level": "HIGH", "rul": 38, "confidence": 0.86, "health_score": 68,
        "predicted_time": iso(DEMO_EPOCH + timedelta(hours=36)),
        "required_resource_type": "COMPONENT",
        "status": MaintenanceEventStatus.WORK_ORDER_CREATED.value,
        "work_order_id": "WO-1045",
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=1)),
    },
    {
        "id": "PM-004", "aircraft_id": "A28", "prediction_id": "A28",
        "predicted_issue": "Fuel system pressure loss", "subsystem": "FUEL_SYSTEM",
        "risk_level": "HIGH", "rul": 20, "confidence": 0.84, "health_score": 55,
        "predicted_time": iso(DEMO_EPOCH + timedelta(hours=20)),
        "required_resource_type": "COMPONENT",
        "status": MaintenanceEventStatus.WORK_ORDER_CREATED.value,
        "work_order_id": "WO-1043",
        "created_at": iso(DEMO_EPOCH + timedelta(hours=5)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=6)),
    },
    {
        # An event deliberately left un-triaged: proof that a prediction does
        # not automatically become a work order.
        "id": "PM-005", "aircraft_id": "A35", "prediction_id": "A35",
        "predicted_issue": "High-pressure subsystem degradation", "subsystem": "HIGH_PRESSURE",
        "risk_level": "MEDIUM", "rul": 55, "confidence": 0.87, "health_score": 72,
        "predicted_time": iso(DEMO_EPOCH + timedelta(hours=48)),
        "required_resource_type": "COMPONENT",
        "status": MaintenanceEventStatus.OPEN.value,
        "work_order_id": None,
        "created_at": iso(DEMO_EPOCH + timedelta(hours=1)),
        "updated_at": iso(DEMO_EPOCH + timedelta(hours=1)),
    },
]

TRANSFERS = [
    {
        "id": "T-101", "part_number": "FP-102", "source_base": "alpha", "dest_base": "bravo",
        "quantity": 1, "status": TransferStatus.IN_TRANSIT.value, "eta_hours": 2.0,
        "created": iso(DEMO_EPOCH + timedelta(hours=-2)), "started_at": iso(DEMO_EPOCH + timedelta(hours=-2)),
        "received_at": None, "for_aircraft": "A28", "work_order_id": "WO-1043", "condition_pct": 91,
    },
    {
        "id": "T-102", "part_number": "OE-310", "source_base": "charlie", "dest_base": "bravo",
        "quantity": 1, "status": TransferStatus.PENDING_APPROVAL.value, "eta_hours": 4.3,
        "created": iso(DEMO_EPOCH), "started_at": None,
        "received_at": None, "for_aircraft": None, "work_order_id": None, "condition_pct": 78,
    },
]


def _seed_prediction_history() -> list[dict]:
    """Deterministic historical predictions (spec section 16).

    A simple declining series ending at the aircraft's current health, so the
    UI can demonstrate condition changing over time without fabricating sensor
    graphs. Replaced wholesale once real ML runs on a schedule.
    """
    from .services.ml import mock_provider  # local import: avoids a cycle

    points = 8
    rows: list[dict] = []
    for ac in AIRCRAFT:
        pred = mock_provider.raw_prediction(ac["id"])
        health = pred["health_score"]
        start = min(99, health + 34)
        step = (start - health) / (points - 1)
        rul_start = pred["rul"] + points * 12
        for i in range(points):
            health_i = round(start - step * i)
            # Timestamp must increase with i so that sorting by time yields a
            # declining series ending at the aircraft's current health.
            ts = DEMO_EPOCH + timedelta(hours=2 * i)
            rows.append({
                "id": f"PH-{ac['id']}-{i + 1:02d}",
                "aircraft_id": ac["id"],
                "timestamp": iso(ts),
                "health_score": health_i,
                "risk_level": mock_provider.risk_band(health_i, pred["failure_probability"]),
                "rul": max(0, round(rul_start - (points - i) * 12)),
                "rul_unit": "flight_hours",
                "prediction_horizon_hours": 72,
                "confidence": pred["confidence"],
                "source": "mock-ml-service",
                "model_version": "mock-demo-v1",
                "history_source": "illustrative",
                "is_synthetic": True,
            })
    return rows


def _seed_audit() -> list[dict]:
    """Audit entries describing how the seeded state came to be."""
    from .domain.enums import AuditEventType

    rows: list[dict] = []

    def add(kind, at, entity_type, entity_id, summary, actor="system", **extra):
        rows.append({
            "id": f"AE-{len(rows) + 1:04d}",
            "event_type": kind,
            "occurred_at": iso(at),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "actor": actor,
            "details": extra,
        })

    t = DEMO_EPOCH
    add(AuditEventType.PREDICTION_GENERATED.value, t, "aircraft", "A17",
        "Prediction generated for A17 (mock-ml-service)", subsystem="HIGH_PRESSURE")
    add(AuditEventType.PREDICTION_GENERATED.value, t + timedelta(minutes=1), "aircraft", "A21",
        "Prediction generated for A21 (mock-ml-service)", subsystem="FUEL_SYSTEM")
    add(AuditEventType.PREDICTION_GENERATED.value, t + timedelta(minutes=1), "aircraft", "A24",
        "Prediction generated for A24 (mock-ml-service)", subsystem="COOLING")
    add(AuditEventType.MAINTENANCE_EVENT_CREATED.value, t + timedelta(hours=1), "predicted_maintenance_event", "PM-001",
        "Maintenance event created for A17 from prediction")
    add(AuditEventType.WORK_ORDER_CREATED.value, t + timedelta(hours=2), "work_order", "WO-1042",
        "Work order WO-1042 created for A17 — requires HP-204",
        predicted_event_id="PM-001", source="PREDICTED_MAINTENANCE")
    add(AuditEventType.RECOMMENDATION_GENERATED.value, t + timedelta(hours=2, minutes=30), "work_order", "WO-1042",
        "Recommendation generated for WO-1042", candidates=2)
    return rows


def build_seed() -> dict:
    """Fresh, deeply-copied seed state."""
    from .services.ml import mock_provider

    audit = _seed_audit()
    return {
        "aircraft": deepcopy(AIRCRAFT),
        "parts": deepcopy(PARTS),
        "inventory": deepcopy(INVENTORY),
        "work_orders": deepcopy(WORK_ORDERS),
        "predicted_events": deepcopy(PREDICTED_EVENTS),
        "transfers": deepcopy(TRANSFERS),
        "prediction_history": _seed_prediction_history(),
        "audit": audit,
        "work_order_seq": 1046,
        "event_seq": 6,
        "transfer_seq": 103,
        "audit_seq": len(audit) + 1,
        "ml": mock_provider.raw_predictions(),
    }
