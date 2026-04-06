from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.evaluator import run_evaluation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run GitStory evaluation harness.")
    parser.add_argument(
        "--dataset",
        default=str(Path("data") / "labeled" / "sample_labeled_data.json"),
        help="Path to labeled dataset JSON.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path for evaluation report.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = run_evaluation(args.dataset)

    payload = {
        "metrics": report.metrics,
        "distribution": report.distribution,
        "raw": report.raw,
        "dataset": {
            "record_count": report.metrics.get("commit_count", 0),
            "repo_count": report.metrics.get("repo_count", 0),
        },
    }
    print(json.dumps(payload, indent=2))
    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
