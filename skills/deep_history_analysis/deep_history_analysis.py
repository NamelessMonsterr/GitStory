"""
Skill 1: Deep History Analysis

Changes in v1.2:
  - PhaseMetrics.file_status_available populated correctly
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from core.models import Commit, Phase, PhaseMetrics, PhaseType
from core.git_parser import GitParser
from core.pattern_detector import PatternDetector


_CATEGORY_TO_PHASE: dict[str, PhaseType] = {
    "feature": PhaseType.FEATURE,
    "bugfix": PhaseType.BUGFIX,
    "refactor": PhaseType.REFACTOR,
    "infrastructure": PhaseType.INFRASTRUCTURE,
    "documentation": PhaseType.DOCUMENTATION,
}


class DeepHistoryAnalysis:

    def __init__(
        self,
        repo_path: Optional[str] = None,
        commits: Optional[list[Commit]] = None,
        max_commits: Optional[int] = None,
    ):
        if commits is not None:
            self.commits = commits
            self._repo_name = "unknown"
        elif repo_path is not None:
            parser = GitParser(repo_path)
            self.commits = parser.parse(max_commits=max_commits)
            self._repo_name = parser.repo_name
        else:
            raise ValueError("Provide either repo_path or commits")

    @property
    def repo_name(self) -> str:
        return self._repo_name

    @repo_name.setter
    def repo_name(self, value: str) -> None:
        self._repo_name = value

    def run(self) -> list[Phase]:
        if not self.commits:
            return []
        classifications = self._classify_all()
        boundaries = self._detect_boundaries()
        return self._build_phases(boundaries, classifications)

    def _classify_all(self) -> list[str]:
        return [PatternDetector.classify_commit(c) for c in self.commits]

    def _detect_boundaries(self) -> list[int]:
        boundaries = PatternDetector.detect_gaps(self.commits, multiplier=3.0)
        if len(boundaries) < 2 and len(self.commits) > 20:
            window = 10
            for i in range(window, len(self.commits) - window):
                if i in boundaries:
                    continue
                win_a = self.commits[i - window : i]
                win_b = self.commits[i : i + window]
                shift = PatternDetector.detect_vocabulary_shift(win_a, win_b)
                if shift > 0.6:
                    boundaries.append(i)
        return sorted(set(boundaries))

    def _build_phases(
        self, boundaries: list[int], classifications: list[str]
    ) -> list[Phase]:
        segments: list[list[int]] = []
        prev = 0
        for b in boundaries:
            segments.append(list(range(prev, b)))
            prev = b
        segments.append(list(range(prev, len(self.commits))))
        segments = [s for s in segments if s]

        phases: list[Phase] = []
        for idx, seg_indices in enumerate(segments):
            seg_commits = [self.commits[i] for i in seg_indices]
            seg_classes = [classifications[i] for i in seg_indices]
            phase_type = self._dominant_type(seg_classes)

            if idx == 0:
                reason = "Repository start"
            else:
                boundary_idx = seg_indices[0]
                gap_hours = (
                    self.commits[boundary_idx].timestamp
                    - self.commits[boundary_idx - 1].timestamp
                ).total_seconds() / 3600
                if gap_hours > 24:
                    reason = (
                        f"Time gap of {gap_hours:.0f} hours "
                        f"(exceeds threshold) between commits"
                    )
                else:
                    reason = (
                        "Vocabulary/pattern shift detected between "
                        "adjacent commit windows"
                    )

            metrics = self._compute_metrics(seg_commits)

            phases.append(
                Phase(
                    phase_number=idx + 1,
                    phase_type=phase_type,
                    start_date=seg_commits[0].timestamp,
                    end_date=seg_commits[-1].timestamp,
                    commits=seg_commits,
                    metrics=metrics,
                    boundary_reason=reason,
                )
            )

        for phase in phases:
            pressure = PatternDetector.detect_pressure_signals(phase.commits)
            if (
                pressure["fix_density"] > 0.6
                and pressure["high_frequency"] > 0.3
            ):
                phase.phase_type = PhaseType.HOTFIX

        if phases and phases[0].metrics.commit_count <= 5:
            phases[0].phase_type = PhaseType.INITIAL

        return phases

    @staticmethod
    def _dominant_type(classifications: list[str]) -> PhaseType:
        counter = Counter(classifications)
        most_common_cat, most_common_count = counter.most_common(1)[0]
        if most_common_count / len(classifications) < 0.4:
            return PhaseType.MIXED
        return _CATEGORY_TO_PHASE.get(most_common_cat, PhaseType.MIXED)

    @staticmethod
    def _compute_metrics(commits: list[Commit]) -> PhaseMetrics:
        if not commits:
            return PhaseMetrics()

        total_adds = sum(c.total_additions for c in commits)
        total_dels = sum(c.total_deletions for c in commits)
        authors = PatternDetector.unique_authors(commits)
        avg_interval = PatternDetector.avg_commit_interval_hours(commits)
        avg_msg = PatternDetector.avg_message_length(commits)
        top_files = PatternDetector.most_changed_files(commits, top_n=5)
        dom_exts = PatternDetector.dominant_extensions(commits, top_n=3)
        new_files = PatternDetector.count_truly_new_files(commits)
        status_known = PatternDetector.file_status_available(commits)

        span_days = max(
            (commits[-1].timestamp - commits[0].timestamp).total_seconds()
            / 86400,
            0.01,
        )

        return PhaseMetrics(
            commit_count=len(commits),
            total_additions=total_adds,
            total_deletions=total_dels,
            total_churn=total_adds + total_dels,
            unique_authors=len(authors),
            avg_commit_interval_hours=round(avg_interval, 2),
            avg_message_length_words=round(avg_msg, 2),
            files_most_changed=top_files,
            dominant_extensions=dom_exts,
            commit_frequency_per_day=round(len(commits) / span_days, 2),
            new_files_added=new_files,
            file_status_available=status_known,
        )
