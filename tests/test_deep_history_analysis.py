"""
Tests for deep_history_analysis — phase detection and metrics computation.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from core.models import Commit, FileChange, PhaseType
from skills.deep_history_analysis import DeepHistoryAnalysis


def _make_commits(
    messages: list[str],
    interval_hours: float = 2.0,
    author: str = "dev",
    files: list[tuple[str, int, int, str]] | None = None,
) -> list[Commit]:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    commits = []
    for i, msg in enumerate(messages):
        fcs = []
        if files:
            for path, a, d, s in files:
                fcs.append(FileChange(path=path, additions=a, deletions=d, status=s))
        commits.append(
            Commit(
                hash=f"hash{i:04d}",
                author=author,
                email=f"{author}@test.com",
                timestamp=base + timedelta(hours=i * interval_hours),
                message=msg,
                file_changes=fcs,
                author_tz_offset_hours=0.0,
            )
        )
    return commits


class TestBasicPhaseDetection:
    def test_single_phase_small_repo(self):
        commits = _make_commits(["add file", "update file", "another change"])
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert len(phases) >= 1
        assert phases[0].metrics.commit_count == 3

    def test_empty_commits(self):
        analysis = DeepHistoryAnalysis(commits=[])
        assert analysis.run() == []

    def test_single_commit(self):
        commits = _make_commits(["initial commit"])
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert len(phases) == 1
        assert phases[0].metrics.commit_count == 1


class TestPhaseTypeAssignment:
    def test_initial_phase_for_small_start(self):
        commits = _make_commits(["init", "setup", "config"])
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert phases[0].phase_type == PhaseType.INITIAL

    def test_hotfix_detection(self):
        """High fix density + high frequency → HOTFIX type."""
        commits = _make_commits(
            ["fix crash", "fix error", "hotfix auth", "fix bug",
             "patch login", "fix", "fix again", "fix test",
             "error fix", "quick patch", "fix more", "bugfix"],
            interval_hours=0.5,
        )
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        # At least one phase should be HOTFIX
        hotfix_phases = [p for p in phases if p.phase_type == PhaseType.HOTFIX]
        assert len(hotfix_phases) >= 1


class TestPhaseMetrics:
    def test_metrics_computed(self):
        commits = _make_commits(
            ["add feature 1", "add feature 2", "add feature 3",
             "add feature 4", "add feature 5", "add feature 6"],
            files=[("src/app.py", 10, 2, "M")],
        )
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        m = phases[0].metrics
        assert m.commit_count == 6
        assert m.total_additions > 0
        assert m.total_deletions > 0
        assert m.total_churn > 0
        assert len(m.files_most_changed) > 0

    def test_new_files_counted(self):
        commits = _make_commits(
            ["create app", "add model"],
            files=[("src/app.py", 30, 0, "A")],
        )
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert phases[0].metrics.new_files_added > 0

    def test_file_status_available_flag(self):
        commits = _make_commits(
            ["update"],
            files=[("a.py", 5, 0, "U")],
        )
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert phases[0].metrics.file_status_available is False


class TestGapDetection:
    def test_gap_creates_multiple_phases(self):
        """A big time gap between commits should create separate phases."""
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        commits = [
            Commit(hash=f"h{i:04d}", author="dev", email="d@t.com",
                   timestamp=base + timedelta(hours=i * 2),
                   message=f"commit {i}", author_tz_offset_hours=0.0)
            for i in range(5)
        ] + [
            Commit(hash=f"h{i:04d}", author="dev", email="d@t.com",
                   timestamp=base + timedelta(days=30, hours=i * 2),
                   message=f"commit {i + 5}", author_tz_offset_hours=0.0)
            for i in range(5)
        ]
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert len(phases) >= 2

    def test_no_gap_stays_single_phase(self):
        commits = _make_commits(
            [f"commit {i}" for i in range(10)],
            interval_hours=1.0,
        )
        analysis = DeepHistoryAnalysis(commits=commits)
        phases = analysis.run()
        assert len(phases) == 1


class TestRepoName:
    def test_default_name(self):
        analysis = DeepHistoryAnalysis(commits=_make_commits(["init"]))
        assert analysis.repo_name == "unknown"

    def test_set_name(self):
        analysis = DeepHistoryAnalysis(commits=_make_commits(["init"]))
        analysis.repo_name = "test-repo"
        assert analysis.repo_name == "test-repo"