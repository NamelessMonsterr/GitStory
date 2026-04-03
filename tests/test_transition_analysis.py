"""
Tests for transition_analysis â€” phase-to-phase meaning and interpretation.
"""

from __future__ import annotations

from core.models import PhaseType
from skills.transition_analysis import TransitionAnalysisEngine


class TestTransitionAnalysis:
    def test_single_phase_has_no_transitions(self, make_phase, make_inference):
        phase = make_phase(
            phase_number=1,
            commit_count=4,
            messages=["init project", "add readme", "setup config", "first pass"],
        )
        transitions = TransitionAnalysisEngine().run([phase], [make_inference(1)])
        assert transitions == []

    def test_feature_to_bugfix_transition(self, make_phase, make_inference):
        feature = make_phase(
            phase_number=1,
            phase_type=PhaseType.FEATURE,
            commit_count=8,
            total_additions=900,
            total_deletions=80,
            messages=[f"add feature {i}" for i in range(8)],
            commit_frequency_per_day=6.0,
            unique_authors=2,
        )
        bugfix = make_phase(
            phase_number=2,
            phase_type=PhaseType.BUGFIX,
            commit_count=6,
            total_additions=120,
            total_deletions=90,
            messages=[f"fix issue {i}" for i in range(6)],
            commit_frequency_per_day=8.0,
            unique_authors=1,
        )

        transitions = TransitionAnalysisEngine().run(
            [feature, bugfix],
            [make_inference(1), make_inference(2)],
        )

        assert len(transitions) == 1
        transition = transitions[0]
        text = f"{transition.title} {transition.summary}".lower()
        assert transition.from_phase_number == 1
        assert transition.to_phase_number == 2
        assert transition.signals
        assert "bug" in text or "instability" in text or "rollout" in text
        assert 0.0 <= transition.confidence_score <= 1.0

    def test_feature_to_refactor_transition(self, make_phase, make_inference):
        feature = make_phase(
            phase_number=1,
            phase_type=PhaseType.FEATURE,
            commit_count=7,
            total_additions=750,
            total_deletions=60,
            messages=[f"add module {i}" for i in range(7)],
            commit_frequency_per_day=5.5,
            unique_authors=2,
        )
        refactor = make_phase(
            phase_number=2,
            phase_type=PhaseType.REFACTOR,
            commit_count=5,
            total_additions=200,
            total_deletions=260,
            messages=[f"refactor layout {i}" for i in range(5)],
            commit_frequency_per_day=3.0,
            unique_authors=1,
        )

        transitions = TransitionAnalysisEngine().run(
            [feature, refactor],
            [make_inference(1), make_inference(2)],
        )

        assert len(transitions) == 1
        transition = transitions[0]
        text = f"{transition.title} {transition.summary}".lower()
        assert transition.from_phase_number == 1
        assert transition.to_phase_number == 2
        assert transition.signals
        assert "refactor" in text or "cleanup" in text or "consolidation" in text
        assert 0.0 <= transition.confidence_score <= 1.0
