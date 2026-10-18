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


def _fmt_signed(value: float, digits: int = 2) -> str:
    value = float(value)
    return f"{value:+.{digits}f}"


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

    _required(policies, "proposed")
    _required(policies, "nearest_fcfs")
    _required(policies, "random_feasible")
    _required(policies, "local_only_procurement")
    paired = _required(scale, "comparison", "paired_deltas_vs_proposed")
    nearest_deltas = [
        _required(paired, "nearest_fcfs", "time_weighted_availability_pct_points", "ci95"),
        _required(paired, "nearest_fcfs", "summed_censored_aircraft_hours_lost", "ci95"),
        _required(paired, "nearest_fcfs", "unserved_work_order_rate_pct_points", "ci95"),
    ]
    nearest_intervals_include_zero = all(
        float(row["lower"]) <= 0 <= float(row["upper"]) for row in nearest_deltas
    )
    if not nearest_intervals_include_zero:
        raise SystemExit("Nearest-policy paired intervals no longer support the generated README wording")

    local_availability = _required(
        paired, "local_only_procurement", "time_weighted_availability_pct_points"
    )
    local_lost_hours = _required(
        paired, "local_only_procurement", "summed_censored_aircraft_hours_lost"
    )
    # The JSON deltas are local-only minus proposed. Report proposed/Sharing minus
    # local-only, including reversed paired interval endpoints, directly.
    sharing_availability = -float(local_availability["mean"])
    sharing_availability_ci = (
        -float(local_availability["ci95"]["upper"]),
        -float(local_availability["ci95"]["lower"]),
    )
    sharing_lost_days = -float(local_lost_hours["mean"]) / 24.0
    sharing_lost_days_ci = (
        -float(local_lost_hours["ci95"]["upper"]) / 24.0,
        -float(local_lost_hours["ci95"]["lower"]) / 24.0,
    )

    official_test = model
    sha = _required(metrics, "existing_artifact_reference", "artifact_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise SystemExit("Missing valid production artifact SHA-256 in metrics report")

    return [
        "- Problem: aircraft condition, maintenance, and spares records are fragmented, delaying readiness decisions.",
        "- Solution: an integrated FD001 RUL demo links model evidence to human-approved maintenance and resource workflows.",
        (f"- Measured: FD001 official-test MAE/RMSE {_fmt(_required(official_test, 'mae_cycles'))}/"
         f"{_fmt(_required(official_test, 'rmse_cycles'))} cycles; across {scale['scenario_count']} paired "
         f"synthetic scenarios, Sharing minus local-only was {_fmt_signed(sharing_availability)} pp availability "
         f"(95% paired CI {_fmt_signed(sharing_availability_ci[0])} to {_fmt_signed(sharing_availability_ci[1])}) "
         f"and {_fmt_signed(sharing_lost_days)} censored aircraft-days lost "
         f"(95% paired CI {_fmt_signed(sharing_lost_days_ci[0])} to {_fmt_signed(sharing_lost_days_ci[1])}); "
         f"nearest-FCFS differences were inconclusive."),
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
