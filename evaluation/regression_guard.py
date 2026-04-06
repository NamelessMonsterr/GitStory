from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from evaluation.evaluator import run_evaluation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guard against metric regressions.")
    parser.add_argument(
        "--dataset",
        default=str(Path("data") / "labeled" / "sample_labeled_data.json"),
        help="Path to labeled dataset JSON.",
    )
    parser.add_argument(
        "--baseline",
        default=str(Path("config") / "baseline_metrics.json"),
        help="Path to baseline metrics JSON.",
    )
    return parser


def _load_baseline(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Baseline metrics must be a JSON object.")
    return payload


def _compare_metrics(
    current: Mapping[str, float],
    baseline: Mapping[str, float],
    tolerance: Mapping[str, float],
) -> list[str]:
    failures: list[str] = []
    for name, base_value in baseline.items():
        if name not in current:
            continue
        tol = float(tolerance.get(name, 0.0))
        if float(current[name]) < float(base_value) - tol:
            failures.append(
                f"{name} regressed: current={current[name]:.3f} "
                f"baseline={base_value:.3f} tol={tol:.3f}"
            )
    return failures


def _dataset_status(
    record_count: int,
    repo_count: int,
    thresholds: Mapping[str, Any],
) -> tuple[int, list[str]]:
    warn_repos = int(thresholds.get("warn_repos", 0))
    soft_fail_repos = int(thresholds.get("soft_fail_repos", 0))
    unstable_repos = int(thresholds.get("unstable_repos", 0))
    messages: list[str] = []
    status = 0

    if record_count <= 0:
        messages.append("Dataset is empty.")
        return 1, messages

    if warn_repos and repo_count < warn_repos:
        messages.append(
            f"Dataset repo coverage below warning threshold: {repo_count} < {warn_repos}"
        )
    if soft_fail_repos and repo_count < soft_fail_repos:
        messages.append(
            f"Dataset repo coverage below soft-fail threshold: {repo_count} < {soft_fail_repos}"
        )
    if unstable_repos and repo_count < unstable_repos:
        messages.append(
            f"Calibration stability risk: repo_count {repo_count} < {unstable_repos}"
        )
    return status, messages


def main() -> None:
    args = _build_parser().parse_args()
    baseline_payload = _load_baseline(args.baseline)
    report = run_evaluation(args.dataset)

    baseline_metrics = baseline_payload.get("metrics", {})
    tolerance = baseline_payload.get("tolerance", {})
    dataset_thresholds = baseline_payload.get("dataset", {})

    failures = _compare_metrics(report.metrics, baseline_metrics, tolerance)
    status, dataset_messages = _dataset_status(
        record_count=int(report.metrics.get("commit_count", 0)),
        repo_count=int(report.metrics.get("repo_count", 0)),
        thresholds=dataset_thresholds,
    )

    if dataset_messages:
        print("\n".join(dataset_messages))
    if failures:
        print("Regression guard failures:")
        print("\n".join(failures))
        status = 1

    if status:
        sys.exit(status)

    print("Regression guard passed.")


if __name__ == "__main__":
    main()
