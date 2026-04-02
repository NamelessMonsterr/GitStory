"""
Shared test fixtures and helpers used across all test files.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from core.models import (
    Commit,
    Confidence,
    FileChange,
    IntentInference,
    Phase,
    PhaseMetrics,
    PhaseType,
    RiskLevel,
    RiskAssessment,
)


# ── Commit Factory ───────────────────────────────────────────────

@pytest.fixture
def make_commit():
    """Factory fixture to create Commit objects with sensible defaults."""

    def _make(
        message: str = "commit",
        hours_offset: int = 0,
        files: list[tuple[str, int, int, str]] | None = None,
        author: str = "dev",
        tz_offset_hours: float | None = None,
        base_time: datetime | None = None,
    ) -> Commit:
        if base_time is None:
            base_time = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

        ts = base_time + timedelta(hours=hours_offset)

        file_changes = []
        if files:
            for path, adds, dels, status in files:
                file_changes.append(
                    FileChange(
                        path=path,
                        additions=adds,
                        deletions=dels,
                        status=status,
                    )
                )

        return Commit(
            hash=f"abc{hours_offset:04d}",
            author=author,
            email=f"{author}@test.com",
            timestamp=ts,
            message=message,
            file_changes=file_changes,
            author_tz_offset_hours=tz_offset_hours,
        )

    return _make


# ── Phase Factory ────────────────────────────────────────────────

@pytest.fixture
def make_phase():
    """Factory fixture to create Phase objects with synthetic commits."""

    def _make(
        phase_number: int = 1,
        phase_type: PhaseType = PhaseType.FEATURE,
        commit_count: int = 10,
        messages: list[str] | None = None,
        total_additions: int = 500,
        total_deletions: int = 50,
        new_files_added: int = 5,
        file_status_available: bool = True,
        commit_frequency_per_day: float = 2.0,
        avg_message_length_words: float = 8.0,
        unique_authors: int = 1,
        file_tuples: list[tuple[str, int, int, str]] | None = None,
    ) -> Phase:
        if messages is None:
            messages = [f"commit {i}" for i in range(commit_count)]
        else:
            commit_count = len(messages)

        commits = []
        base = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        for i, msg in enumerate(messages):
            fcs = []
            if file_tuples:
                for path, a, d, s in file_tuples:
                    fcs.append(
                        FileChange(path=path, additions=a, deletions=d, status=s)
                    )
            commits.append(
                Commit(
                    hash=f"h{phase_number:02d}{i:04d}",
                    author=f"dev{i % unique_authors}",
                    email=f"dev{i % unique_authors}@test.com",
                    timestamp=base + timedelta(hours=i * 2),
                    message=msg,
                    file_changes=fcs,
                    author_tz_offset_hours=0.0,
                )
            )

        metrics = PhaseMetrics(
            commit_count=commit_count,
            total_additions=total_additions,
            total_deletions=total_deletions,
            total_churn=total_additions + total_deletions,
            unique_authors=unique_authors,
            avg_commit_interval_hours=2.0,
            avg_message_length_words=avg_message_length_words,
            files_most_changed=["app.py"],
            dominant_extensions=[".py"],
            commit_frequency_per_day=commit_frequency_per_day,
            new_files_added=new_files_added,
            file_status_available=file_status_available,
        )

        return Phase(
            phase_number=phase_number,
            phase_type=phase_type,
            start_date=commits[0].timestamp,
            end_date=commits[-1].timestamp,
            commits=commits,
            metrics=metrics,
            boundary_reason="test boundary",
        )

    return _make


# ── Inference Factory ────────────────────────────────────────────

@pytest.fixture
def make_inference():
    """Factory for IntentInference objects."""

    def _make(
        phase_number: int = 1,
        confidence: Confidence = Confidence.MEDIUM,
        score: float = 0.5,
    ) -> IntentInference:
        return IntentInference(
            phase_number=phase_number,
            intent_summary="test inference",
            confidence=confidence,
            confidence_score=score,
        )

    return _make