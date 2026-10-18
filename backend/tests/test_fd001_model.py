from pathlib import Path

import numpy as np
import pytest

from app.services.ml.fd001_model import (
    FD001RULModel,
    evaluate_saved_artifact,
    _life_classification,
    _nasa_score,
    feature_vector,
    healthy_training_reference,
    load_engine_histories,
    train_fd001,
)


def _write_matrix(path: Path, rows):
    np.savetxt(path, np.asarray(rows, dtype=float), fmt="%.6f")


def _make_fd001_fixture(root: Path):
    train_rows = []
    for engine in range(1, 7):
        for cycle in range(1, 13):
            # Engine-specific offset prevents all sensor columns from being
            # constant while keeping the fixture deterministic and tiny.
            settings = [engine / 10, cycle / 10, (engine + cycle) / 20]
            sensors = [engine + cycle * (sensor + 1) / 100 for sensor in range(21)]
            train_rows.append([engine, cycle, *settings, *sensors])
    test_rows = []
    for engine in range(1, 4):
        for cycle in range(1, 9):
            settings = [engine / 10, cycle / 10, (engine + cycle) / 20]
            sensors = [engine + cycle * (sensor + 1) / 100 for sensor in range(21)]
            test_rows.append([engine, cycle, *settings, *sensors])
    _write_matrix(root / "train_FD001.txt", train_rows)
    _write_matrix(root / "test_FD001.txt", test_rows)
    _write_matrix(root / "RUL_FD001.txt", [[3], [5], [7]])


def test_fd001_loader_exposes_test_histories_without_official_labels(tmp_path):
    _make_fd001_fixture(tmp_path)

    histories = load_engine_histories(tmp_path, "test")

    assert sorted(histories) == [1, 2, 3]
    assert histories[1].shape == (8, 25)
    assert histories[1][-1, 0] == 8

    # Inference history loading must not require either training data or the
    # official test RUL labels, which are reserved for offline scoring.
    (tmp_path / "train_FD001.txt").unlink()
    (tmp_path / "RUL_FD001.txt").unlink()
    assert load_engine_histories(tmp_path, "test")[1].shape == (8, 25)
    with pytest.raises(ValueError, match="split"):
        load_engine_histories(tmp_path, "validation")


def test_fd001_features_and_inference_validate_history(tmp_path):
    _make_fd001_fixture(tmp_path)
    raw_history = load_engine_histories(tmp_path, "train")[1]

    assert feature_vector(raw_history).shape == (73,)
    with pytest.raises(ValueError, match="consecutive"):
        feature_vector(raw_history[[1, 0]])
    with pytest.raises(ValueError, match="positive integers"):
        feature_vector([[1.5, *raw_history[0, 1:]]])
    with pytest.raises(ValueError, match="consecutive"):
        feature_vector(raw_history[[0, 2]])
    with pytest.raises(ValueError, match="25 values"):
        feature_vector([[1, 2, 3]])


