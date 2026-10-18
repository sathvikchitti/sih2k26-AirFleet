"""Regression checks for paired effects in the generated README summary."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update_readme_summary.py"
SPEC = importlib.util.spec_from_file_location("update_readme_summary", SCRIPT)
assert SPEC and SPEC.loader
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def test_summary_reports_sharing_minus_local_paired_effects(monkeypatch):
    model_metrics = {
        "existing_artifact_reference": {
            "artifact_sha256": "a" * 64,
            "official_test": {
                "mae_cycles": 13.7862,
                "rmse_cycles": 18.6998,
                "uncertainty": {"mean_inclusive_envelope": {}},
                "rul_le_30_cycles": {},
            }
        }
    }
    paired = {
        "local_only_procurement": {
            "time_weighted_availability_pct_points": {
                "mean": -5.049701,
                "ci95": {"lower": -5.244893, "upper": -4.853157},
            },
            "summed_censored_aircraft_hours_lost": {
                "mean": 96.954333,
                "ci95": {"lower": 93.356092, "upper": 100.625117},
            },
        },
        "nearest_fcfs": {
            "time_weighted_availability_pct_points": {"ci95": {"lower": -0.02, "upper": 0.02}},
            "summed_censored_aircraft_hours_lost": {"ci95": {"lower": -0.3, "upper": 0.3}},
            "unserved_work_order_rate_pct_points": {"ci95": {"lower": -0.4, "upper": 0.4}},
        },
    }
    scale_report = {
        "evaluation_type": "deterministic_synthetic_simulation",
        "real_operational_performance_claimed": False,
        "scenario_count": 300,
        "horizon_unit": "hours",
        "policies": {name: {} for name in ("proposed", "nearest_fcfs", "random_feasible", "local_only_procurement")},
        "comparison": {"paired_deltas_vs_proposed": paired},
    }

    def fake_read_json(path):
        return model_metrics if path == summary.MODEL_METRICS else scale_report

    monkeypatch.setattr(summary, "_read_json", fake_read_json)
    measured_line = summary.render_lines()[2]

    assert "Sharing minus local-only was +5.05 pp availability" in measured_line
    assert "95% paired CI +4.85 to +5.24" in measured_line
    assert "-4.04 censored aircraft-days lost" in measured_line
    assert "95% paired CI -4.19 to -3.89" in measured_line
    assert "nearest-FCFS differences were inconclusive" in measured_line
