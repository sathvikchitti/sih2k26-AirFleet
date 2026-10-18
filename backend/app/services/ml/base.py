"""ML integration boundary (spec section 2).

The application depends on `MLProvider` and nothing else. Swapping the mock
for XGBoost / Random Forest / LSTM / Transformer means implementing
`predict()` (and optionally `predict_many()` / `degradation_trend()`) and
registering it — no calling code changes.

A provider reports *condition*, never a part number. Deciding which component
or resource an aircraft needs is the maintenance knowledge layer's job
(`app/domain/knowledge.py`), because that mapping belongs to fleet
engineering, not to a degradation model.

Contract shape returned by `predict()`:

    {
        "aircraft_id": "A17",
        "timestamp": "2026-10-06T08:00:00+00:00",
        "health_score": 41,             # 0-100
        "failure_probability": 0.78,    # 0-1 or null when unavailable
        "rul": 12,                      # remaining useful life, flight hours
        "confidence": 0.91,             # 0-1
        "risk_level": "HIGH",           # LOW | MEDIUM | HIGH | CRITICAL
        "predicted_issue": "High-pressure subsystem degradation",
        "subsystem": "HIGH_PRESSURE",
        "predicted_maintenance": true,
        "source": "mock-ml-service",
    }
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from ...domain.enums import RiskLevel

_PROVIDER_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ml-provider")


@runtime_checkable
class MLProvider(Protocol):
    """Everything the application may ask of a model."""

    name: str

    def predict(self, aircraft_id: str) -> dict:
        """Predict condition for one aircraft.

        Must return the contract documented in this module. `subsystem` and
        `predicted_issue` may be absent, but must never be a part number.
        """
        ...

    def predict_many(self, aircraft_ids: list[str]) -> list[dict]:
        """Batch prediction. Default implementation loops `predict`."""
        return [self.predict(aid) for aid in aircraft_ids]

    def degradation_trend(self, aircraft_id: str, points: int = 12) -> list[int]:
        """Historical health scores, oldest first. Illustrative by default."""
        pred = self.predict(aircraft_id)
        score = pred.get("health_score", 85)
        start = min(98, score + 22)
        step = (start - score) / max(1, points - 1)
        return [round(start - step * i) for i in range(points)]


def risk_band(health_score: float, failure_probability: float | None = None) -> str:
    """Return the more severe band from health and probability signals.

    Health boundaries are <45 CRITICAL, <60 HIGH, <80 MEDIUM, else LOW.
    Failure probability boundaries are >=.70 CRITICAL, >=.45 HIGH,
    >=.25 MEDIUM, else LOW. Signals are combined by taking the most severe
    band, so contradictory inputs cannot lower operational concern.
    """
    fs = _bounded_number(health_score, "health_score", 0.0, 100.0)
    bands = [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]
    health_band = (RiskLevel.CRITICAL if fs < 45 else RiskLevel.HIGH if fs < 60
                   else RiskLevel.MEDIUM if fs < 80 else RiskLevel.LOW)
    chosen = health_band
    if failure_probability is not None:
        probability = _bounded_number(failure_probability, "failure_probability", 0.0, 1.0)
        probability_band = (RiskLevel.CRITICAL if probability >= .70 else RiskLevel.HIGH
                            if probability >= .45 else RiskLevel.MEDIUM
                            if probability >= .25 else RiskLevel.LOW)
        chosen = min((health_band, probability_band), key=lambda band: bands.index(band))
    return chosen.value


class PredictionValidationError(ValueError):
    """A provider returned data that must not enter operational decisions."""


def _bounded_number(value, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PredictionValidationError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise PredictionValidationError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def validate_prediction(prediction: dict, aircraft_id: str, *, now: datetime | None = None,
                        max_age: timedelta = timedelta(hours=24)) -> dict:
    """Validate and normalize the provider contract before operational use.

    The provider's risk label is informational; backend thresholds are
    authoritative. Legacy `timestamp` and `rul` names remain supported.
    """
    if not isinstance(prediction, dict):
        raise PredictionValidationError("prediction must be an object")
    requested_id = str(aircraft_id).strip().upper()
    returned_id = str(prediction.get("aircraft_id", "")).strip().upper()
    if not requested_id or returned_id != requested_id:
        raise PredictionValidationError("prediction aircraft_id does not match request")

    timestamp_value = prediction.get("prediction_timestamp", prediction.get("timestamp"))
    if not isinstance(timestamp_value, str):
        raise PredictionValidationError("prediction_timestamp is required")
    try:
        timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredictionValidationError("prediction_timestamp must be ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise PredictionValidationError("prediction_timestamp must include a timezone")
    now = now or datetime.now(timezone.utc)
    age = now - timestamp.astimezone(timezone.utc)
    if age < timedelta(minutes=-5):
        raise PredictionValidationError("prediction_timestamp is in the future")
    if age > max_age:
        raise PredictionValidationError("prediction is stale")

    health = _bounded_number(prediction.get("health_score"), "health_score", 0, 100)
    raw_probability = prediction.get("failure_probability")
    probability = (None if raw_probability is None else
                   _bounded_number(raw_probability, "failure_probability", 0, 1))
    rul = prediction.get("remaining_useful_life", prediction.get("rul"))
    unit = prediction.get("rul_unit")
    if rul is not None:
        rul = _bounded_number(rul, "remaining_useful_life", 0, 1e9)
        if unit not in {"flight_hours", "cycles"}:
            raise PredictionValidationError("rul_unit must be flight_hours or cycles")
    interval_fields = ("rul_low", "rul_high")
    if any(prediction.get(key) is not None for key in interval_fields):
        if rul is None or any(prediction.get(key) is None for key in interval_fields):
            raise PredictionValidationError("rul_low and rul_high require an RUL point prediction")
        low = _bounded_number(prediction["rul_low"], "rul_low", 0, 1e9)
        high = _bounded_number(prediction["rul_high"], "rul_high", 0, 1e9)
        if low > rul or high < rul or low > high:
            raise PredictionValidationError("RUL interval must contain the point prediction")
    raw_interval_fields = ("tree_rul_p10", "tree_rul_p90")
    if any(prediction.get(key) is not None for key in raw_interval_fields):
        if any(prediction.get(key) is None for key in raw_interval_fields):
            raise PredictionValidationError("tree RUL percentiles must be supplied together")
        raw_low = _bounded_number(prediction["tree_rul_p10"], "tree_rul_p10", 0, 1e9)
        raw_high = _bounded_number(prediction["tree_rul_p90"], "tree_rul_p90", 0, 1e9)
        if raw_low > raw_high:
            raise PredictionValidationError("tree RUL p10 must not exceed p90")
    if prediction.get("rul_std") is not None:
        _bounded_number(prediction["rul_std"], "rul_std", 0, 1e9)
    for name in ("rul_uncertainty_method", "driver_method"):
        value = prediction.get(name)
        if value is not None and not isinstance(value, str):
            raise PredictionValidationError(f"{name} must be text or null")
    drivers = prediction.get("top_drivers")
    if drivers is not None and (not isinstance(drivers, list) or len(drivers) > 5):
        raise PredictionValidationError("top_drivers must be a list of at most 5 entries")
    if isinstance(drivers, list):
        for driver in drivers:
            if not isinstance(driver, dict):
                raise PredictionValidationError("top_drivers entries must be objects")
            if driver.get("direction") not in {"above_reference", "below_reference"}:
                raise PredictionValidationError("top driver direction is invalid")
            _bounded_number(driver.get("contribution_score"), "top driver contribution_score", -5, 5)
    horizon = prediction.get("prediction_horizon_hours", prediction.get("prediction_horizon"))
    if isinstance(horizon, dict):
        horizon = horizon.get("hours")
    if horizon is None and unit == "cycles":
        # FD001 reports cycles. Do not silently convert cycles into flight hours
        # just to satisfy this legacy hours-based horizon field.
        horizon_status = "unavailable"
    else:
        horizon = _bounded_number(horizon, "prediction_horizon_hours", 0.001, 8760)
        horizon_status = "available"
    if prediction.get("confidence") is not None:
        _bounded_number(prediction["confidence"], "confidence", 0, 1)
    model_version = prediction.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise PredictionValidationError("model_version is required")

    result = dict(prediction)
    result.update({
        "aircraft_id": requested_id,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "prediction_timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "prediction_horizon_hours": horizon,
        "prediction_horizon_status": horizon_status,
        "health_score": health,
        "failure_probability": probability,
        "probability_status": "available" if probability is not None else "unavailable",
        "risk_level": risk_band(health, probability),
        "model_version": model_version.strip(),
    })
    if rul is not None:
        result.update({"rul": rul, "remaining_useful_life": rul, "rul_unit": unit})
    return result


def predict_validated(provider: MLProvider, aircraft_id: str, *, timeout_seconds: float = 5.0) -> dict:
    """Call an injected provider and apply the shared operational contract."""
    future = _PROVIDER_EXECUTOR.submit(provider.predict, aircraft_id)
    try:
        prediction = future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        raise PredictionValidationError("prediction provider timed out; prediction unavailable") from exc
    except Exception as exc:
        raise PredictionValidationError(f"prediction unavailable: {exc}") from exc
    return validate_prediction(prediction, aircraft_id)