def test_training_is_grouped_reproducible_and_round_trips_artifact(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_fd001_fixture(data_dir)
    first_path = tmp_path / "one.joblib"
    second_path = tmp_path / "two.joblib"

    first = train_fd001(data_dir, first_path, random_seed=7, n_estimators=12)
    second = train_fd001(data_dir, second_path, random_seed=7, n_estimators=12)

    assert first == second
    validation = first["validation"]
    assert validation["train_engine_count"] + validation["held_out_engine_count"] == 6
    assert validation["train_engine_count"] > 0
    assert validation["held_out_engine_count"] > 0
    assert set(validation["held_out_engine_ids"]).isdisjoint({1, 2, 3, 4, 5, 6} - set(validation["held_out_engine_ids"]))
    assert validation["random_forest"]["count"] == validation["held_out_engine_count"]
    assert validation["hist_gradient_boosting"]["count"] == validation["held_out_engine_count"]
    assert first["official_test"]["test_observation_count"] == 3
    assert first["training_details"]["official_test_labels_used_for_training"] is False
    assert "nasa_asymmetric_score" in first["official_test"]["random_forest"]
    assert "uncertainty" in first["official_test"]["random_forest"]
    assert first["official_test"]["median_rul_baseline"]["rul_le_30_cycles"]["confusion"]

    model = FD001RULModel.load(first_path)
    history = load_engine_histories(data_dir, "test")[1]
    prediction = model.predict_history(history)
    assert prediction["rul_cycles"] >= 0
    assert prediction["model_version"] == "cmapss-fd001-rf-v1"
    assert prediction["observation_count"] == 8
    assert prediction["is_synthetic"] is True
    assert model.metadata["numpy_version"]
    assert model.metadata["scikit_learn_version"]
    assert model.metadata["train_file_sha256"]
    repeated_prediction = FD001RULModel.load(second_path).predict_history(history)
    assert repeated_prediction["rul_cycles"] == pytest.approx(
        prediction["rul_cycles"], rel=1e-12, abs=1e-12
    )
    assert {key: value for key, value in repeated_prediction.items() if key != "rul_cycles"} == {
        key: value for key, value in prediction.items() if key != "rul_cycles"
    }
    saved_metrics = evaluate_saved_artifact(data_dir, first_path)
    assert saved_metrics["model_version"] == "cmapss-fd001-rf-v1"
    assert len(saved_metrics["artifact_sha256"]) == 64
    assert saved_metrics["official_test"]["count"] == 3


def test_missing_artifact_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="artifact is unavailable"):
        FD001RULModel.load(tmp_path / "missing.joblib")


def test_tree_spread_envelope_and_indicative_drivers_are_distinct_and_bounded(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_fd001_fixture(data_dir)
    artifact = tmp_path / "model.joblib"
    train_fd001(data_dir, artifact, target_cap=5, n_estimators=12)
    model = FD001RULModel.load(artifact)
    histories = load_engine_histories(data_dir, "test")
    reference = healthy_training_reference(data_dir, target_cap=5)

    first = model.predict_history(histories[1], reference)
    second = model.predict_history(histories[1], reference)

    for key in ("rul_cycles", "rul_low", "rul_high", "tree_rul_p10", "tree_rul_p90", "rul_std"):
        assert first[key] == pytest.approx(second[key], rel=1e-12, abs=1e-12)
    assert {key: value for key, value in first.items()
            if key not in {"rul_cycles", "rul_low", "rul_high", "tree_rul_p10",
                           "tree_rul_p90", "rul_std"}} == {
        key: value for key, value in second.items()
        if key not in {"rul_cycles", "rul_low", "rul_high", "tree_rul_p10",
                       "tree_rul_p90", "rul_std"}
    }
    assert first["rul_low"] <= first["rul_cycles"] <= first["rul_high"]
    assert first["tree_rul_p10"] <= first["tree_rul_p90"]
    assert first["rul_std"] >= 0
    assert first["rul_low"] <= first["tree_rul_p10"]
    assert first["rul_high"] >= first["tree_rul_p90"]
    assert "uncalibrated" in first["rul_uncertainty_method"]
    assert len(first["top_drivers"]) <= 5
    assert all(driver["feature"] != "cycle" for driver in first["top_drivers"])
    assert all(abs(driver["contribution_score"]) <= 5 for driver in first["top_drivers"])
    assert all(driver["direction"] in {"above_reference", "below_reference"}
               for driver in first["top_drivers"])
    assert "indicative" in first["driver_method"]


def test_official_error_metrics_follow_asymmetric_score_and_30_cycle_rule():
    true = np.asarray([10.0, 50.0, 20.0, 80.0])
    prediction = np.asarray([0.0, 20.0, 40.0, 70.0])
    expected_score = np.expm1(10 / 13) + np.expm1(30 / 13) + np.expm1(2) + np.expm1(10 / 13)
    assert _nasa_score(true, prediction) == pytest.approx(expected_score, abs=1e-4)
    result = _life_classification(true, prediction)
    assert result["confusion"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert result["precision"] == result["recall"] == result["f1"] == 0.5
