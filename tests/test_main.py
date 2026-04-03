"""Regression tests for CLI output safety and debug rendering."""

from __future__ import annotations

import io

from core.models import (
    AnalysisResult,
    Confidence,
    IntentInference,
    RiskAssessment,
    RiskLevel,
    TransitionInsight,
)
from main import _build_debug_report, _safe_for_stream, build_parser


def test_safe_for_stream_preserves_utf8_output() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")

    text = "risk marker \U0001f7e1 stays intact"

    assert _safe_for_stream(text, stream) == text


def test_safe_for_stream_replaces_unencodable_characters() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")

    text = "risk marker \U0001f7e1 \u26a0\ufe0f \u2588 degrades safely"

    assert _safe_for_stream(text, stream) == "risk marker  RISK # degrades safely"


def test_build_parser_accepts_debug_flag() -> None:
    args = build_parser().parse_args(["repo-path", "--debug"])
    assert args.repo_path == "repo-path"
    assert args.debug is True


def test_build_debug_report_shows_evidence_and_transitions(make_phase) -> None:
    phase = make_phase(phase_number=1)
    inference = IntentInference(
        phase_number=1,
        intent_summary="Reactive bug fixing under pressure",
        confidence=Confidence.HIGH,
        confidence_score=0.88,
        evidence=[],
    )
    transition = TransitionInsight(
        from_phase_number=1,
        to_phase_number=2,
        title="Feature Push Gave Way to Firefighting",
        summary="A rollout likely introduced instability.",
        signals=["commit pace accelerated", "messages became terser"],
        confidence=Confidence.HIGH,
        confidence_score=0.85,
        impact="Suggests a quality gap after release.",
    )
    risk = RiskAssessment(
        risk_id="RSK-100",
        phase_number=1,
        risk_level=RiskLevel.HIGH,
        title="Production Instability Detected",
        signals=["fix-related keyword density: 70%"],
        inference="Reactive fixes under pressure.",
        impact="Potential instability in production systems.",
        commits_involved=6,
    )

    result = AnalysisResult(
        repo_name="debug-repo",
        total_commits=phase.metrics.commit_count,
        date_range_start=phase.start_date,
        date_range_end=phase.end_date,
        unique_authors=["dev0"],
        phases=[phase],
        inferences=[inference],
        transitions=[transition],
        risks=[risk],
    )

    debug_text = _build_debug_report(result)

    assert "=== DEBUG: PIPELINE INTELLIGENCE ===" in debug_text
    assert "Reactive bug fixing under pressure" in debug_text
    assert "to phase 2: Feature Push Gave Way to Firefighting" in debug_text
    assert "RSK-100 high: Production Instability Detected" in debug_text
