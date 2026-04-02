"""
Tests for intent inference — INITIAL priority, confidence scoring,
unknown file status, reasoning chain completeness.
"""

from __future__ import annotations

from core.models import PhaseType, Confidence
from skills.intent_inference import IntentInferenceEngine


class TestInitialPhasePriority:
    def test_initial_stays_initial(self, make_phase):
        phase = make_phase(
            phase_type=PhaseType.INITIAL,
            commit_count=3,
            messages=["add package.json", "add src/index.ts", "create readme"],
            new_files_added=3,
            total_additions=200,
            total_deletions=0,
        )
        results = IntentInferenceEngine().run([phase])
        summary = results[0].intent_summary.lower()
        assert "initial" in summary or "setup" in summary

    def test_initial_not_called_firefighting(self, make_phase):
        phase = make_phase(
            phase_type=PhaseType.INITIAL,
            commit_count=4,
            messages=["init", "setup", "add config", "fix typo"],
            new_files_added=3,
        )
        summary = IntentInferenceEngine().run([phase])[0].intent_summary.lower()
        assert "damage control" not in summary
        assert "bug fixing" not in summary
        assert "firefight" not in summary

    def test_initial_with_feature_signals_still_initial(self, make_phase):
        """Even with strong feature signals, INITIAL type stays INITIAL."""
        phase = make_phase(
            phase_type=PhaseType.INITIAL,
            commit_count=5,
            messages=["add app", "add model", "add view", "add tests", "create api"],
            new_files_added=10,
            total_additions=800,
            total_deletions=0,
        )
        summary = IntentInferenceEngine().run([phase])[0].intent_summary.lower()
        assert "initial" in summary or "setup" in summary or "origin" in summary


class TestConfidenceScore:
    def test_has_numeric_score(self, make_phase):
        results = IntentInferenceEngine().run([make_phase()])
        assert isinstance(results[0].confidence_score, float)
        assert 0.0 <= results[0].confidence_score <= 1.0

    def test_more_signals_higher_score(self, make_phase):
        weak = make_phase(
            phase_type=PhaseType.MIXED,
            messages=["stuff", "things", "misc"],
            commit_count=3,
            new_files_added=0,
            total_additions=50,
            total_deletions=40,
        )
        strong = make_phase(
            messages=["add feature " + str(i) for i in range(10)],
            new_files_added=8,
            total_additions=1000,
            total_deletions=50,
            unique_authors=3,
        )
        weak_score = IntentInferenceEngine().run([weak])[0].confidence_score
        strong_score = IntentInferenceEngine().run([strong])[0].confidence_score
        assert strong_score > weak_score

    def test_confidence_never_exceeds_one(self, make_phase):
        """Even with many signals, score should cap at 0.95."""
        phase = make_phase(
            messages=["add feature " + str(i) for i in range(20)],
            new_files_added=20,
            total_additions=5000,
            total_deletions=100,
            unique_authors=5,
        )
        score = IntentInferenceEngine().run([phase])[0].confidence_score
        assert score <= 0.95


class TestUnknownFileStatus:
    def test_stdin_mode_mentions_unavailable(self, make_phase):
        phase = make_phase(file_status_available=False, new_files_added=0)
        results = IntentInferenceEngine().run([phase])
        combined = results[0].observation
        for ev in results[0].evidence:
            combined += " " + ev.detail
        assert "unavailable" in combined.lower() or "stdin" in combined.lower()

    def test_stdin_mode_no_false_new_file_count(self, make_phase):
        phase = make_phase(file_status_available=False, new_files_added=0)
        results = IntentInferenceEngine().run([phase])
        combined = results[0].observation
        for ev in results[0].evidence:
            combined += " " + ev.detail
        assert "0 genuinely new files" not in combined


class TestReasoningChain:
    def test_always_present(self, make_phase):
        inf = IntentInferenceEngine().run([make_phase()])[0]
        assert len(inf.observation) > 0
        assert len(inf.pattern) > 0
        assert len(inf.intent_summary) > 0

    def test_observation_contains_metrics(self, make_phase):
        phase = make_phase(total_additions=500, total_deletions=50)
        inf = IntentInferenceEngine().run([phase])[0]
        assert "500" in inf.observation
        assert "50" in inf.observation

    def test_multiple_phases(self, make_phase):
        phases = [
            make_phase(phase_number=1, messages=["add feature " + str(i) for i in range(5)]),
            make_phase(phase_number=2, messages=["fix bug " + str(i) for i in range(5)]),
        ]
        results = IntentInferenceEngine().run(phases)
        assert len(results) == 2
        assert results[0].phase_number == 1
        assert results[1].phase_number == 2


class TestIntentCategories:
    def test_bugfix_phase_detected(self, make_phase):
        phase = make_phase(
            phase_type=PhaseType.BUGFIX,
            messages=["fix crash", "fix error", "patch bug", "hotfix login", "fix"],
            commit_frequency_per_day=6.0,
            avg_message_length_words=2.5,
            total_additions=100,
            total_deletions=80,
        )
        inf = IntentInferenceEngine().run([phase])[0]
        summary_lower = inf.intent_summary.lower()
        assert "damage control" in summary_lower or "bug" in summary_lower or "fix" in summary_lower

    def test_refactor_phase_detected(self, make_phase):
        phase = make_phase(
            phase_type=PhaseType.REFACTOR,
            messages=[
                "refactor auth", "simplify api", "cleanup models",
                "consolidate utils", "extract service",
            ],
            total_additions=200,
            total_deletions=500,
        )
        inf = IntentInferenceEngine().run([phase])[0]
        summary_lower = inf.intent_summary.lower()
        assert "clean" in summary_lower or "refactor" in summary_lower or "debt" in summary_lower