"""Read-only tests for current availability and target/resource KPIs."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.services import availability_service


def _wo(wo_id, aircraft_id, base_id, component="HP-204", *, status="WAITING_FOR_RESOURCE",
        priority="MEDIUM", resource_reserved=False, created_at="2026-10-01T00:00:00+00:00"):
    return {
        "id": wo_id,
        "aircraft_id": aircraft_id,
        "base_id": base_id,
        "required_component": component,
        "status": status,
        "priority": priority,
        "resource_reserved": resource_reserved,
        "created_at": created_at,
    }


def _state():
    return {
        "aircraft": [
            {"id": "A1", "base_id": "alpha", "status": "WAITING_FOR_PART"},
            {"id": "A2", "base_id": "alpha", "status": "MAINTENANCE"},
            {"id": "A3", "base_id": "alpha", "status": "AT_RISK"},
            {"id": "A4", "base_id": "bravo", "status": "AVAILABLE"},
        ],
        "parts": [
            {"part_number": "HP-204", "min_condition_pct": 40},
            {"part_number": "FP-102", "min_condition_pct": 35},
        ],
        "inventory": [
            {"id": "i1", "base_id": "alpha", "part_number": "HP-204",
             "quantity": 1, "reserved": 1, "minimum_reserve": 0, "condition_pct": 80},
            {"id": "i2", "base_id": "alpha", "part_number": "FP-102",
             "quantity": 1, "reserved": 0, "minimum_reserve": 0, "condition_pct": 90},
        ],
        "work_orders": [
            _wo("WO-1", "A1", "alpha"),
            _wo("WO-2", "A2", "alpha", status="IN_PROGRESS", resource_reserved=True),
            _wo("WO-3", "A3", "alpha", component="FP-102"),
            _wo("WO-4", "A1", "alpha", component=None),
        ],
        "transfers": [{
            "id": "T-1", "work_order_id": "WO-1", "part_number": "HP-204",
            "source_base": "charlie", "dest_base": "alpha", "status": "IN_TRANSIT",
            "quantity": 1,
        }],
    }


def test_target_parser_defaults_and_rejects_nonfinite_or_out_of_range_values():
    assert availability_service.parse_readiness_target(None) == 75.0
    assert availability_service.parse_readiness_target("0") == 0.0
    assert availability_service.parse_readiness_target("75.25") == 75.25
    assert availability_service.parse_readiness_target("100") == 100.0
    for invalid in ("", "abc", "NaN", "Infinity", "-Infinity", "-0.1", "100.1"):
        with pytest.raises(RuntimeError, match="READINESS_TARGET_PCT"):
            availability_service.parse_readiness_target(invalid)


def test_readiness_target_environment_is_validated_on_service_startup():
    backend_dir = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-c",
               "from app.services.availability_service import READINESS_TARGET_PCT; print(READINESS_TARGET_PCT)"]
    default_env = os.environ.copy()
    default_env.pop("READINESS_TARGET_PCT", None)
    default = subprocess.run(command, cwd=backend_dir, env=default_env,
                             capture_output=True, text=True, check=False)
    assert default.returncode == 0
    assert default.stdout.strip() == "75.0"

    invalid_env = dict(default_env, READINESS_TARGET_PCT="NaN")
    invalid = subprocess.run(command, cwd=backend_dir, env=invalid_env,
                             capture_output=True, text=True, check=False)
    assert invalid.returncode != 0
    assert "READINESS_TARGET_PCT must be a finite number from 0 to 100" in invalid.stderr


def test_readiness_kpis_are_snapshot_based_deduplicated_and_keep_health_separate():
    state = _state()
    before = deepcopy(state)

    metrics = availability_service._readiness_kpis_from_snapshot(state, 75.0)

    assert state == before
    assert metrics["fleet"] == {
        "mission_capable_rate_pct": 25.0,
        "readiness_target_pct": 75.0,
        "gap_to_target_pct": 50.0,
        "nmcs_count": 1,
        "aircraft_down_for_maintenance": 2,
    }
    assert metrics["bases"]["alpha"] == {
        "mission_capable_rate_pct": 0.0,
        "readiness_target_pct": 75.0,
        "gap_to_target_pct": 75.0,
        "nmcs_count": 1,
        "aircraft_down_for_maintenance": 2,
    }
    assert metrics["bases"]["bravo"] == {
        "mission_capable_rate_pct": 100.0,
        "readiness_target_pct": 75.0,
        "gap_to_target_pct": 0.0,
        "nmcs_count": 0,
        "aircraft_down_for_maintenance": 0,
    }
    assert metrics["bases"]["charlie"] == {
        "mission_capable_rate_pct": 0.0,
        "readiness_target_pct": 75.0,
        "gap_to_target_pct": 75.0,
        "nmcs_count": 0,
        "aircraft_down_for_maintenance": 0,
    }
    # A1's second missing-component WO does not increase the aircraft count;
    # the in-transit item is not yet present in Alpha inventory. A3 is health-
    # only AT_RISK but has local stock, so it does not count as NMCS.


def test_local_stock_is_claimed_once_and_pending_outbound_stock_is_not_reused():
    state = {
        "aircraft": [
            {"id": "A1", "base_id": "alpha", "status": "WAITING_FOR_PART"},
            {"id": "A2", "base_id": "alpha", "status": "WAITING_FOR_PART"},
            {"id": "A3", "base_id": "alpha", "status": "WAITING_FOR_PART"},
        ],
        "parts": [{"part_number": "HP-204", "min_condition_pct": 40}],
        "inventory": [{"id": "i1", "base_id": "alpha", "part_number": "HP-204",
                       "quantity": 2, "reserved": 0, "minimum_reserve": 0,
                       "condition_pct": 80}],
        "work_orders": [
            _wo("WO-1", "A1", "alpha", priority="HIGH", created_at="2026-10-01"),
            _wo("WO-2", "A2", "alpha", priority="MEDIUM", created_at="2026-10-02"),
            _wo("WO-3", "A3", "alpha", priority="LOW", created_at="2026-10-03"),
        ],
        "transfers": [{
            "id": "T-1", "work_order_id": "WO-9", "part_number": "HP-204",
            "source_base": "alpha", "dest_base": "bravo", "status": "PENDING_APPROVAL",
            "quantity": 1, "created": "2026-10-04",
        }],
    }

    metrics = availability_service._readiness_kpis_from_snapshot(state, 75.0)

    # Pending outgoing transfer provisionally claims one of two units. The
    # remaining serviceable unit is earmarked to the highest-priority WO.
    assert metrics["fleet"]["nmcs_count"] == 2
    assert metrics["bases"]["alpha"]["nmcs_count"] == 2


def test_reserved_unit_requires_serviceable_grade_and_zero_stock_reserve_are_shortages():
    state = {
        "aircraft": [
            {"id": "A1", "base_id": "alpha", "status": "MAINTENANCE"},
            {"id": "A2", "base_id": "alpha", "status": "WAITING_FOR_PART"},
        ],
        "parts": [{"part_number": "HP-204", "min_condition_pct": 40}],
        "inventory": [{"id": "i1", "base_id": "alpha", "part_number": "HP-204",
                       "quantity": 1, "reserved": 1, "minimum_reserve": 0,
                       "condition_pct": 30}],
        "work_orders": [
            _wo("WO-1", "A1", "alpha", status="IN_PROGRESS", resource_reserved=True),
            _wo("WO-2", "A2", "alpha"),
        ],
        "transfers": [],
    }

    metrics = availability_service._readiness_kpis_from_snapshot(state, 75.0)

    assert metrics["fleet"]["nmcs_count"] == 2
    assert metrics["fleet"]["aircraft_down_for_maintenance"] == 2


def test_fleet_overview_keeps_legacy_fields_and_adds_kpis_from_one_snapshot(monkeypatch):
    state = _state()
    snapshot_calls = []
    monkeypatch.setattr(availability_service, "store", lambda: None)
    monkeypatch.setattr(availability_service, "snapshot", lambda: snapshot_calls.append(1) or deepcopy(state))
    monkeypatch.setattr(availability_service, "get_provider", lambda: object())
    monkeypatch.setattr(
        availability_service, "predict_validated",
        lambda _provider, _aircraft_id: {"risk_level": "LOW"},
    )
    monkeypatch.setattr(availability_service, "READINESS_TARGET_PCT", 75.0)

    overview = availability_service.fleet_overview()

    assert snapshot_calls == [1]
    assert overview["total"] == 4
    assert overview["available"] == 1
    assert overview["availability_pct"] == 25.0
    assert overview["mission_capable_rate_pct"] == overview["availability_pct"]
    assert overview["readiness_target_pct"] == 75.0
    assert overview["gap_to_target_pct"] == 50.0
    assert overview["nmcs_count"] == 1
    assert overview["aircraft_down_for_maintenance"] == 2
    alpha = next(row for row in overview["bases"] if row["id"] == "alpha")
    assert alpha["aircraft_count"] == 3
    assert alpha["mission_capable_rate_pct"] == alpha["availability_pct"] == 0.0
    assert alpha["gap_to_target_pct"] == 75.0

