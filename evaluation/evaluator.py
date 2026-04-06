from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from core.models import Commit, FileChange, PhaseType
from core.pattern_detector import PatternDetector
from skills.deep_history_analysis import DeepHistoryAnalysis
from skills.intent_inference import IntentInferenceEngine
from skills.risk_detection import RiskDetectionEngine
from skills.transition_analysis import TransitionAnalysisEngine

from analysis.calibration import percentile_calibrate
from analysis.distribution import distribution_summary


REQUIRED_FIELDS = {"commit_id", "message", "phase", "urgency", "conflict"}
PHASE_LABELS = {"bugfix", "feature", "cleanup", "refactor"}
URGENCY_LABELS = {"low", "medium", "high"}


@dataclass
class EvaluationResult:
    metrics: dict[str, Any]
    distribution: dict[str, Any]
    raw: dict[str, Any]


def load_labeled(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Labeled dataset must be a list of records.")
    for idx, record in enumerate(payload):
        if not isinstance(record, dict):
            raise ValueError(f"Record {idx} is not an object.")
        missing = REQUIRED_FIELDS - set(record.keys())
        if missing:
            raise ValueError(f"Record {idx} missing fields: {sorted(missing)}")
        if record["phase"] not in PHASE_LABELS:
            raise ValueError(f"Record {idx} has invalid phase: {record['phase']}")
        if record["urgency"] not in URGENCY_LABELS:
            raise ValueError(f"Record {idx} has invalid urgency: {record['urgency']}")
        if not isinstance(record["conflict"], bool):
            raise ValueError(f"Record {idx} conflict must be boolean.")
    return payload


def _parse_timestamp(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).astimezone(timezone.utc)
    except ValueError:
        return fallback


def build_commits(records: list[dict[str, Any]]) -> list[Commit]:
    commits: list[Commit] = []
    base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    for idx, record in enumerate(records):
        timestamp = _parse_timestamp(
            record.get("timestamp"),
            base_time + timedelta(hours=idx),
        )
        files = []
        for fc in record.get("files", []) or []:
            files.append(
                FileChange(
                    path=str(fc.get("path", "unknown.txt")),
                    additions=int(fc.get("additions", 0)),
                    deletions=int(fc.get("deletions", 0)),
                    status=str(fc.get("status", "U")),
                )
            )
        commits.append(
            Commit(
                hash=str(record["commit_id"]),
                author=str(record.get("author", "unknown")),
                email=str(record.get("email", "unknown@example.com")),
                timestamp=timestamp,
                message=str(record["message"]),
                file_changes=files,
                author_tz_offset_hours=None,
            )
        )
    return commits


def _phase_label(phase_type: PhaseType) -> str:
    if phase_type in {PhaseType.BUGFIX, PhaseType.HOTFIX}:
        return "bugfix"
    if phase_type == PhaseType.FEATURE:
        return "feature"
    if phase_type == PhaseType.REFACTOR:
        return "refactor"
    return "cleanup"


def _urgency_bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _ordinal_score(label: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[label]


def _rank(values: list[float]) -> list[float]:
    pairs = sorted((v, i) for i, v in enumerate(values))
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(pairs):
        j = idx
        while j < len(pairs) and pairs[j][0] == pairs[idx][0]:
            j += 1
        avg_rank = (idx + j - 1) / 2.0
        for k in range(idx, j):
            ranks[pairs[k][1]] = avg_rank
        idx = j
    return ranks


def spearman_corr(x: list[float], y: list[float]) -> float:
    if len(x) < 2:
        return 0.0
    rx = _rank(x)
    ry = _rank(y)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    num = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    den_x = sum((a - mean_x) ** 2 for a in rx)
    den_y = sum((b - mean_y) ** 2 for b in ry)
    denom = (den_x * den_y) ** 0.5
    return num / denom if denom else 0.0


def evaluate(records: list[dict[str, Any]]) -> EvaluationResult:
    commits = build_commits(records)
    analysis = DeepHistoryAnalysis(commits=commits)
    phases = analysis.run()
    inferences = IntentInferenceEngine().run(phases)
    transitions = TransitionAnalysisEngine().run(phases, inferences)
    risks = RiskDetectionEngine().run(phases, inferences)

    # Map commit -> phase label
    commit_to_phase: dict[str, str] = {}
    commit_to_conflict: dict[str, bool] = {}
    commit_to_urgency: dict[str, float] = {}
    phase_pressures: dict[int, dict[str, float]] = {}

    for phase in phases:
        pressure = PatternDetector.detect_pressure_signals(phase.commits)
        phase_pressures[phase.phase_number] = {
            "raw_urgency": pressure.get("temporal_urgency", pressure["burst_pressure"]),
            "conflict": pressure.get("alternation_score", 0.0) >= 0.4,
        }
        for commit in phase.commits:
            commit_to_phase[commit.hash] = _phase_label(phase.phase_type)
            commit_to_conflict[commit.hash] = phase_pressures[phase.phase_number][
                "conflict"
            ]
            commit_to_urgency[commit.hash] = phase_pressures[phase.phase_number][
                "raw_urgency"
            ]

    raw_scores = [commit_to_urgency[c["commit_id"]] for c in records]
    calibrated_scores = percentile_calibrate(raw_scores)
    for record, calibrated in zip(records, calibrated_scores):
        commit_to_urgency[record["commit_id"]] = calibrated

    # Metrics
    phase_matches = 0
    urgency_matches = 0
    y_true = []
    y_pred = []
    conflict_tp = conflict_fp = conflict_fn = 0

    for record in records:
        commit_id = record["commit_id"]
        predicted_phase = commit_to_phase.get(commit_id, "cleanup")
        if predicted_phase == record["phase"]:
            phase_matches += 1

        predicted_urgency = _urgency_bucket(commit_to_urgency[commit_id])
        if predicted_urgency == record["urgency"]:
            urgency_matches += 1

        y_true.append(_ordinal_score(record["urgency"]))
        y_pred.append(_ordinal_score(predicted_urgency))

        predicted_conflict = commit_to_conflict.get(commit_id, False)
        if predicted_conflict and record["conflict"]:
            conflict_tp += 1
        elif predicted_conflict and not record["conflict"]:
            conflict_fp += 1
        elif (not predicted_conflict) and record["conflict"]:
            conflict_fn += 1

    total = max(len(records), 1)
    conflict_precision = (
        conflict_tp / (conflict_tp + conflict_fp)
        if conflict_tp + conflict_fp
        else 0.0
    )
    conflict_recall = (
        conflict_tp / (conflict_tp + conflict_fn)
        if conflict_tp + conflict_fn
        else 0.0
    )

    metrics = {
        "phase_accuracy": round(phase_matches / total, 3),
        "urgency_match_rate": round(urgency_matches / total, 3),
        "urgency_spearman": round(spearman_corr(y_true, y_pred), 3),
        "conflict_precision": round(conflict_precision, 3),
        "conflict_recall": round(conflict_recall, 3),
        "phase_fragmentation": round(
            len(phases) / max(1.0, len(commits) ** 0.5), 3
        ),
        "phase_count": len(phases),
        "commit_count": len(commits),
    }

    distribution = distribution_summary(
        phases=phases,
        inferences=inferences,
        transitions=transitions,
        risks=risks,
        urgency_scores=calibrated_scores,
    )

    raw = {
        "phases": [p.phase_type.value for p in phases],
        "transitions": [t.title for t in transitions],
        "risks": [r.title for r in risks],
        "raw_urgency": raw_scores,
        "calibrated_urgency": calibrated_scores,
    }

    return EvaluationResult(metrics=metrics, distribution=distribution, raw=raw)


def run_evaluation(path: str | Path) -> EvaluationResult:
    records = load_labeled(path)
    return evaluate(records)
