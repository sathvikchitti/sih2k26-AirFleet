"""Read-only synthetic evaluation endpoints."""

import json
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..evaluation.scale_simulation import REPORT_JSON_PATH

router = APIRouter(tags=["evaluation"])

FD001_METRICS_PATH = Path(__file__).resolve().parents[2] / "models" / "cmapss_fd001_rf_v1_metrics.json"


def _finite_number(value, *, minimum=0.0, maximum=None):
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value >= minimum
        and (maximum is None or value <= maximum)
    )


def _fd001_metrics_projection(result):
    """Validate and project only the saved production-artifact reference."""
    if (not isinstance(result, dict) or result.get("dataset") != "NASA C-MAPSS FD001"
            or result.get("evaluation_type") != "offline_simulation"):
        return None
    reference = result.get("existing_artifact_reference")
    if not isinstance(reference, dict):
        return None
    version = reference.get("model_version")
    digest = reference.get("artifact_sha256")
    official = reference.get("official_test")
    uncertainty = official.get("uncertainty") if isinstance(official, dict) else None
    raw = uncertainty.get("raw_tree_p10_p90") if isinstance(uncertainty, dict) else None
    inclusive = uncertainty.get("mean_inclusive_envelope") if isinstance(uncertainty, dict) else None
    metrics = official
    protocol = reference.get("protocol")
    source_note = result.get("dataset_source_note")
    provenance = (result.get("training_details") or {}).get("provenance") if isinstance(
        result.get("training_details"), dict
    ) else None
    if not all(isinstance(value, str) and value.strip() for value in
               (version, digest, protocol, source_note, provenance)):
        return None
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        return None
    if not isinstance(metrics, dict) or not isinstance(raw, dict) or not isinstance(inclusive, dict):
        return None
    count = metrics.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        return None
    metric_values = {
        "mae_cycles": metrics.get("mae_cycles"),
        "rmse_cycles": metrics.get("rmse_cycles"),
        "nasa_asymmetric_score": metrics.get("nasa_asymmetric_score"),
    }
    if not all(_finite_number(value) for value in metric_values.values()):
        return None
    for interval in (raw, inclusive):
        if (not _finite_number(interval.get("coverage"), maximum=1.0)
                or not _finite_number(interval.get("mean_width_cycles"))
                or interval.get("calibrated", False) is not False):
            return None

    return {
        "status": "available",
        "source": "existing_artifact_reference",
        "evaluation_type": result.get("evaluation_type"),
        "dataset": result["dataset"],
        "unit": "cycles",
        "model": {"version": version, "artifact_sha256": digest.lower()},
        "official_test": {
            "engine_count": count,
            "protocol": protocol,
            "metrics": metric_values,
            "uncertainty": {
                "raw_tree_p10_p90": {
                    "reference_quantile_range": [10, 90],
                    "nominal_coverage": 0.8,
                    "observed_coverage": raw["coverage"],
                    "mean_width_cycles": raw["mean_width_cycles"],
                    "calibrated": False,
                },
                "mean_inclusive_envelope": {
                    "reference_quantile_range": [10, 90],
                    "nominal_coverage": None,
                    "observed_coverage": inclusive["coverage"],
                    "mean_width_cycles": inclusive["mean_width_cycles"],
                    "calibrated": False,
                },
            },
        },
        "scope": {"dataset_source_note": source_note, "provenance": provenance},
        "calibrated": False,
    }


@router.get("/api/ml/fd001/metrics")
def fd001_metrics():
    """Expose a validated projection of saved metrics; never evaluate/train here."""
    try:
        report = json.loads(FD001_METRICS_PATH.read_text(encoding="utf-8"))
        projection = _fd001_metrics_projection(report)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        projection = None
    if projection is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "FD001 metrics unavailable", "metrics_status": "unavailable"},
        )
    return projection


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
