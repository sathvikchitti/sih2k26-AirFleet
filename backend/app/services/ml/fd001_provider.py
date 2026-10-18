"""Explicit demo adapter from aircraft IDs to simulated FD001 test engines."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .base import PredictionValidationError, risk_band
from .fd001_model import FD001RULModel, load_engine_histories


# Stable one-to-one demo mapping. These aircraft IDs and the NASA engine
# trajectories are separate simulated examples; they are not linked telemetry.
AIRCRAFT_TO_FD001_ENGINE = {
    "A17": 1, "A19": 2, "A21": 3, "A23": 4, "A24": 5,
    "A26": 6, "A28": 7, "A32": 8, "A33": 9, "A35": 10,
}
HEALTH_RUL_CAP_CYCLES = 125
HEALTH_DERIVATION = "round(100 * min(max(rul_cycles, 0), 125) / 125)"


class FD001MLProvider:
    """Predict RUL cycles from a saved model and fixed simulated histories."""

    name = "fd001-random-forest"
    trend_source = "fd001_model_prefix_predictions"

    def __init__(self, model: FD001RULModel, histories: dict[int, object]):
        self._model = model
        self._histories = histories

    @classmethod
    def from_environment(cls) -> "FD001MLProvider":
        backend_root = Path(__file__).resolve().parents[3]
        repo_root = backend_root.parent
        model_path = Path(os.getenv(
            "FD001_MODEL_PATH", str(backend_root / "models" / "cmapss_fd001_rf_v1.joblib")
        ))
        data_dir = Path(os.getenv("FD001_DATA_DIR", str(repo_root / "CMAPSSData")))
        model = FD001RULModel.load(model_path)
        histories = load_engine_histories(data_dir, split="test")
        missing = sorted(set(AIRCRAFT_TO_FD001_ENGINE.values()) - set(histories))
        if missing:
            raise ValueError(f"FD001 test histories are missing mapped engine IDs: {missing}")
        return cls(model, histories)

    @staticmethod
    def health_from_rul(rul_cycles: float) -> int:
        bounded = min(max(float(rul_cycles), 0.0), float(HEALTH_RUL_CAP_CYCLES))
        return int(round(100.0 * bounded / HEALTH_RUL_CAP_CYCLES))

    def predict(self, aircraft_id: str) -> dict:
        key = str(aircraft_id).strip().upper()
        engine_id = AIRCRAFT_TO_FD001_ENGINE.get(key)
        if engine_id is None:
            raise ValueError(f"no FD001 demo engine history is mapped to aircraft {key!r}")
        history = self._histories.get(engine_id)
        if history is None:
            raise ValueError(f"mapped FD001 engine history {engine_id} is unavailable")

        output = self._model.predict_history(history)
        rul = float(output["rul_cycles"])
        health = self.health_from_rul(rul)
        level = risk_band(health)
        needs_triage = level in {"HIGH", "CRITICAL"}
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "aircraft_id": key,
            "timestamp": timestamp,
            "prediction_timestamp": timestamp,
            "prediction_horizon_hours": None,
            "health_score": health,
            "health_score_derived": "linear_rul_cap_125_cycles",
            "failure_probability": None,
            "probability_status": "unavailable",
            "rul": rul,
            "remaining_useful_life": rul,
            "rul_unit": "cycles",
            "risk_level": level,
            "predicted_issue": (
                f"FD001 RUL indicator is {rul:.1f} cycles; human subsystem diagnosis required"
                if needs_triage else None
            ),
            # FD001 predicts RUL only; it does not classify a subsystem or part.
            "subsystem": None,
            "predicted_maintenance": needs_triage,
            "source": "cmapss-fd001-demo-history",
            "provider": self.name,
            "model_version": output["model_version"],
            "history_source": "synthetic_fd001_test_engine_history",
            "trend_source": self.trend_source,
            "is_synthetic": True,
            "metadata": {
                "engine_id": engine_id,
                "observation_cycle_count": output["observation_count"],
                "prediction_timestamp": timestamp,
                "health_score_derivation": HEALTH_DERIVATION,
            },
        }

    def degradation_trend(self, aircraft_id: str, points: int = 12) -> list[int]:
        """Model-derived health indicators on prefixes of the mapped history."""
        key = str(aircraft_id).strip().upper()
        engine_id = AIRCRAFT_TO_FD001_ENGINE.get(key)
        if engine_id is None or engine_id not in self._histories:
            raise ValueError(f"no FD001 demo engine history is mapped to aircraft {key!r}")
        history = self._histories[engine_id]
        if points < 1:
            raise ValueError("points must be positive")
        import numpy as np

        end_indices = np.unique(np.linspace(1, len(history), min(points, len(history)), dtype=int))
        return [
            self.health_from_rul(self._model.predict_history(history[:end])['rul_cycles'])
            for end in end_indices
        ]
