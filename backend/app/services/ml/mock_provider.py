"""MOCK ML PROVIDER — STATE A (POC).

Deterministic stand-in for a real degradation model. Replace the body of
`predict()` with model inference (or an HTTP call to the ML service) and
nothing else in the application has to change.

Deliberate constraint (spec section 2): this provider reports the degraded
**subsystem**, never a part number. It has no access to `PARTS`. Mapping
subsystem -> component is `app/domain/knowledge.py`'s responsibility.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .base import risk_band as _risk_band

# Re-exported so callers (and the seeder) can share one banding function.
risk_band = _risk_band

# Deterministic demo predictions. `subsystem` / `predicted_issue` are what a
# real model would emit from sensor data; they are not part identifiers.
# Labels in this table are retained only for provenance. The backend always
# recomputes risk from health and probability using the shared policy.
_RAW = {
    "A17": {"health_score": 41, "failure_probability": 0.78, "rul": 12, "confidence": 0.91, "risk_level": "HIGH", "subsystem": "HIGH_PRESSURE", "predicted_issue": "High-pressure subsystem degradation"},
    "A19": {"health_score": 92, "failure_probability": 0.06, "rul": 145, "confidence": 0.96, "risk_level": "LOW", "subsystem": None, "predicted_issue": None},
    "A21": {"health_score": 76, "failure_probability": 0.32, "rul": 38, "confidence": 0.88, "risk_level": "MEDIUM", "subsystem": "FUEL_SYSTEM", "predicted_issue": "Fuel system pressure loss"},
    "A23": {"health_score": 88, "failure_probability": 0.10, "rul": 110, "confidence": 0.94, "risk_level": "LOW", "subsystem": None, "predicted_issue": None},
    "A24": {"health_score": 68, "failure_probability": 0.45, "rul": 38, "confidence": 0.86, "risk_level": "MEDIUM", "subsystem": "COOLING", "predicted_issue": "Oil cooling capacity degradation"},
    "A26": {"health_score": 90, "failure_probability": 0.08, "rul": 130, "confidence": 0.95, "risk_level": "LOW", "subsystem": None, "predicted_issue": None},
    "A28": {"health_score": 55, "failure_probability": 0.58, "rul": 20, "confidence": 0.84, "risk_level": "MEDIUM", "subsystem": "FUEL_SYSTEM", "predicted_issue": "Fuel system pressure loss"},
    "A32": {"health_score": 93, "failure_probability": 0.05, "rul": 120, "confidence": 0.97, "risk_level": "LOW", "subsystem": None, "predicted_issue": None},
    "A33": {"health_score": 89, "failure_probability": 0.09, "rul": 105, "confidence": 0.95, "risk_level": "LOW", "subsystem": None, "predicted_issue": None},
    "A35": {"health_score": 72, "failure_probability": 0.38, "rul": 55, "confidence": 0.87, "risk_level": "MEDIUM", "subsystem": "HIGH_PRESSURE", "predicted_issue": "High-pressure subsystem degradation"},
}

# Fallback for an airframe the model has no history for.
_UNKNOWN = {"health_score": 85, "failure_probability": 0.12, "rul": 100, "confidence": 0.80, "risk_level": None, "subsystem": None, "predicted_issue": None}


def raw_predictions() -> dict:
    """The raw table, used to seed prediction history deterministically."""
    return {k: dict(v) for k, v in _RAW.items()}


def raw_prediction(aircraft_id: str) -> dict:
    """Raw values only — no envelope. Used by the seeder."""
    return dict(_RAW.get(str(aircraft_id).upper(), _UNKNOWN))


def risk_band_for(health_score: float) -> str:
    """Risk from health score alone (history seeding has no probability)."""
    return _risk_band(health_score)


class MockMLProvider:
    """STATE A implementation of `MLProvider`."""

    name = "mock-ml-service"
    trend_source = "illustrative_mock_curve"

    def predict(self, aircraft_id: str) -> dict:
        key = str(aircraft_id).upper()
        if key not in _RAW:
            raise ValueError(f"no mock prediction is available for aircraft {key}")
        m = raw_prediction(key)
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "aircraft_id": key,
            "timestamp": timestamp,
            "prediction_timestamp": timestamp,
            "prediction_horizon_hours": 72,
            "health_score": m["health_score"],
            "failure_probability": m["failure_probability"],
            "rul": m["rul"],
            "remaining_useful_life": m["rul"],
            "rul_unit": "flight_hours",
            "confidence": m["confidence"],
            "risk_level": _risk_band(m["health_score"], m["failure_probability"]),
            "predicted_issue": m["predicted_issue"],
            "subsystem": m["subsystem"],
            # True when a subsystem was identified, i.e. maintenance is worth
            # triaging. Still NOT an instruction to raise a work order.
            "predicted_maintenance": bool(m["subsystem"]),
            "source": self.name,
            "model_version": "mock-demo-v1",
            "history_source": "synthetic_provider_output",
            "trend_source": self.trend_source,
            "is_synthetic": True,
        }

    def degradation_trend(self, aircraft_id: str, points: int = 12) -> list[int]:
        """Illustrative decline ending at the current score.

        Recorded history lives in the prediction repository — this is only for
        the detail chart and is clearly labelled as such by the UI.
        """
        pred = self.predict(aircraft_id)
        score = pred.get("health_score", 85)
        start = min(98, score + 22)
        step = (start - score) / max(1, points - 1)
        return [round(start - step * i) for i in range(points)]


_provider: MockMLProvider | None = None


def get_provider():
    """Return the provider selected by `ML_PROVIDER`.

    The mock is the explicit development default. Selecting FD001 never falls
    back to mock if its artifact or example histories are unavailable.
    """
    global _provider
    if _provider is None:
        selected = os.getenv("ML_PROVIDER", "mock").strip().lower()
        if selected == "mock":
            _provider = MockMLProvider()
        elif selected == "fd001":
            from .fd001_provider import FD001MLProvider
            try:
                _provider = FD001MLProvider.from_environment()
            except Exception as exc:
                from .base import PredictionValidationError
                if isinstance(exc, PredictionValidationError):
                    raise
                raise PredictionValidationError(f"FD001 provider unavailable: {exc}") from exc
        else:
            from .base import PredictionValidationError
            raise PredictionValidationError(
                f"unsupported ML_PROVIDER {selected!r}; choose 'mock' or 'fd001'"
            )
    return _provider


def set_provider(provider) -> None:
    """Inject a provider (used by tests and the ML integration)."""
    global _provider
    _provider = provider
