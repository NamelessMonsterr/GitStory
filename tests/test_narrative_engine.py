"""
Tests for narrative_engine — both tones, risk integration, edge cases.
"""

from __future__ import annotations

from core.models import (
    Confidence,
    Evidence,
    IntentInference,
    PhaseType,
    TransitionInsight,
    RiskAssessment,
    RiskLevel,
)
from skills.narrative_engine import NarrativeEngine


class TestStoryTone:
    def test_generates_output(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "test-repo", "story")
        assert len(result) > 100
        assert "test-repo" in result

    def test_contains_chapter_title(self, make_phase, make_inference):
        phase = make_phase(phase_type=PhaseType.FEATURE)
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "repo", "story")
        assert "Building" in result

    def test_contains_big_picture(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "repo", "story")
        assert "Big Picture" in result

    def test_hotfix_chapter_title(self, make_phase, make_inference):
        phase = make_phase(phase_type=PhaseType.HOTFIX)
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "repo", "story")
        assert "Fire Fighting" in result

    def test_multiple_phases(self, make_phase, make_inference):
        phases = [
            make_phase(phase_number=1, phase_type=PhaseType.FEATURE),
            make_phase(phase_number=2, phase_type=PhaseType.BUGFIX),
        ]
        infs = [make_inference(1), make_inference(2)]
        result = NarrativeEngine().run(phases, infs, "repo", "story")
        assert "Chapter 1" in result
        assert "Chapter 2" in result

    def test_confidence_score_shown(self, make_phase):
        phase = make_phase()
        inf = IntentInference(
            phase_number=1,
            intent_summary="test",
            confidence=Confidence.HIGH,
            confidence_score=0.88,
        )
        result = NarrativeEngine().run([phase], [inf], "repo", "story")
        assert "0.88" in result


class TestProfessionalTone:
    def test_generates_output(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "test-repo", "professional")
        assert len(result) > 100
        assert "Repository Analysis" in result

    def test_contains_metrics_table(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "repo", "professional")
        assert "| Metric |" in result

    def test_contains_evidence(self, make_phase):
        phase = make_phase()
        inf = IntentInference(
            phase_number=1,
            intent_summary="test",
            confidence=Confidence.HIGH,
            confidence_score=0.9,
            evidence=[Evidence(signal="test_signal", detail="test detail", commits_involved=5)],
        )
        result = NarrativeEngine().run([phase], [inf], "repo", "professional")
        assert "test_signal" in result
        assert "test detail" in result


class TestRiskIntegration:
    def test_story_shows_inline_risks(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        risk = RiskAssessment(
            risk_id="RSK-001",
            phase_number=1,
            risk_level=RiskLevel.HIGH,
            title="Test Risk",
            signals=["signal 1"],
            inference="test inference",
            impact="test impact",
            commits_involved=5,
        )
        result = NarrativeEngine().run([phase], [inf], "repo", "story", risks=[risk])
        assert "Test Risk" in result

    def test_professional_shows_risk_section(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        risk = RiskAssessment(
            risk_id="RSK-001",
            phase_number=1,
            risk_level=RiskLevel.HIGH,
            title="Test Risk",
            signals=["signal 1"],
            inference="test inference",
            impact="test impact",
            commits_involved=5,
        )
        result = NarrativeEngine().run([phase], [inf], "repo", "professional", risks=[risk])
        assert "Risk Assessment" in result

    def test_cross_phase_risks_shown(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        risk = RiskAssessment(
            risk_id="RSK-002",
            phase_number=0,
            risk_level=RiskLevel.HIGH,
            title="Cross-Phase Risk",
            signals=["cross signal"],
            inference="cross inference",
            impact="cross impact",
            commits_involved=10,
        )
        result = NarrativeEngine().run([phase], [inf], "repo", "story", risks=[risk])
        assert "Cross-Phase" in result

    def test_no_risks(self, make_phase, make_inference):
        phase = make_phase()
        inf = make_inference()
        result = NarrativeEngine().run([phase], [inf], "repo", "story", risks=[])
        assert "Risk" not in result or "Big Picture" in result


class TestTransitionIntegration:
    def test_story_shows_transition_section(self, make_phase, make_inference):
        phases = [
            make_phase(phase_number=1, phase_type=PhaseType.FEATURE),
            make_phase(phase_number=2, phase_type=PhaseType.BUGFIX),
        ]
        inferences = [make_inference(1), make_inference(2)]
        transition = TransitionInsight(
            from_phase_number=1,
            to_phase_number=2,
            title="Feature Burst to Bugfix Spike",
            summary="Feature work gave way to reactive bug fixing.",
            signals=[
                "phase type changed from feature_development to bug_fixing",
                "commit cadence increased",
            ],
            confidence=Confidence.HIGH,
            confidence_score=0.92,
            impact="Likely instability after rollout.",
        )

        result = NarrativeEngine().run(
            phases,
            inferences,
            "repo",
            "story",
            transitions=[transition],
        )

        assert "Between the Chapters" in result
        assert "Feature Burst to Bugfix Spike" in result

    def test_professional_shows_transition_section(self, make_phase, make_inference):
        phases = [
            make_phase(phase_number=1, phase_type=PhaseType.FEATURE),
            make_phase(phase_number=2, phase_type=PhaseType.REFACTOR),
        ]
        inferences = [make_inference(1), make_inference(2)]
        transition = TransitionInsight(
            from_phase_number=1,
            to_phase_number=2,
            title="Feature Push to Refactor Cleanup",
            summary="Rapid expansion gave way to code consolidation.",
            signals=[
                "phase type changed from feature_development to refactoring",
                "deletion ratio increased",
            ],
            confidence=Confidence.MEDIUM,
            confidence_score=0.78,
            impact="Likely cleanup after rapid growth.",
        )

        result = NarrativeEngine().run(
            phases,
            inferences,
            "repo",
            "professional",
            transitions=[transition],
        )

        assert "Transition Analysis" in result
        assert "Feature Push to Refactor Cleanup" in result


class TestEdgeCases:
    def test_empty_phases(self):
        result = NarrativeEngine().run([], [], "empty-repo", "story")
        assert "No phases" in result

    def test_single_phase_opening(self, make_phase, make_inference):
        result = NarrativeEngine().run(
            [make_phase()], [make_inference()], "repo", "story"
        )
        assert "One phase" in result
