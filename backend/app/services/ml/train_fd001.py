"""CLI for reproducible FD001 training and official test evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fd001_model import evaluate_saved_artifact, train_fd001


def main() -> None:
    default_data = Path(__file__).resolve().parents[4] / "CMAPSSData"
    default_artifact = Path(__file__).resolve().parents[4] / "backend" / "models" / "cmapss_fd001_rf_v1.joblib"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--artifact", type=Path, default=default_artifact)
    parser.add_argument("--metrics", type=Path, default=None, help="optional JSON evaluation report path")
    parser.add_argument(
        "--reference-artifact", type=Path, default=None,
        help="optionally score an existing artifact read-only and include its hash/metrics",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-cap", type=int, default=125)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--trees", type=int, default=200)
    args = parser.parse_args()
    metrics = train_fd001(
        args.data_dir, args.artifact, random_seed=args.seed,
        target_cap=args.target_cap, validation_fraction=args.validation_fraction,
        n_estimators=args.trees,
    )
    if args.reference_artifact:
        metrics["existing_artifact_reference"] = evaluate_saved_artifact(
            args.data_dir, args.reference_artifact,
        )
    output = json.dumps(metrics, indent=2, sort_keys=True)
    if args.metrics:
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
