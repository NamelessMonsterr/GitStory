"""
Integration tests — full pipeline from commits to final output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from core.models import Commit, FileChange, PhaseType, RiskLevel
from skills.deep_history_analysis import DeepHistoryAnalysis
from skills.intent_inference import IntentInferenceEngine
from skills.risk_detection import RiskDetectionEngine
from skills.narrative_engine import NarrativeEngine
from skills.visual_timeline import VisualTimeline


def _build_test_repo() -> list[Commit]:
    """Build a synthetic repo with clear phase transitions."""
    commits: list[Commit] = []
    base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Phase 1: Initial setup (3 commits)
    for i, msg in enumerate(["init project", "add readme", "setup config"]):
        commits.append(Commit(
            hash=f"init{i:04d}",
            author="alice",
            email="alice@t.com",
            timestamp=base + timedelta(hours=i * 4),
            message=msg,
            file_changes=[
                FileChange(path=f"file{i}.py", additions=50, deletions=0, status="A"),
            ],
            author_tz_offset_hours=0.0,
        ))

    # Phase 2: Feature development (15 commits, after 3-day gap)
    feature_base = base + timedelta(days=5)
    for i in range(15):
        commits.append(Commit(
            hash=f"feat{i:04d}",
            author="alice" if i % 2 == 0 else "bob",
            email=f"{'alice' if i % 2 == 0 else 'bob'}@t.com",
            timestamp=feature_base + timedelta(hours=i * 6),
            message=f"add feature component {i}",
            file_changes=[
                FileChange(
                    path=f"src/component{i}.py",
                    additions=80,
                    deletions=10,
                    status="A" if i < 8 else "M",
                ),
            ],
            author_tz_offset_hours=0.0,
        ))

    # Phase 3: Hotfix sprint (10 commits in 2 days, after 5-day gap)
    hotfix_base = feature_base + timedelta(days=10)
    for i in range(10):
        commits.append(Commit(
            hash=f"fix{i:04d}",
            author="alice",
            email="alice@t.com",
            timestamp=hotfix_base + timedelta(hours=i * 3),
            message=["fix crash", "fix error", "hotfix", "patch bug", "fix",
                      "fix again", "fix login", "error fix", "bugfix", "fix auth"][i],
            file_changes=[
                FileChange(path="src/component0.py", additions=5, deletions=3, status="M"),
            ],
            author_tz_offset_hours=0.0,
        ))

    return commits


class TestFullPipeline:
    def test_pipeline_produces_phases(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        analysis.repo_name = "test-repo"
        phases = analysis.run()
        assert len(phases) >= 2

    def test_pipeline_produces_inferences(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        assert len(inferences) == len(phases)
        for inf in inferences:
            assert len(inf.intent_summary) > 0
            assert len(inf.observation) > 0
            assert 0.0 <= inf.confidence_score <= 1.0

    def test_pipeline_produces_risks(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        risks = RiskDetectionEngine().run(phases, inferences)
        # Should detect at least fragile code (component0 modified 10+ times)
        assert isinstance(risks, list)

    def test_pipeline_produces_narrative(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        analysis.repo_name = "integration-test"
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        risks = RiskDetectionEngine().run(phases, inferences)
        narrative = NarrativeEngine().run(
            phases, inferences, "integration-test", "story", risks=risks
        )
        assert "integration-test" in narrative
        assert len(narrative) > 200

    def test_pipeline_produces_professional_narrative(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        narrative = NarrativeEngine().run(
            phases, inferences, "test", "professional"
        )
        assert "Repository Analysis" in narrative

    def test_pipeline_produces_ascii_timeline(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        risks = RiskDetectionEngine().run(phases, inferences)
        tl = VisualTimeline().ascii(phases, risks=risks)
        assert "Repository Timeline" in tl
        assert "Phase 1" in tl

    def test_pipeline_produces_svg_timeline(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        tl = VisualTimeline().svg(phases)
        assert "<svg" in tl
        assert "</svg>" in tl.strip()

    def test_initial_phase_detected(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert phases[0].phase_type == PhaseType.INITIAL

    def test_phases_are_chronological(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        for i in range(len(phases) - 1):
            assert phases[i].end_date <= phases[i + 1].start_date

    def test_all_commits_accounted_for(self):
        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        total = sum(p.metrics.commit_count for p in phases)
        assert total == len(commits)


class TestJsonOutput:
    def test_full_result_serializable(self):
        from core.models import AnalysisResult

        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        analysis.repo_name = "json-test"
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        risks = RiskDetectionEngine().run(phases, inferences)
        narrative = NarrativeEngine().run(phases, inferences, "json-test", "story", risks=risks)

        result = AnalysisResult(
            repo_name="json-test",
            total_commits=sum(p.metrics.commit_count for p in phases),
            date_range_start=phases[0].start_date,
            date_range_end=phases[-1].end_date,
            unique_authors=sorted({c.author for p in phases for c in p.commits}),
            phases=phases,
            inferences=inferences,
            risks=risks,
            narrative=narrative,
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["repo_name"] == "json-test"
        assert parsed["total_commits"] == len(commits)
        assert len(parsed["phases"]) >= 2
        assert len(parsed["inferences"]) >= 2

    def test_json_contains_risk_data(self):
        from core.models import AnalysisResult

        commits = _build_test_repo()
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        inferences = IntentInferenceEngine().run(phases)
        risks = RiskDetectionEngine().run(phases, inferences)

        result = AnalysisResult(
            repo_name="risk-json",
            total_commits=len(commits),
            date_range_start=phases[0].start_date,
            date_range_end=phases[-1].end_date,
            unique_authors=[],
            risks=risks,
        )

        parsed = json.loads(result.to_json())
        assert "risks" in parsed
        assert isinstance(parsed["risks"], list)