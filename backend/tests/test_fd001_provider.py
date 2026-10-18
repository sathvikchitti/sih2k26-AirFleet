"""Integration contract tests for the explicit FD001 provider."""

from fastapi.testclient import TestClient

from app.main import app, initialize_demo_state
from app.repositories import (
    AircraftRepository, EventRepository, InventoryRepository,
    PredictionHistoryRepository, TransferRepository, WorkOrderRepository, reset,
)
from app.services.ml import PredictionValidationError, get_provider, predict_validated, set_provider
from app.services.ml.fd001_provider import AIRCRAFT_TO_FD001_ENGINE, FD001MLProvider
from app.services.ml.mock_provider import MockMLProvider


class FakeRULModel:
    model_version = "cmapss-fd001-rf-v1"
    metadata = {"unit": "cycles"}

    def predict_history(self, history):
        return {
            "rul_cycles": 12.0,
            "rul_low": 10.0,
            "rul_high": 14.0,
            "tree_rul_p10": 10.0,
            "tree_rul_p90": 13.0,
            "rul_std": 1.5,
            "rul_uncertainty_method": "uncalibrated-test-envelope",
            "top_drivers": [{
                "feature": "sensor_2_mean", "sensor": "sensor_2", "statistic": "mean",
                "contribution_score": -0.25, "direction": "below_reference",
            }],
            "driver_method": "indicative-not-causal-test-reference",
            "model_version": self.model_version,
            "observation_count": len(history),
            "source": "nasa-cmapss-fd001-random-forest",
            "is_synthetic": True,
        }


class FixedCycleProvider:
    name = "fd001-random-forest"

    def predict(self, aircraft_id):
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).isoformat()
        return {
            "aircraft_id": aircraft_id,
            "timestamp": stamp,
            "health_score": 42,
            "health_score_derived": "linear_rul_cap_125_cycles",
            "failure_probability": None,
            "probability_status": "unavailable",
            "prediction_horizon_hours": None,
            "rul": 52.0,
            "rul_unit": "cycles",
            "predicted_maintenance": True,
            "predicted_issue": "FD001 RUL indicator; human subsystem diagnosis required",
            "subsystem": None,
            "source": "cmapss-fd001-demo-history",
            "provider": self.name,
            "model_version": "test-fd001-v1",
            "history_source": "synthetic_fd001_test_engine_history",
            "is_synthetic": True,
        }


def _histories():
    row = [1.0] + [0.0] * 24
    return {engine_id: [row, [2.0] + [0.1] * 24] for engine_id in range(1, 11)}


def test_fd001_provider_mapping_and_nullable_cycle_contract():
    provider = FD001MLProvider(FakeRULModel(), _histories())

    result = predict_validated(provider, "A17")

    assert AIRCRAFT_TO_FD001_ENGINE["A17"] == 1
    assert result["rul"] == result["remaining_useful_life"] == 12
    assert result["rul_unit"] == "cycles"
    assert result["rul_low"] == 10
    assert result["rul_high"] == 14
    assert result["tree_rul_p10"] == 10
    assert result["tree_rul_p90"] == 13
    assert result["rul_std"] == 1.5
    assert result["top_drivers"][0]["direction"] == "below_reference"
    assert result["prediction_horizon_hours"] is None
    assert result["health_score"] == FD001MLProvider.health_from_rul(12)
    assert result["health_score_derived"] == "linear_rul_cap_125_cycles"
    assert result["failure_probability"] is None
    assert result["probability_status"] == "unavailable"
    assert result["risk_level"] == "CRITICAL"
    assert result["predicted_maintenance"] is True
    assert result["subsystem"] is None
    assert result["source"] == "cmapss-fd001-demo-history"
    assert result["provider"] == "fd001-random-forest"
    assert result["model_version"] == "cmapss-fd001-rf-v1"
    assert result["is_synthetic"] is True
    assert result["metadata"]["engine_id"] == 1
    assert result["metadata"]["observation_cycle_count"] == 2


def test_fd001_trend_is_model_predictions_over_history_prefixes():
    provider = FD001MLProvider(FakeRULModel(), _histories())

    assert provider.degradation_trend("A17", points=2) == [10, 10]
    assert provider.trend_source == "fd001_model_prefix_predictions"


def test_fd001_rul_trend_returns_cycle_native_points_and_intervals():
    provider = FD001MLProvider(FakeRULModel(), _histories())

    points = provider.rul_trend("A17", points=2)

    assert points == [
        {"cycle": 1, "rul_cycles": 12.0, "rul_low": 10.0, "rul_high": 14.0},
        {"cycle": 2, "rul_cycles": 12.0, "rul_low": 10.0, "rul_high": 14.0},
    ]


def test_mock_uncertainty_and_driver_fields_are_explicitly_unavailable():
    prediction = MockMLProvider().predict("A17")
    assert prediction["failure_probability"] == 0.78
    assert prediction["rul_low"] is None
    assert prediction["rul_high"] is None
    assert prediction["tree_rul_p10"] is None
    assert prediction["tree_rul_p90"] is None
    assert prediction["rul_std"] is None
    assert prediction["rul_uncertainty_method"] is None
    assert prediction["top_drivers"] == []
    assert prediction["driver_method"] is None
    assert MockMLProvider().rul_trend("A17") == []


