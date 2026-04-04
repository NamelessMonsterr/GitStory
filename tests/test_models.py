"""
Tests for core/models.py — data model correctness.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from core.models import (
    AnalysisResult,
    Commit,
    Confidence,
    Evidence,
    FileChange,
    IntentInference,
    Phase,
    PhaseMetrics,
    PhaseType,
    TransitionInsight,
    RiskAssessment,
    RiskLevel,
)


class TestFileChange:
    def test_churn(self):
        fc = FileChange(path="a.py", additions=10, deletions=5)
        assert fc.churn == 15

    def test_is_new_file_status_A(self):
        fc = FileChange(path="a.py", status="A")
        assert fc.is_new_file is True

    def test_is_new_file_status_M(self):
        fc = FileChange(path="a.py", status="M")
        assert fc.is_new_file is False

    def test_is_new_file_status_U(self):
        fc = FileChange(path="a.py", status="U")
        assert fc.is_new_file is False

    def test_is_status_known_M(self):
        fc = FileChange(path="a.py", status="M")
        assert fc.is_status_known is True

    def test_is_status_known_U(self):
        fc = FileChange(path="a.py", status="U")
        assert fc.is_status_known is False

    def test_default_status_is_M(self):
        fc = FileChange(path="a.py")
        assert fc.status == "M"


class TestCommit:
    def test_total_additions(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
            file_changes=[
                FileChange(path="a.py", additions=10, deletions=2),
                FileChange(path="b.py", additions=5, deletions=3),
            ],
        )
        assert c.total_additions == 15
        assert c.total_deletions == 5
        assert c.total_churn == 20
        assert c.files_touched == 2

    def test_message_word_count(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="fix the broken login page",
        )
        assert c.message_word_count == 5

    def test_message_word_count_single(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="fix",
        )
        assert c.message_word_count == 1

    def test_tz_known(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
            author_tz_offset_hours=5.5,
        )
        assert c.tz_known is True

    def test_tz_unknown(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
            author_tz_offset_hours=None,
        )
        assert c.tz_known is False

    def test_empty_file_changes(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
        )
        assert c.total_additions == 0
        assert c.total_deletions == 0
        assert c.files_touched == 0

    def test_source_index_property(self):
        c = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
            _source_index=7,
        )
        assert c.source_index == 7


class TestPhase:
    def test_duration_days(self):
        p = Phase(
            phase_number=1,
            phase_type=PhaseType.FEATURE,
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 11, tzinfo=timezone.utc),
        )
        assert abs(p.duration_days - 10.0) < 0.01

    def test_duration_days_same_day(self):
        p = Phase(
            phase_number=1,
            phase_type=PhaseType.FEATURE,
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert p.duration_days == 0.01  # minimum


class TestPhaseType:
    def test_all_values(self):
        expected = {
            "feature_development",
            "bug_fixing",
            "refactoring",
            "infrastructure",
            "documentation",
            "initial_setup",
            "mixed",
            "hotfix_sprint",
        }
        actual = {pt.value for pt in PhaseType}
        assert actual == expected


class TestRiskLevel:
    def test_all_values(self):
        expected = {"critical", "high", "medium", "low", "none"}
        actual = {rl.value for rl in RiskLevel}
        assert actual == expected


class TestAnalysisResult:
    def test_to_json_serializable(self):
        result = AnalysisResult(
            repo_name="test-repo",
            total_commits=10,
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 3, 1, tzinfo=timezone.utc),
            unique_authors=["alice", "bob"],
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["repo_name"] == "test-repo"
        assert parsed["total_commits"] == 10
        assert len(parsed["unique_authors"]) == 2

    def test_to_dict_handles_enums(self):
        result = AnalysisResult(
            repo_name="test",
            total_commits=1,
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            unique_authors=[],
            risks=[
                RiskAssessment(
                    risk_id="RSK-001",
                    phase_number=1,
                    risk_level=RiskLevel.HIGH,
                    title="Test Risk",
                )
            ],
        )
        d = result.to_dict()
        assert d["risks"][0]["risk_level"] == "high"

    def test_to_json_roundtrip(self):
        result = AnalysisResult(
            repo_name="roundtrip",
            total_commits=5,
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 2, 1, tzinfo=timezone.utc),
            unique_authors=["dev1"],
            inferences=[
                IntentInference(
                    phase_number=1,
                    intent_summary="test",
                    confidence=Confidence.HIGH,
                    confidence_score=0.85,
                    signal_scores={"urgency_pressure": 0.72},
                    evidence=[
                        Evidence(signal="test_signal", detail="detail", commits_involved=3)
                    ],
                )
            ],
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["inferences"][0]["confidence"] == "high"
        assert parsed["inferences"][0]["confidence_score"] == 0.85
        assert parsed["inferences"][0]["signal_scores"]["urgency_pressure"] == 0.72

    def test_to_json_contains_transitions(self):
        result = AnalysisResult(
            repo_name="transition-roundtrip",
            total_commits=8,
            date_range_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            date_range_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            unique_authors=["dev1", "dev2"],
            transitions=[
                TransitionInsight(
                    from_phase_number=1,
                    to_phase_number=2,
                    title="Feature Burst to Bugfix Spike",
                    summary="Feature work gave way to reactive bug fixing.",
                    signals=[
                        "phase type changed from feature to bugfix",
                        "commit frequency increased",
                    ],
                    confidence=Confidence.HIGH,
                    confidence_score=0.91,
                    impact="Likely instability after rollout.",
                )
            ],
        )

        parsed = json.loads(result.to_json())
        assert "transitions" in parsed
        assert parsed["transitions"][0]["from_phase_number"] == 1
        assert parsed["transitions"][0]["to_phase_number"] == 2
        assert parsed["transitions"][0]["confidence"] == "high"

    def test_internal_commit_sort_state_not_serialized(self):
        commit = Commit(
            hash="abc",
            author="dev",
            email="dev@t.com",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            message="test",
            _source_index=9,
        )
        phase = Phase(
            phase_number=1,
            phase_type=PhaseType.FEATURE,
            start_date=commit.timestamp,
            end_date=commit.timestamp,
            commits=[commit],
        )
        result = AnalysisResult(
            repo_name="serialize-commit",
            total_commits=1,
            date_range_start=commit.timestamp,
            date_range_end=commit.timestamp,
            unique_authors=["dev"],
            phases=[phase],
        )

        parsed = json.loads(result.to_json())
        assert "_source_index" not in parsed["phases"][0]["commits"][0]
