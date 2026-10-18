"""ML health endpoints — the contract the ML teammate owns.

`GET /api/health/{aircraft_id}` returns the model output plus a
`maintenance` block contributed by the knowledge layer. The model part of the
payload never changes when a real model is swapped in.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..repositories import AircraftRepository, PredictionHistoryRepository
from ..services import compatibility
from ..services.ml import get_provider

router = APIRouter(tags=["health"])


@router.get("/api/health/{aircraft_id}")
def health(aircraft_id: str):
    """ML prediction contract — UI consumes ONLY this shape.

    `required_component` is retained at the top level for the existing UI, but
    it is derived by the maintenance knowledge layer, not the model. The model
    output itself carries only condition signals plus a subsystem.
    """
    if AircraftRepository.get(aircraft_id) is None:
        raise HTTPException(404, "unknown aircraft")
    return compatibility.get_prediction_with_component(aircraft_id)


@router.get("/api/health")
def all_health():
    return [
        compatibility.get_prediction_with_component(a["id"])
        for a in AircraftRepository.list_all()
    ]


@router.get("/api/predictions/{aircraft_id}/history")
def prediction_history(aircraft_id: str):
    """Historical predictions (spec section 16).

    Distinct from `/trend`: this is recorded prediction history, not an
    illustrative curve.
    """
    if AircraftRepository.get(aircraft_id) is None:
        raise HTTPException(404, "unknown aircraft")
    rows = PredictionHistoryRepository.for_aircraft(aircraft_id)
    return {
        "aircraft_id": aircraft_id.upper(), "predictions": rows, "count": len(rows),
        "history_source": "mixed_synthetic_and_recorded" if any(
            row.get("history_source") == "recorded" for row in rows
        ) else "illustrative",
        "is_synthetic": any(row.get("is_synthetic", True) for row in rows),
    }
