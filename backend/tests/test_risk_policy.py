"""Authoritative, read-only demo risk-band configuration contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.store import snapshot
from app.services.ml import base


def _prediction(*, health_score: float, failure_probability: float | None) -> dict:
    return {
        "aircraft_id": "A17",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_score": health_score,
        "failure_probability": failure_probability,
        "rul": 10,
        "rul_unit": "flight_hours",
        "confidence": 0.9,
        "prediction_horizon_hours": 72,
        "model_version": "risk-policy-test-v1",
    }


def test_policy_endpoint_matches_effective_shared_policy_and_is_read_only():
    before = snapshot()
    with TestClient(app) as client:
        response = client.get("/api/policy/risk-bands")
    assert response.status_code == 200
    policy = response.json()
    assert snapshot() == before

    assert policy["policy_id"] == "demo-risk-bands-v1"
    assert policy["source"] == "backend.services.ml.base.risk_band"
    assert policy["configuration_source"] == base.RISK_BAND_POLICY.configuration_source
    assert policy["configurable"] is True
    assert policy["health_score"]["configurable"] is True
    assert [(row["risk_level"], row["operator"], row["value"])
            for row in policy["health_score"]["thresholds"]] == [
        ("CRITICAL", "<", base.RISK_BAND_POLICY.health_thresholds[0]),
        ("HIGH", "<", base.RISK_BAND_POLICY.health_thresholds[1]),
        ("MEDIUM", "<", base.RISK_BAND_POLICY.health_thresholds[2]),
        ("LOW", ">=", base.RISK_BAND_POLICY.health_thresholds[2]),
    ]
    p_critical, p_high, p_medium = base.RISK_PROBABILITY_THRESHOLDS
    assert policy["failure_probability"]["configurable"] is False
    assert [(row["risk_level"], row["operator"], row["value"])
            for row in policy["failure_probability"]["thresholds"]] == [
        ("CRITICAL", ">=", p_critical),
        ("HIGH", ">=", p_high),
        ("MEDIUM", ">=", p_medium),
        ("LOW", "<", p_medium),
    ]
    assert policy["combination"] == {
        "rule": "most_severe",
        "severity_order": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
    }
    from app.services.ml.fd001_provider import HEALTH_DERIVATION, HEALTH_RUL_CAP_CYCLES
    assert policy["fd001"] == {
        "rul_unit": "cycles",
        "health_score_formula": HEALTH_DERIVATION,
        "rul_cap_cycles": HEALTH_RUL_CAP_CYCLES,
        "failure_probability": None,
        "probability_status": "unavailable",
        "probability_calibrated": False,
        "subsystem_inferred": False,
    }


@pytest.mark.parametrize(("raw", "expected"), [
    ("[20,50,90]", (20.0, 50.0, 90.0)),
    ("[0,0.1,100]", (0.0, 0.1, 100.0)),
])
def test_health_cutoffs_accept_finite_in_range_strictly_ascending_values(raw, expected):
    policy = base.load_risk_band_policy(raw)
    assert policy.health_thresholds == expected
    assert policy.configuration_source == base.RISK_HEALTH_THRESHOLDS_ENV


@pytest.mark.parametrize("raw", [
    "not-json", "{}", "[]", "[1,2]", "[1,2,3,4]", "[true,60,80]",
    "[-1,60,80]", "[45,60,101]", "[45,45,80]", "[60,45,80]",
    "[45, NaN, 80]", "[45, Infinity, 80]",
])
def test_invalid_health_cutoff_configuration_is_rejected(raw):
    with pytest.raises(ValueError, match="DEMO_RISK_HEALTH_THRESHOLDS"):
        base.load_risk_band_policy(raw)


def test_invalid_environment_health_cutoffs_fail_configuration_load(monkeypatch):
    monkeypatch.setenv(base.RISK_HEALTH_THRESHOLDS_ENV, "[80,60,45]")
    with pytest.raises(ValueError, match="strictly increasing"):
        base.load_risk_band_policy()


def test_configured_thresholds_drive_risk_band_and_prediction_validation(monkeypatch):
    configured = base.load_risk_band_policy("[20,50,90]")
    monkeypatch.setattr(base, "RISK_BAND_POLICY", configured)

    assert [base.risk_band(score) for score in (19.999, 20, 49.999, 50, 89.999, 90)] == [
        "CRITICAL", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW",
    ]
    # A missing calibrated probability keeps the configured health band;
    # an available contradictory probability can only increase severity.
    normalized = base.validate_prediction(
        _prediction(health_score=20, failure_probability=None), "A17",
    )
    assert normalized["risk_level"] == "HIGH"
    assert normalized["probability_status"] == "unavailable"
    assert base.risk_band(95, 0.70) == "CRITICAL"
