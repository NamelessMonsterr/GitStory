"""Helpers for deterministic golden and adversarial output tests."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from core.git_parser import GitParser
from core.models import AnalysisResult, RiskLevel
from core.pattern_detector import PatternDetector
from skills.deep_history_analysis import DeepHistoryAnalysis
from skills.intent_inference import IntentInferenceEngine
from skills.risk_detection import RiskDetectionEngine
from skills.transition_analysis import TransitionAnalysisEngine


_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
FLOAT_EPSILON = 0.05

LOW_CONFIDENCE_RANGE = (0.0, 0.4)
MEDIUM_CONFIDENCE_RANGE = (0.4, 0.7)
HIGH_CONFIDENCE_RANGE = (0.7, 1.01)

DOMINANCE_THRESHOLD = 0.6
DOMINANCE_MARGIN = 0.15
CONSISTENCY_RUNS = 5

MAX_PHASES_SPARSE = 2
MAX_SPIKE_SCORE = 0.30
MAX_PHASE_COUNT_SQRT_FACTOR = 2.0

PERTURBATION_EPSILON = 0.05
PERTURBATION_FLOOR_DELTA = 0.5
MAX_GAMED_CONFIDENCE = 0.7

SCALING_COMMIT_SIZES = (200, 400, 800)
PERFORMANCE_FIXTURE_COMMITS = 1500
SMALL_PERFORMANCE_FIXTURE_COMMITS = 150
MAX_RUNTIME_MS = 20000
MAX_RUNTIME_SCALE_FACTOR = 20.0
PERFORMANCE_COMMIT_SIZES = SCALING_COMMIT_SIZES
PHASE_COUNT_SQRT_FACTOR = 1.0

_SEVERITY_ORDER = {
    RiskLevel.CRITICAL.value: 0,
    RiskLevel.HIGH.value: 1,
    RiskLevel.MEDIUM.value: 2,
    RiskLevel.LOW.value: 3,
    RiskLevel.NONE.value: 4,
}


def load_fixture_text(name: str) -> str:
    return (_FIXTURE_ROOT / "logs" / f"{name}.txt").read_text(encoding="utf-8")


def load_expected_json(name: str) -> dict:
    return json.loads(
        (_FIXTURE_ROOT / "expected" / f"{name}.json").read_text(encoding="utf-8")
    )


def confidence_bucket(score: float) -> str:
    if HIGH_CONFIDENCE_RANGE[0] <= score < HIGH_CONFIDENCE_RANGE[1]:
        return "high"
    if MEDIUM_CONFIDENCE_RANGE[0] <= score < MEDIUM_CONFIDENCE_RANGE[1]:
        return "medium"
    return "low"


def dominant_signal(
    signal_scores: dict[str, float], active_signals: list[str] | None = None
) -> str | None:
    candidates = {
        key: value
        for key, value in signal_scores.items()
        if active_signals is None or key in active_signals
    }
    if not candidates:
        return None

    ordered = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
    leader_name, leader_score = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0

    if leader_score < DOMINANCE_THRESHOLD:
        return None
    if leader_score - runner_up < DOMINANCE_MARGIN:
        return None
    return leader_name


def analyze_log_text(log_text: str, name: str = "fixture") -> AnalysisResult:
    commits = GitParser.from_log_text(log_text)
    analysis = DeepHistoryAnalysis(commits=commits)
    analysis.repo_name = name
    phases = analysis.run()
    inferences = IntentInferenceEngine().run(phases)
    transitions = TransitionAnalysisEngine().run(phases, inferences)
    risks = RiskDetectionEngine().run(phases, inferences)

    if phases:
        start_date = phases[0].start_date
        end_date = phases[-1].end_date
    else:
        start_date = datetime.fromtimestamp(0, tz=timezone.utc)
        end_date = start_date

    return AnalysisResult(
        repo_name=name,
        total_commits=len(commits),
        date_range_start=start_date,
        date_range_end=end_date,
        unique_authors=sorted({commit.author for commit in commits}),
        phases=phases,
        inferences=inferences,
        transitions=transitions,
        risks=risks,
    )


def analyze_fixture(name: str) -> AnalysisResult:
    return analyze_log_text(load_fixture_text(name), name=name)


def split_commit_blocks(log_text: str) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for raw_line in log_text.strip().splitlines():
        line = raw_line.rstrip()
        if "|" in line:
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)

    if current:
        blocks.append(current)

    return ["\n".join(block) for block in blocks]


def build_high_volume_log(commit_count: int = PERFORMANCE_FIXTURE_COMMITS) -> str:
    base_ts = 1704067200
    lines: list[str] = []
    for idx in range(commit_count):
        ts = base_ts + (idx * 900)
        iso_day = 1 + (idx // 96)
        iso_hour = (idx // 4) % 24
        iso_minute = (idx % 4) * 15
        hash_value = f"{idx + 1:040x}"
        lines.append(
            f"{hash_value}|perf|perf@example.com|{ts}|2024-01-{iso_day:02d}T{iso_hour:02d}:{iso_minute:02d}:00+00:00|implement service slice {idx}"
        )
        lines.append(f"8\t2\tsrc/module_{idx % 12}.py")
    return "\n".join(lines)


def max_phase_bound(commit_count: int) -> int:
    return max(1, math.ceil(PHASE_COUNT_SQRT_FACTOR * math.sqrt(commit_count)))


def _merge_signal_scores(
    left: dict[str, float], right: dict[str, float]
) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = max(merged.get(key, 0.0), value)
    return merged


def _canonicalize_phase_entries(raw_phases: list[dict]) -> list[dict]:
    canonical: list[dict] = []
    for phase in raw_phases:
        if canonical and canonical[-1]["type"] == phase["type"]:
            prior = canonical[-1]
            prior["confidence_score"] = max(
                prior["confidence_score"], phase["confidence_score"]
            )
            prior["confidence_bucket"] = confidence_bucket(prior["confidence_score"])
            prior["signal_scores"] = _merge_signal_scores(
                prior["signal_scores"], phase["signal_scores"]
            )
            prior["active_signals"] = sorted(
                set(prior["active_signals"]) | set(phase["active_signals"])
            )
            prior["dominant_signal"] = dominant_signal(
                prior["signal_scores"], prior["active_signals"]
            )
            continue
        canonical.append(phase)
    return canonical


def to_golden_view(result: AnalysisResult) -> dict:
    inference_map = {inference.phase_number: inference for inference in result.inferences}
    phase_type_map = {phase.phase_number: phase.phase_type.value for phase in result.phases}

    raw_phases = []
    for phase in result.phases:
        inference = inference_map[phase.phase_number]
        pressure = PatternDetector.detect_pressure_signals(phase.commits)
        signal_scores = {
            key: round(value, 2) for key, value in inference.signal_scores.items()
        }
        active_signals = sorted({evidence.signal for evidence in inference.evidence})
        raw_phases.append(
            {
                "type": phase.phase_type.value,
                "confidence_score": round(inference.confidence_score, 2),
                "confidence_bucket": confidence_bucket(inference.confidence_score),
                "signal_scores": signal_scores,
                "active_signals": active_signals,
                "dominant_signal": dominant_signal(signal_scores, active_signals),
                "pressure_signals": {
                    "temporal_urgency": round(pressure.get("temporal_urgency", 0.0), 2),
                    "burst_pressure": round(pressure.get("burst_pressure", 0.0), 2),
                    "raw_burst_pressure": round(
                        pressure.get("raw_burst_pressure", pressure.get("burst_pressure", 0.0)),
                        2,
                    ),
                    "alternation_score": round(pressure.get("alternation_score", 0.0), 2),
                    "raw_alternation_score": round(
                        pressure.get("raw_alternation_score", pressure.get("alternation_score", 0.0)),
                        2,
                    ),
                    "impact_weight": round(pressure.get("impact_weight", 0.0), 2),
                    "cleanup_bias": round(pressure.get("cleanup_bias", 0.0), 2),
                    "reactive_ratio": round(pressure.get("reactive_ratio", 0.0), 2),
                    "proactive_ratio": round(pressure.get("proactive_ratio", 0.0), 2),
                },
            }
        )

    phases = _canonicalize_phase_entries(raw_phases)

    transitions = []
    for transition in result.transitions:
        score = round(transition.confidence_score, 2)
        transitions.append(
            {
                "from_type": phase_type_map[transition.from_phase_number],
                "to_type": phase_type_map[transition.to_phase_number],
                "title": transition.title,
                "confidence_bucket": confidence_bucket(score),
                "confidence_score": score,
                "signal_count": len(transition.signals),
            }
        )

    risks = sorted(
        [
            {"title": risk.title, "severity": risk.risk_level.value}
            for risk in result.risks
        ],
        key=lambda item: (_SEVERITY_ORDER[item["severity"]], item["title"]),
    )

    return {
        "phase_count": len(result.phases),
        "canonical_phase_count": len(phases),
        "phase_sequence": [phase["type"] for phase in phases],
        "phases": phases,
        "transitions": transitions,
        "risks": risks,
    }


def assert_close(actual: float, expected: float, epsilon: float = FLOAT_EPSILON) -> None:
    assert abs(actual - expected) <= epsilon


def assert_in_range(
    actual: float, lower: float, upper: float, epsilon: float = FLOAT_EPSILON
) -> None:
    assert actual >= lower - epsilon
    assert actual < upper + epsilon


def compare_golden_view(actual: dict, expected: dict, epsilon: float = FLOAT_EPSILON) -> None:
    if (
        "phase_count" in expected
        and "canonical_phase_count" not in expected
        and "phase_count_max" not in expected
    ):
        assert actual["phase_count"] == expected["phase_count"]
    if "phase_count_max" in expected:
        assert actual["phase_count"] <= expected["phase_count_max"]
    if "phase_count_min" in expected:
        assert actual["phase_count"] >= expected["phase_count_min"]
    if "canonical_phase_count" in expected:
        assert actual["canonical_phase_count"] == expected["canonical_phase_count"]
    if "canonical_phase_count_max" in expected:
        assert actual["canonical_phase_count"] <= expected["canonical_phase_count_max"]
    if "canonical_phase_count_min" in expected:
        assert actual["canonical_phase_count"] >= expected["canonical_phase_count_min"]

    expected_phase_sequence = expected.get(
        "phase_sequence", [phase["type"] for phase in expected["phases"]]
    )
    assert actual["phase_sequence"] == expected_phase_sequence
    assert len(actual["phases"]) == len(expected["phases"])

    for actual_phase, expected_phase in zip(actual["phases"], expected["phases"]):
        assert actual_phase["type"] == expected_phase["type"]
        if "confidence_bucket" in expected_phase:
            assert (
                actual_phase["confidence_bucket"] == expected_phase["confidence_bucket"]
            )

        if "confidence_score" in expected_phase:
            assert_close(
                actual_phase["confidence_score"],
                expected_phase["confidence_score"],
                epsilon=epsilon,
            )
        if "confidence_range" in expected_phase:
            assert_in_range(
                actual_phase["confidence_score"],
                expected_phase["confidence_range"][0],
                expected_phase["confidence_range"][1],
                epsilon=epsilon,
            )
        if "dominant_signal" in expected_phase:
            assert actual_phase["dominant_signal"] == expected_phase["dominant_signal"]
        if "active_signals" in expected_phase:
            assert actual_phase["active_signals"] == expected_phase["active_signals"]

        for key, expected_value in expected_phase.get("signal_scores", {}).items():
            assert key in actual_phase["signal_scores"]
            assert_close(actual_phase["signal_scores"][key], expected_value, epsilon=epsilon)

        for key, bounds in expected_phase.get("signal_expectations", {}).items():
            assert key in actual_phase["signal_scores"]
            actual_value = actual_phase["signal_scores"][key]
            if "min" in bounds:
                assert actual_value >= bounds["min"]
            if "max" in bounds:
                assert actual_value <= bounds["max"]

        for key, bounds in expected_phase.get("pressure_expectations", {}).items():
            assert key in actual_phase["pressure_signals"]
            actual_value = actual_phase["pressure_signals"][key]
            if "min" in bounds:
                assert actual_value >= bounds["min"]
            if "max" in bounds:
                assert actual_value <= bounds["max"]

    assert len(actual["transitions"]) == len(expected["transitions"])
    for actual_transition, expected_transition in zip(
        actual["transitions"], expected["transitions"]
    ):
        assert actual_transition["from_type"] == expected_transition["from_type"]
        assert actual_transition["to_type"] == expected_transition["to_type"]
        if "title" in expected_transition:
            assert actual_transition["title"] == expected_transition["title"]
        if "confidence_bucket" in expected_transition:
            assert (
                actual_transition["confidence_bucket"]
                == expected_transition["confidence_bucket"]
            )
        if "confidence_score" in expected_transition:
            assert_close(
                actual_transition["confidence_score"],
                expected_transition["confidence_score"],
                epsilon=epsilon,
            )
        if "confidence_range" in expected_transition:
            assert_in_range(
                actual_transition["confidence_score"],
                expected_transition["confidence_range"][0],
                expected_transition["confidence_range"][1],
                epsilon=epsilon,
            )
        if "signal_count_min" in expected_transition:
            assert actual_transition["signal_count"] >= expected_transition["signal_count_min"]
        if "signal_count_max" in expected_transition:
            assert actual_transition["signal_count"] <= expected_transition["signal_count_max"]

    if "risks" in expected:
        assert actual["risks"] == expected["risks"]
    expected_contains = expected.get("risk_contains", [])
    actual_risks = {(risk["title"], risk["severity"]) for risk in actual["risks"]}
    for risk in expected_contains:
        assert (risk["title"], risk["severity"]) in actual_risks
    expected_excludes = expected.get("risk_excludes", [])
    for risk in expected_excludes:
        assert (risk["title"], risk["severity"]) not in actual_risks