def test_prediction_validation_rejects_interval_that_excludes_point():
    provider = FixedCycleProvider()
    original = provider.predict

    def invalid(aircraft_id):
        result = original(aircraft_id)
        result.update({"rul_low": 60, "rul_high": 70, "rul_std": 2})
        return result

    provider.predict = invalid
    try:
        predict_validated(provider, "A17")
    except PredictionValidationError as exc:
        assert "contain the point prediction" in str(exc)
    else:
        raise AssertionError("an RUL interval excluding the point was accepted")


def test_prediction_validation_rejects_unbounded_driver_scores():
    provider = FixedCycleProvider()
    original = provider.predict

    def invalid(aircraft_id):
        result = original(aircraft_id)
        result["top_drivers"] = [{
            "direction": "above_reference", "contribution_score": 5.01,
        }]
        return result

    provider.predict = invalid
    try:
        predict_validated(provider, "A17")
    except PredictionValidationError as exc:
        assert "top driver contribution_score" in str(exc)
    else:
        raise AssertionError("an unbounded top-driver score was accepted")


def test_provider_selection_is_explicit_and_real_provider_never_falls_back(monkeypatch, tmp_path):
    previous = get_provider()
    try:
        set_provider(None)
        monkeypatch.setenv("ML_PROVIDER", "mock")
        assert isinstance(get_provider(), MockMLProvider)

        set_provider(None)
        monkeypatch.setenv("ML_PROVIDER", "fd001")
        monkeypatch.setenv("FD001_MODEL_PATH", str(tmp_path / "missing.joblib"))
        try:
            get_provider()
        except PredictionValidationError as exc:
            assert "FD001 provider unavailable" in str(exc)
        else:
            raise AssertionError("selected FD001 provider silently fell back")
    finally:
        set_provider(previous)


def test_selected_fd001_missing_artifact_is_explicit_api_unavailable(monkeypatch, tmp_path, caplog):
    previous = get_provider()
    try:
        set_provider(None)
        monkeypatch.setenv("ML_PROVIDER", "fd001")
        monkeypatch.setenv("FD001_MODEL_PATH", str(tmp_path / "missing.joblib"))

        response = TestClient(app).get("/api/health/A17")

        assert response.status_code == 503
        assert response.json() == {
            "detail": "prediction provider unavailable",
            "prediction_status": "unavailable",
        }
        assert str(tmp_path) not in response.text
        assert str(tmp_path) in caplog.text
    finally:
        set_provider(previous)


def test_selected_fd001_corrupt_artifact_is_generic_api_unavailable_and_diagnosed(
        monkeypatch, tmp_path, caplog):
    previous = get_provider()
    try:
        set_provider(None)
        monkeypatch.setenv("ML_PROVIDER", "fd001")
        corrupt = tmp_path / "corrupt-model.joblib"
        corrupt.write_bytes(b"not a joblib artifact")
        monkeypatch.setenv("FD001_MODEL_PATH", str(corrupt))

        response = TestClient(app).get("/api/health/A17")

        assert response.status_code == 503
        assert response.json() == {
            "detail": "prediction provider unavailable",
            "prediction_status": "unavailable",
        }
        assert str(corrupt) not in response.text
        assert "KeyError" in caplog.text
        assert "fd001_model.py" in caplog.text
    finally:
        set_provider(previous)


def test_fd001_demo_initialization_clears_mock_seed_and_preserves_catalog(monkeypatch):
    previous_provider = get_provider()
    monkeypatch.setenv("ML_PROVIDER", "fd001")
    set_provider(FixedCycleProvider())
    try:
        initialize_demo_state()

        assert len(AircraftRepository.list_all()) == 10
        inventory_snapshot = [
            (row["base_id"], row["part_number"], row["quantity"], row["reserved"])
            for row in InventoryRepository.list_all()
        ]
        assert len(inventory_snapshot) == 10
        assert WorkOrderRepository.list_all() == []
        assert TransferRepository.list_all() == []
        assert len(EventRepository.list_all()) == 10
        assert all(event["subsystem"] is None for event in EventRepository.list_all())
        assert all(event["rul_unit"] == "cycles" and event["predicted_time"] is None
                   for event in EventRepository.list_all())
        histories = PredictionHistoryRepository.for_aircraft("A17")
        assert len(histories) == 1
        assert histories[0]["source"] == "cmapss-fd001-demo-history"
        assert histories[0]["failure_probability"] is None
        assert histories[0]["rul_unit"] == "cycles"

        # Normal prediction reads must not rerun reset initialization or erase
        # user actions. Only startup and explicit reset invoke the initializer.
        event = next(event for event in EventRepository.list_all()
                     if event["aircraft_id"] == "A17")
        response = TestClient(app).post(
            f"/api/maintenance/events/{event['id']}/work-order",
            json={"required_component": "HP-204", "actor": "base"},
            headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
        )
        assert response.status_code == 200
        work_order_id = response.json()["id"]
        TestClient(app).get("/api/health/A17")
        assert WorkOrderRepository.get(work_order_id) is not None
        assert inventory_snapshot == [
            (row["base_id"], row["part_number"], row["quantity"], row["reserved"])
            for row in InventoryRepository.list_all()
        ]

        initialize_demo_state()
        assert WorkOrderRepository.list_all() == []
        assert TransferRepository.list_all() == []
        assert len(EventRepository.list_all()) == 10
        assert len(PredictionHistoryRepository.for_aircraft("A17")) == 1
    finally:
        set_provider(previous_provider)
        monkeypatch.setenv("ML_PROVIDER", "mock")
        reset()
