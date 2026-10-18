"""Bases and fleet availability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..data import BASES, DISTANCES_KM
from ..repositories import AircraftRepository, InventoryRepository
from ..services import availability_service
from ..services.readiness_service import readiness_simulation

router = APIRouter(tags=["fleet", "bases"])


@router.get("/api/fleet/overview")
def fleet_overview():
    """Calculated availability — never a stored constant."""
    return availability_service.fleet_overview()


@router.get("/api/fleet/readiness-simulation")
def readiness_what_if(work_order_ids: list[str] | None = Query(default=None),
                       horizon_hours: float = Query(default=48.0, ge=0, le=168)):
    """Compare read-only no-action, nearest-feasible, and proposed plans."""
    return readiness_simulation(work_order_ids=work_order_ids, horizon_hours=horizon_hours)


@router.get("/api/bases")
def bases():
    return [
        {**b, "aircraft": [a["id"] for a in AircraftRepository.list_by_base(b["id"])]}
        for b in BASES
    ]


@router.get("/api/bases/{base_id}")
def base_detail(base_id: str):
    base = next((b for b in BASES if b["id"] == base_id), None)
    if base is None:
        raise HTTPException(404, "unknown base")
    return {
        **base,
        "aircraft": AircraftRepository.list_by_base(base_id),
        "availability": availability_service.base_overview(base_id),
        "inventory": [
            i for i in InventoryRepository.list_all() if i["base_id"] == base_id
        ],
    }


@router.get("/api/demo/distances")
def distances():
    return {
        "alpha-bravo": {"km": DISTANCES_KM[("alpha", "bravo")], "eta_h": 2.0},
        "alpha-charlie": {"km": DISTANCES_KM[("alpha", "charlie")], "eta_h": 6.3},
        "bravo-charlie": {"km": DISTANCES_KM[("bravo", "charlie")], "eta_h": 4.3},
    }
