"""Read-only synthetic evaluation endpoints."""

import json

from fastapi import APIRouter, HTTPException

from ..evaluation.scale_simulation import REPORT_JSON_PATH

router = APIRouter(tags=["evaluation"])


@router.get("/api/evaluation/summary")
def evaluation_summary():
    """Read the precomputed deterministic synthetic fleet-scale report."""
    try:
        result = json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail="evaluation report unavailable")
    policies = result.get("policies") if isinstance(result, dict) else None
    if (not isinstance(result, dict)
            or result.get("simulated") is not True
            or result.get("evaluation_type") != "deterministic_synthetic_simulation"
            or result.get("real_operational_performance_claimed") is not False
            or result.get("scenario_count") != 300
            or not isinstance(policies, dict)
            or set(policies) != {
                "proposed", "nearest_fcfs", "random_feasible", "local_only_procurement",
            }):
        raise HTTPException(status_code=503, detail="evaluation report unavailable")
    # Raw per-scenario rows remain in the checked-in/generated artifact for
    # reproducibility; the dashboard only needs the aggregate projection.
    result.pop("scenario_results", None)
    return result
