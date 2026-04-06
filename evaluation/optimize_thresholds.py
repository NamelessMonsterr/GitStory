from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from analysis.calibration import load_calibrator
from evaluation.evaluator import run_evaluation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize calibration thresholds.")
    parser.add_argument(
        "--dataset",
        default=str(Path("data") / "labeled" / "sample_labeled_data.json"),
        help="Path to labeled dataset JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("config") / "calibrated_thresholds.json"),
        help="Output path for calibrated thresholds.",
    )
    return parser


def _score(metrics: dict[str, Any]) -> float:
    return (
        float(metrics.get("phase_accuracy", 0.0))
        + float(metrics.get("urgency_match_rate", 0.0))
        + float(metrics.get("conflict_f1", 0.0))
    ) / 3.0


def _write_config(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _candidate_values(start: float, end: float, step: float) -> list[float]:
    values = []
    current = start
    while current <= end + 1e-9:
        values.append(round(current, 2))
        current += step
    return values


def main() -> None:
    args = _build_parser().parse_args()
    config_path = Path(args.output)
    base_config = json.loads(config_path.read_text(encoding="utf-8"))

    urgency_candidates = _candidate_values(0.3, 0.8, 0.05)
    conflict_candidates = _candidate_values(0.25, 0.75, 0.05)
    phase_candidates = _candidate_values(0.35, 0.6, 0.05)

    best_score = -1.0
    best_config: dict[str, Any] | None = None

    for medium_min in urgency_candidates:
        for high_min in urgency_candidates:
            if high_min <= medium_min:
                continue
            for conflict_min in conflict_candidates:
                for dominant_min in phase_candidates:
                    candidate = deepcopy(base_config)
                    candidate["urgency"]["medium_min"] = medium_min
                    candidate["urgency"]["high_min"] = high_min
                    candidate["conflict"]["alternation_min"] = conflict_min
                    candidate["phase"]["dominant_ratio_min"] = dominant_min
                    _write_config(config_path, candidate)
                    load_calibrator.cache_clear()
                    report = run_evaluation(args.dataset)
                    score = _score(report.metrics)
                    if score > best_score:
                        best_score = score
                        best_config = candidate

    if best_config is None:
        raise RuntimeError("No viable threshold configuration found.")

    _write_config(config_path, best_config)
    load_calibrator.cache_clear()
    final = run_evaluation(args.dataset)
    print(json.dumps({"score": round(best_score, 3), "metrics": final.metrics}, indent=2))


if __name__ == "__main__":
    main()
