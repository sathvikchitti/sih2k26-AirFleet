"""Saved FD001 metrics exposure is fixed-path, read-only, and versioned."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import snapshot
from app.routers import evaluation
from app.services.ml import set_provider
from app.services.ml.fd001_provider import FD001MLProvider


class _FakeRULModel:
    model_version = "cmapss-fd001-rf-v1"
    metadata = {"unit": "cycles"}

    def predict_history(self, history):
        return {
            "rul_cycles": 12.0, "rul_low": 10.0, "rul_high": 14.0,
            "tree_rul_p10": 10.0, "tree_rul_p90": 13.0, "rul_std": 1.5,
            "rul_uncertainty_method": "uncalibrated-test-envelope",
            "top_drivers": [], "driver_method": None,
            "model_version": self.model_version,
            "observation_count": len(history), "source": "test", "is_synthetic": True,
        }


def _histories():
    return {engine_id: [[1.0] + [0.0] * 24, [2.0] + [0.1] * 24]
            for engine_id in range(1, 11)}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _report_path():
    return Path(__file__).resolve().parents[1] / "models" / "cmapss_fd001_rf_v1_metrics.json"


def test_fd001_metrics_endpoint_projects_official_reference_without_mutation(client):
    before = snapshot()
    first = client.get("/api/ml/fd001/metrics")
    second = client.get("/api/ml/fd001/metrics")

    assert first.status_code == second.status_code == 200
    payload = first.json()
    assert payload == second.json()
    assert payload["status"] == "available"
    assert payload["source"] == "existing_artifact_reference"
    assert payload["evaluation_type"] == "offline_simulation"
    assert payload["dataset"] == "NASA C-MAPSS FD001"
    assert payload["unit"] == "cycles"
    assert payload["model"] == {
        "version": "cmapss-fd001-rf-v1",
        "artifact_sha256": "14114389bc8dc09449cde646f9b582933b58ffa188f3955508cc2f3e87d30be9",
    }
    official = payload["official_test"]
    assert official["engine_count"] == 100
    assert official["metrics"] == {
        "mae_cycles": 13.7862,
        "rmse_cycles": 18.6998,
        "nasa_asymmetric_score": 669.5007,
    }
    assert official["uncertainty"]["raw_tree_p10_p90"] == {
        "reference_quantile_range": [10, 90], "nominal_coverage": 0.8,
        "observed_coverage": 0.7, "mean_width_cycles": 38.1932,
        "calibrated": False,
    }
    assert official["uncertainty"]["mean_inclusive_envelope"]["nominal_coverage"] is None
    assert official["uncertainty"]["mean_inclusive_envelope"]["observed_coverage"] == 0.7
    assert payload["calibrated"] is False
    assert "not aircraft telemetry" in payload["scope"]["provenance"]
    assert "scoring-only" in official["protocol"]
    assert "random_forest" not in payload["official_test"]
    assert snapshot() == before


@pytest.mark.parametrize("contents", ["{truncated", "null", "[]", '{"dataset":"wrong"}'])
def test_missing_or_invalid_saved_report_returns_generic_503(client, tmp_path, monkeypatch, contents):
    path = tmp_path / "metrics.json"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(evaluation, "FD001_METRICS_PATH", path)

    before = snapshot()
    response = client.get("/api/ml/fd001/metrics")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "FD001 metrics unavailable", "metrics_status": "unavailable",
    }
    assert snapshot() == before


def test_missing_metrics_report_returns_generic_503(client, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "FD001_METRICS_PATH", tmp_path / "absent.json")
    response = client.get("/api/ml/fd001/metrics")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "FD001 metrics unavailable", "metrics_status": "unavailable",
    }


def test_report_validation_rejects_nonfinite_metric(client, tmp_path, monkeypatch):
    report = json.loads(_report_path().read_text(encoding="utf-8"))
    report["existing_artifact_reference"]["official_test"]["mae_cycles"] = float("nan")
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(evaluation, "FD001_METRICS_PATH", path)

    response = client.get("/api/ml/fd001/metrics")
    assert response.status_code == 503
    assert response.json()["metrics_status"] == "unavailable"


def test_fd001_trend_exposes_actual_model_version_in_aircraft_detail(client):
    previous = None
    try:
        from app.services.ml import get_provider
        previous = get_provider()
        provider = FD001MLProvider(_FakeRULModel(), _histories())
        set_provider(provider)
        detail = client.get("/api/aircraft/A17").json()
        assert detail["rul_trend_model_version"] == "cmapss-fd001-rf-v1"
        assert detail["rul_trend"]
    finally:
        set_provider(previous)
