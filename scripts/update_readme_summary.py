"""Refresh the five-line README evidence summary from local evaluation reports.

Run from any directory with `python scripts/update_readme_summary.py`.
The script reads the existing production-model metrics and the checked-in
synthetic scale-evaluation JSON; it does not retrain models or run simulations.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MODEL_METRICS = ROOT / "backend" / "models" / "cmapss_fd001_rf_v1_metrics.json"
SCALE_REPORT = ROOT / "backend" / "app" / "evaluation" / "results" / "scale_simulation.json"
START = "<!-- GENERATED EVIDENCE SUMMARY START -->"
END = "<!-- GENERATED EVIDENCE SUMMARY END -->"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read required evaluation report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Expected an object in evaluation report {path}")
    return value


def _required(mapping: dict, *keys: str):
    value = mapping
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise SystemExit(f"Missing report field: {'.'.join(keys)}")
        value = value[key]
    return value


def _fmt(value: float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


def render_lines() -> list[str]:
    metrics = _read_json(MODEL_METRICS)
    scale = _read_json(SCALE_REPORT)
    model = _required(metrics, "existing_artifact_reference", "official_test")
    uncertainty = _required(model, "uncertainty", "mean_inclusive_envelope")
    threshold = _required(model, "rul_le_30_cycles")
    policies = _required(scale, "policies")
    if (scale.get("evaluation_type") != "deterministic_synthetic_simulation"
            or scale.get("real_operational_performance_claimed") is not False
            or scale.get("scenario_count") != 300
            or scale.get("horizon_unit") != "hours"):
        raise SystemExit("Scale report does not match the expected synthetic evaluation contract")

    proposed = _required(policies, "proposed")
    nearest = _required(policies, "nearest_fcfs")
    random_policy = _required(policies, "random_feasible")
    local_only = _required(policies, "local_only_procurement")
    paired = _required(scale, "comparison", "paired_deltas_vs_proposed")
    deltas = [
        _required(paired, "nearest_fcfs", "time_weighted_availability_pct_points", "ci95"),
        _required(paired, "nearest_fcfs", "summed_censored_aircraft_hours_lost", "ci95"),
        _required(paired, "nearest_fcfs", "unserved_work_order_rate_pct_points", "ci95"),
    ]
    intervals_include_zero = all(float(row["lower"]) <= 0 <= float(row["upper"]) for row in deltas)
    if not intervals_include_zero:
        raise SystemExit("Nearest-policy paired intervals no longer support the generated README wording")

    validation = _required(metrics, "validation", "random_forest")
    official_test = model
    sha = _required(metrics, "existing_artifact_reference", "artifact_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise SystemExit("Missing valid production artifact SHA-256 in metrics report")

    availability_ci = _required(
        paired, "nearest_fcfs", "time_weighted_availability_pct_points", "ci95"
    )
    return [
        "- Problem: aircraft condition, maintenance, and spares records are fragmented, delaying readiness decisions.",
        "- Solution: an integrated FD001 RUL demo links model evidence to human-approved maintenance and resource workflows.",
        (f"- Measured: FD001 official-test MAE/RMSE {_fmt(_required(official_test, 'mae_cycles'))}/"
         f"{_fmt(_required(official_test, 'rmse_cycles'))} cycles; production-policy availability "
         f"{_fmt(proposed['mean_time_weighted_availability_pct'], 2)}% vs nearest-FCFS "
         f"{_fmt(nearest['mean_time_weighted_availability_pct'], 2)}% across {scale['scenario_count']} paired scenarios "
         f"(95% paired interval for the difference [{_fmt(availability_ci['lower'], 3)}, "
         f"{_fmt(availability_ci['upper'], 3)}] percentage points)."),
        f"- Run locally: `.{chr(92)}run_demo.ps1` (Windows PowerShell) or `./run_demo.sh` (macOS/Linux).",
        "- Evidence is from NASA C-MAPSS and synthetic fleet scenarios; intervals are uncalibrated and results are not real-fleet performance.",
    ]


def update_readme(*, check_only: bool = False) -> bool:
    text = README.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit("README must contain exactly one generated-summary marker pair")
    before, rest = text.split(START, 1)
    _old, after = rest.split(END, 1)
    # Keep the generated five-line executive summary immediately below the title.
    body = before + after
    body = re.sub(r"\n## Current measured evidence\n", "\n", body, count=1)
    body = re.sub(r"\nRefresh these five lines[^\n]*\n", "\n", body, count=1)
    title, separator, remainder = body.partition("\n")
    if not separator or not title.startswith("# "):
        raise SystemExit("README must begin with a level-one project title")
    block = "\n" + "\n".join(render_lines()) + "\n"
    refresh_note = (
        "Refresh these five lines from the existing model metrics and scale-simulation JSON with "
        "`python scripts/update_readme_summary.py`; this reads the reports without retraining or rerunning simulations."
    )
    updated = (
        title + "\n\n" + START + block + END + "\n\n" + refresh_note
        + "\n\n" + remainder.lstrip("\n")
    )
    updated = updated.replace("\n\n\n## Run the FD001 demo", "\n\n## Run the FD001 demo", 1)
    if check_only:
        if text != updated:
            raise SystemExit("README evidence summary is stale; run python scripts/update_readme_summary.py")
        return False
    if text != updated:
        README.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


if __name__ == "__main__":
    import sys

    changed = update_readme(check_only="--check" in sys.argv[1:])
    print("README evidence summary is current." if not changed else "Updated five-line README evidence summary.")
