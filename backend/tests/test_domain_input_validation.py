"""Request/domain validation must fail before creating records or audit rows."""

from math import inf, nan
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import InventoryRepository, WorkOrderRepository, reset, snapshot
from app.services import maintenance_service


@pytest.mark.parametrize(("condition", "expected_status"), [
    (-1, 422), (101, 422), (True, 422), (False, 422),
    (inf, 422), (-inf, 422), (nan, 422), (0, 200), (100, 200),
])
def test_inventory_condition_bounds(condition, expected_status):
    reset()
    inv = InventoryRepository.get("inv-03")
    before = snapshot()

    response = TestClient(app).patch(
        f"/api/inventory/{inv['id']}",
        content=json.dumps({"condition_pct": condition}, allow_nan=True),
        headers={"content-type": "application/json", "X-Demo-Role": "logistics"},
    )

    assert response.status_code == expected_status
    if expected_status == 422:
        assert snapshot() == before
    else:
        assert InventoryRepository.get(inv["id"])["condition_pct"] == condition


@pytest.mark.parametrize("payload", [
    {"component": "NOT-A-PART", "estimated_repair_hours": 2, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": 2, "priority": "URGENT"},
    {"component": "AV-077", "estimated_repair_hours": 0, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": -0.1, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": inf, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": nan, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": True, "priority": "HIGH"},
    {"component": "AV-077", "estimated_repair_hours": False, "priority": "HIGH"},
])
def test_invalid_manual_work_order_request_does_not_mutate_state(payload):
    reset()
    before = snapshot()

    response = TestClient(app).post(
        "/api/maintenance/work-orders",
        params={"aircraft_id": "A19"},
        content=json.dumps(payload, allow_nan=True),
        headers={"content-type": "application/json", "X-Demo-Role": "base",
                 "X-Demo-Base": "alpha"},
    )

    assert response.status_code == 422
    assert snapshot() == before


@pytest.mark.parametrize(("field", "value"), [
    ("component", "NOT-A-PART"),
    ("priority", "URGENT"),
    ("estimated_repair_hours", 0),
    ("estimated_repair_hours", -1),
    ("estimated_repair_hours", inf),
    ("estimated_repair_hours", nan),
])
def test_manual_work_order_service_validation_is_atomic(field, value):
    reset()
    before = snapshot()
    values = {"component": "AV-077", "priority": "HIGH", "estimated_repair_hours": 2}
    values[field] = value

    with pytest.raises(maintenance_service.ManualWorkOrderValidationError):
        maintenance_service.create_manual_work_order("A19", **values)

    assert snapshot() == before


def test_valid_catalogued_manual_work_order_accepts_priority_case_and_positive_duration():
    reset()

    work_order = maintenance_service.create_manual_work_order(
        "A19", " av-077 ", priority="low", estimated_repair_hours=0.25,
    )

    assert work_order["required_component"] == "AV-077"
    assert work_order["priority"] == "LOW"
    assert work_order["estimated_repair_hours"] == 0.25
    assert WorkOrderRepository.get(work_order["id"]) == work_order
