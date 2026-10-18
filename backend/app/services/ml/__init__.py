"""ML integration boundary.

`app.services.ml` is the ONLY place the application touches a model.
"""

from .base import MLProvider, PredictionValidationError, predict_validated, risk_band, validate_prediction
from .mock_provider import MockMLProvider, get_provider, set_provider

__all__ = ["MLProvider", "PredictionValidationError", "predict_validated", "validate_prediction", "risk_band", "MockMLProvider", "get_provider", "set_provider"]
