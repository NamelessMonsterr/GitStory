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
MIN_PHASE_COMMITS = 3
MIN_PHASE_HOURS = 2.0


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
        boundaries = self._detect_boundaries(classifications)
        return self._build_phases(boundaries, classifications)

    def _classify_all(self) -> list[str]:
        return [PatternDetector.classify_commit(c) for c in self.commits]

    def _detect_boundaries(self, classifications: list[str]) -> list[int]:
        boundaries = PatternDetector.detect_gaps(self.commits, multiplier=3.0)
        if len(boundaries) < 2 and len(self.commits) >= 8:
            candidates: list[tuple[float, int]] = []
            max_window = min(8, max(3, len(self.commits) // 4))
            for window in range(3, max_window + 1):
                for i in range(window, len(self.commits) - window):
                    if i in boundaries or any(abs(i - boundary) < window for boundary in boundaries):
                        continue
                    win_a = self.commits[i - window : i]
                    win_b = self.commits[i : i + window]
                    shift = PatternDetector.detect_vocabulary_shift(win_a, win_b)
                    class_shift = self._classification_shift(
                        classifications[i - window : i],
                        classifications[i : i + window],
                    )
                    left_alt = self._alternation_ratio(classifications[i - window : i])
                    right_alt = self._alternation_ratio(classifications[i : i + window])
                    left_pressure = PatternDetector.detect_pressure_signals(win_a)
                    right_pressure = PatternDetector.detect_pressure_signals(win_b)
                    conflict_boundary = max(
                        left_pressure["alternation_score"],
                        right_pressure["alternation_score"],
                    )
                    temporal_boundary = max(
                        left_pressure.get("temporal_urgency", left_pressure["burst_pressure"]),
                        right_pressure.get("temporal_urgency", right_pressure["burst_pressure"]),
                    )
                    left_label, left_strength = self._dominant_class(
                        classifications[i - window : i]
                    )
                    right_label, right_strength = self._dominant_class(
                        classifications[i : i + window]
                    )
                    balance = min(i, len(self.commits) - i) / max(i, len(self.commits) - i)
                    boundary_score = max(
                        shift,
                        class_shift,
                        min(1.0, (conflict_boundary * 0.8) + (temporal_boundary * 0.2)),
                    ) * balance
                    if (
                        left_label != right_label
                        and left_strength >= 0.6
                        and right_strength >= 0.6
                        and (
                            boundary_score > 0.6
                            or abs(left_alt - right_alt) > 0.35
                        )
                    ):
                        candidates.append((boundary_score, i))

            if candidates:
                ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
                best_boundary = ordered[0][1]
                for _, candidate_boundary in ordered:
                    left_type = self._dominant_type(classifications[:candidate_boundary])
                    right_type = self._dominant_type(classifications[candidate_boundary:])
                    if left_type != right_type:
                        best_boundary = candidate_boundary
                        break
                boundaries.append(best_boundary)
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
        segments = self._merge_short_segments(segments)

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
            temporal_urgency = pressure.get(
                "temporal_urgency", pressure["burst_pressure"]
            )
            if (
                (
                    pressure["fix_density"] > 0.6
                    or (
                        pressure["fix_density"] >= 0.45
                        and pressure["alternation_score"] >= 0.8
                    )
                )
                and (
                    pressure["high_frequency"] > 0.3
                    or temporal_urgency > 0.25
                )
                and (
                    pressure["fix_diversity"] >= 0.5
                    or pressure["implicit_fix_density"] >= 0.3
                )
                and pressure["semantic_alignment"] >= 0.6
                and (
                    pressure["fix_coherence"] >= 0.35
                    or pressure["implicit_fix_density"] >= 0.50
                    or pressure["alternation_score"] >= 0.80
                )
                and pressure["impact_weight"] >= 0.75
                and pressure["cleanup_fix_ratio"] <= 0.35
                and (
                    pressure["reactive_ratio"] >= pressure["proactive_ratio"]
                    or (
                        pressure["implicit_fix_density"] >= 0.30
                        and temporal_urgency >= 0.45
                    )
                )
            ):
                phase.phase_type = PhaseType.HOTFIX

        if phases and phases[0].metrics.commit_count <= 5:
            first_pressure = PatternDetector.detect_pressure_signals(phases[0].commits)
            first_temporal_urgency = first_pressure.get(
                "temporal_urgency", first_pressure["burst_pressure"]
            )
            if (
                first_pressure["alternation_score"] < 0.5
                and first_temporal_urgency < 0.25
            ):
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
    def _classification_shift(
        left: list[str], right: list[str]
    ) -> float:
        if not left or not right:
            return 0.0

        left_counter = Counter(left)
        right_counter = Counter(right)
        all_labels = set(left_counter) | set(right_counter)

        distance = 0.0
        for label in all_labels:
            distance += abs(
                (left_counter[label] / len(left))
                - (right_counter[label] / len(right))
            )
        return distance / 2.0

    @staticmethod
    def _dominant_class(classifications: list[str]) -> tuple[str | None, float]:
        if not classifications:
            return None, 0.0

        counter = Counter(classifications)
        label, count = counter.most_common(1)[0]
        return label, count / len(classifications)

    @staticmethod
    def _alternation_ratio(classifications: list[str]) -> float:
        return PatternDetector.conflict_alternation_ratio(classifications)

    def _merge_short_segments(self, segments: list[list[int]]) -> list[list[int]]:
        if len(segments) <= 1:
            return segments

        merged = [list(seg) for seg in segments]
        idx = 0
        while idx < len(merged):
            seg = merged[idx]
            if not seg:
                merged.pop(idx)
                continue
            seg_commits = [self.commits[i] for i in seg]
            duration_hours = (
                (seg_commits[-1].timestamp - seg_commits[0].timestamp).total_seconds()
                / 3600
            )
            if len(seg) >= MIN_PHASE_COMMITS or duration_hours >= MIN_PHASE_HOURS:
                idx += 1
                continue
            if idx == 0 and len(merged) > 1:
                merged[1] = seg + merged[1]
                merged.pop(idx)
                continue
            if idx > 0:
                merged[idx - 1].extend(seg)
                merged.pop(idx)
                continue
            idx += 1
        return merged

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
