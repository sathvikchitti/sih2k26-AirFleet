"""Reproducible FD001 RUL training and inference helpers.

FD001 targets are remaining operating cycles, not flight hours. Histories
contain only observations available through the requested prediction cycle.
The model artifact uses rolling window summaries and a train-fitted variance
filter; it never needs an engine's eventual failure cycle at inference.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import VarianceThreshold
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
import sklearn


DATA_FILES = ("train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt")
RAW_WIDTH = 25  # cycle + 3 settings + 21 FD001 sensors
WINDOW_CYCLES = 10
FEATURE_NAMES = ("cycle",) + tuple(
    f"{name}_{stat}"
    for name in tuple(f"setting_{i}" for i in range(1, 4))
    + tuple(f"sensor_{i}" for i in range(1, 22))
    for stat in ("last", "mean", "slope")
)
MODEL_VERSION = "cmapss-fd001-rf-v1"


@dataclass(frozen=True)
class FD001Data:
    train_histories: dict[int, np.ndarray]
    test_histories: dict[int, np.ndarray]
    test_rul: dict[int, float]


def _read_matrix(path: Path, expected_columns: int) -> np.ndarray:
    if not path.is_file():
        raise FileNotFoundError(f"required FD001 file is missing: {path}")
    try:
        matrix = np.loadtxt(path, dtype=np.float64, ndmin=2)
    except (ValueError, OSError) as exc:
        raise ValueError(f"could not parse FD001 file {path.name}: {exc}") from exc
    if matrix.ndim != 2 or matrix.shape[1] != expected_columns:
        raise ValueError(f"{path.name} must have {expected_columns} numeric columns")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{path.name} contains non-finite values")
    return matrix


def _split_histories(matrix: np.ndarray, label: str) -> dict[int, np.ndarray]:
    engine_ids = matrix[:, 0].astype(np.int64)
    cycles = matrix[:, 1]
    if (engine_ids < 1).any() or not np.array_equal(matrix[:, 0], engine_ids):
        raise ValueError(f"{label} engine identifiers must be positive integers")
    if (cycles <= 0).any() or not np.equal(cycles, np.floor(cycles)).all():
        raise ValueError(f"{label} cycle numbers must be positive integers")
    histories: dict[int, np.ndarray] = {}
    for engine_id in sorted(set(engine_ids.tolist())):
        rows = matrix[engine_ids == engine_id]
        order = np.argsort(rows[:, 1], kind="stable")
        rows = rows[order]
        if len(rows) == 0 or (np.diff(rows[:, 1]) <= 0).any():
            raise ValueError(f"{label} engine {engine_id} has duplicate or unordered cycles")
        histories[int(engine_id)] = rows[:, 1:].copy()
    return histories


def load_fd001_data(data_dir: str | Path) -> FD001Data:
    """Load authentic FD001 train/test histories and official final RUL labels."""
    root = Path(data_dir)
    train = _split_histories(_read_matrix(root / DATA_FILES[0], 26), "train")
    test = _split_histories(_read_matrix(root / DATA_FILES[1], 26), "test")
    labels = _read_matrix(root / DATA_FILES[2], 1).reshape(-1)
    if len(labels) != len(test):
        raise ValueError(f"RUL_FD001.txt has {len(labels)} labels for {len(test)} test engines")
    if (labels < 0).any():
        raise ValueError("official test RUL labels cannot be negative")
    test_ids = sorted(test)
    return FD001Data(train, test, {engine_id: float(labels[i]) for i, engine_id in enumerate(test_ids)})


def load_engine_histories(data_dir: str | Path, split: str = "test") -> dict[int, np.ndarray]:
    """Return engine histories without identifiers for provider-side mapping.

    `split` is `train` or `test`. Test labels are deliberately not returned by
    this helper, preventing normal inference code from consuming final labels.
    Returned row shape is `[cycle, settings 1..3, sensors 1..21]`.
    """
    if split not in {"train", "test"}:
        raise ValueError("split must be 'train' or 'test'")
    root = Path(data_dir)
    filename = "train_FD001.txt" if split == "train" else "test_FD001.txt"
    return _split_histories(_read_matrix(root / filename, 26), split)


def validate_history(history: Sequence[Sequence[float]]) -> np.ndarray:
    try:
        rows = np.asarray(history, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("history must contain numeric FD001 rows") from exc
    if rows.ndim != 2 or rows.shape[1] != RAW_WIDTH or rows.shape[0] < 1:
        raise ValueError(f"history must contain at least one row with {RAW_WIDTH} values")
    if not np.isfinite(rows).all():
        raise ValueError("history contains non-finite sensor values")
    cycles = rows[:, 0]
    if (cycles <= 0).any() or not np.equal(cycles, np.floor(cycles)).all():
        raise ValueError("history cycles must be positive integers")
    if len(cycles) > 1 and not np.array_equal(np.diff(cycles), np.ones(len(cycles) - 1)):
        raise ValueError("history cycles must be consecutive")
    return rows


def feature_vector(history: Sequence[Sequence[float]], window_cycles: int = WINDOW_CYCLES) -> np.ndarray:
    """Use current cycle and trailing-window last/mean/slope sensor features."""
    rows = validate_history(history)
    window = rows[-window_cycles:]
    x = np.arange(len(window), dtype=np.float64)
    centered_x = x - x.mean()
    denominator = float(centered_x @ centered_x)
    values = [float(rows[-1, 0])]
    for column in range(1, RAW_WIDTH):
        series = window[:, column]
        slope = float(centered_x @ (series - series.mean()) / denominator) if denominator else 0.0
        values.extend((float(series[-1]), float(series.mean()), slope))
    return np.asarray(values, dtype=np.float64)


def _all_prefix_samples(histories: dict[int, np.ndarray], target_cap: int):
    vectors: list[np.ndarray] = []
    targets: list[float] = []
    groups: list[int] = []
    for engine_id in sorted(histories):
        rows = validate_history(histories[engine_id])
        end_cycle = float(rows[-1, 0])
        for end in range(len(rows)):
            vectors.append(feature_vector(rows[:end + 1]))
            targets.append(min(float(target_cap), max(0.0, end_cycle - float(rows[end, 0]))))
            groups.append(engine_id)
    return np.vstack(vectors), np.asarray(targets), np.asarray(groups)


def _last_cutoff_sample(history: np.ndarray, target_cap: int, observed_fraction: float = 0.8):
    """Make one test-like validation observation without exposing later rows."""
    rows = validate_history(history)
    cutoff = max(0, min(len(rows) - 1, int(np.ceil(len(rows) * observed_fraction)) - 1))
    return feature_vector(rows[:cutoff + 1]), min(target_cap, float(rows[-1, 0] - rows[cutoff, 0]))


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "count": int(len(y_true)),
        "mae_cycles": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse_cycles": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
    }


def _range_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, dict]:
    ranges = (("0-24", 0, 25), ("25-49", 25, 50), ("50-99", 50, 100), ("100+", 100, np.inf))
    result = {}
    for name, low, high in ranges:
        mask = (y_true >= low) & (y_true < high)
        result[name] = _metrics(y_true[mask], y_pred[mask]) if mask.any() else {"count": 0, "mae_cycles": None, "rmse_cycles": None}
    return result


def _fit_selector_and_model(x: np.ndarray, y: np.ndarray, seed: int, n_estimators: int):
    selector = VarianceThreshold(threshold=0.0)
    selected = selector.fit_transform(x)
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        min_samples_leaf=3,
        max_features=0.8,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(selected, y)
    return selector.get_support(), model


def train_fd001(
    data_dir: str | Path,
    artifact_path: str | Path,
    random_seed: int = 42,
    target_cap: int = 125,
    validation_fraction: float = 0.2,
    n_estimators: int = 200,
) -> dict:
    """Train/evaluate RF, compare a median baseline, then save a full-train model.

    Validation is grouped by engine. Each held-out validation engine contributes
    one prediction at 80% of its observed trajectory. The official test labels
    are evaluated only after fitting the full-train artifact.
    """
    if target_cap <= 0 or not 0 < validation_fraction < 1 or n_estimators < 1:
        raise ValueError("target_cap and n_estimators must be positive; validation_fraction must be in (0, 1)")
    data_root = Path(data_dir)
    train_histories = load_engine_histories(data_root, "train")
    engine_ids = np.asarray(sorted(train_histories), dtype=np.int64)
    if len(engine_ids) < 2:
        raise ValueError("at least two training engines are required for grouped validation")
    splitter = GroupShuffleSplit(n_splits=1, test_size=validation_fraction, random_state=random_seed)
    train_pos, validation_pos = next(splitter.split(engine_ids, groups=engine_ids))
    train_ids = set(int(engine_ids[i]) for i in train_pos)
    validation_ids = set(int(engine_ids[i]) for i in validation_pos)

    split_train_histories = {key: train_histories[key] for key in sorted(train_ids)}
    x_train, y_train, _ = _all_prefix_samples(split_train_histories, target_cap)
    validation_samples = [_last_cutoff_sample(train_histories[key], target_cap) for key in sorted(validation_ids)]
    x_validation = np.vstack([row[0] for row in validation_samples])
    y_validation = np.asarray([row[1] for row in validation_samples], dtype=np.float64)

    validation_mask, validation_model = _fit_selector_and_model(
        x_train, y_train, random_seed, n_estimators
    )
    rf_validation = np.maximum(0.0, validation_model.predict(x_validation[:, validation_mask]))
    median_validation = np.full(len(y_validation), float(np.median(y_train)))

    x_all, y_all, _ = _all_prefix_samples(train_histories, target_cap)
    final_mask, final_model = _fit_selector_and_model(x_all, y_all, random_seed, n_estimators)

    # Do not open official test labels until all feature selection and fitting
    # has finished. Runtime inference uses load_engine_histories and never reads
    # RUL_FD001.txt at all.
    test_histories = load_engine_histories(data_root, "test")
    test_labels = _read_matrix(data_root / "RUL_FD001.txt", 1).reshape(-1)
    if len(test_labels) != len(test_histories):
        raise ValueError(f"RUL_FD001.txt has {len(test_labels)} labels for {len(test_histories)} test engines")
    if (test_labels < 0).any():
        raise ValueError("official test RUL labels cannot be negative")
    test_ids = sorted(test_histories)
    x_test = np.vstack([feature_vector(test_histories[key]) for key in test_ids])
    y_test = test_labels.astype(np.float64)
    rf_test = np.maximum(0.0, final_model.predict(x_test[:, final_mask]))
    median_test = np.full(len(y_test), float(np.median(y_all)))

    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    metrics = {
        "dataset": "NASA C-MAPSS FD001",
        "dataset_source_note": "Local CMAPSSData files; no substitute or fabricated operational data.",
        "evaluation_type": "offline_simulation",
        "random_seed": int(random_seed),
        "target_cap_cycles": int(target_cap),
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "training_file_sha256": sha256_file(data_root / "train_FD001.txt"),
        "feature_window_cycles": WINDOW_CYCLES,
        "feature_count_before_variance_filter": len(FEATURE_NAMES),
        "train_only_selected_feature_count_validation": int(validation_mask.sum()),
        "train_only_selected_feature_count_final": int(final_mask.sum()),
        "validation": {
            "split": "GroupShuffleSplit by engine id; one observation at 80% of each held-out training trajectory",
            "train_engine_count": len(train_ids),
            "held_out_engine_count": len(validation_ids),
            "train_observation_count": int(len(y_train)),
            "held_out_engine_ids": sorted(validation_ids),
            "random_forest": _metrics(y_validation, rf_validation),
            "median_rul_baseline": _metrics(y_validation, median_validation),
            "random_forest_by_true_rul_range": _range_metrics(y_validation, rf_validation),
            "median_baseline_by_true_rul_range": _range_metrics(y_validation, median_validation),
        },
        "official_test": {
            "protocol": "one prediction from each test engine's final observed row; official RUL_FD001 labels used only for scoring",
            "train_engine_count": len(train_histories),
            "test_engine_count": len(test_ids),
            "test_observation_count": int(len(test_ids)),
            "random_forest": _metrics(y_test, rf_test),
            "median_rul_baseline": _metrics(y_test, median_test),
            "random_forest_by_true_rul_range": _range_metrics(y_test, rf_test),
            "median_baseline_by_true_rul_range": _range_metrics(y_test, median_test),
        },
        "training_details": {
            "features": "current cycle plus last, trailing 10-cycle mean, and trailing linear slope for each setting and sensor",
            "feature_filter": "VarianceThreshold(0.0), fit only on the training-engine samples for each fit",
            "target": "max(0, final_training_cycle - observed_cycle), capped at target_cap_cycles",
            "estimator": "RandomForestRegressor(n_estimators, min_samples_leaf=3, max_features=0.8, fixed random_state)",
            "official_test_labels_used_for_training": False,
            "unit": "cycles",
            "provenance": "synthetic turbofan simulation; not aircraft telemetry or real-aircraft validation",
        },
    }

    artifact = {
        "model_version": MODEL_VERSION,
        "estimator": final_model,
        "selected_features": final_mask.astype(bool),
        "feature_names": FEATURE_NAMES,
        "metadata": {
            "target_cap_cycles": int(target_cap),
            "window_cycles": WINDOW_CYCLES,
            "random_seed": int(random_seed),
            "training_engine_count": len(train_histories),
            "training_observation_count": int(len(y_all)),
            "feature_selection": "train-only variance threshold 0.0",
            "unit": "cycles",
            "source": "NASA C-MAPSS FD001 training trajectories",
            "provenance": "synthetic turbofan simulation; not aircraft telemetry",
            "numpy_version": np.__version__,
            "scikit_learn_version": sklearn.__version__,
            "train_file_sha256": sha256_file(data_root / "train_FD001.txt"),
            "training_config": {
                "random_seed": int(random_seed),
                "target_cap_cycles": int(target_cap),
                "n_estimators": int(n_estimators),
                "min_samples_leaf": 3,
                "max_features": 0.8,
                "feature_window_cycles": WINDOW_CYCLES,
            },
        },
    }
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path, compress=3)
    return metrics


class FD001RULModel:
    """Loaded, reusable inference wrapper for a saved FD001 random forest."""

    def __init__(self, artifact: dict):
        if artifact.get("model_version") != MODEL_VERSION:
            raise ValueError("unsupported FD001 model artifact version")
        self._estimator = artifact["estimator"]
        self._selected = np.asarray(artifact["selected_features"], dtype=bool)
        self.model_version = artifact["model_version"]
        self.metadata = dict(artifact["metadata"])

    @classmethod
    def load(cls, path: str | Path) -> "FD001RULModel":
        artifact_path = Path(path)
        if not artifact_path.is_file():
            raise FileNotFoundError(f"FD001 model artifact is unavailable: {artifact_path}")
        return cls(joblib.load(artifact_path))

    def predict_history(self, history: Sequence[Sequence[float]]) -> dict:
        rows = validate_history(history)
        features = feature_vector(rows, int(self.metadata.get("window_cycles", WINDOW_CYCLES)))
        prediction = float(self._estimator.predict(features[self._selected].reshape(1, -1))[0])
        return {
            "rul_cycles": max(0.0, prediction),
            "model_version": self.model_version,
            "observation_count": len(rows),
            "source": "nasa-cmapss-fd001-random-forest",
            "is_synthetic": True,
        }
