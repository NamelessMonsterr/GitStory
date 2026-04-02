"""
Data models for GitStory.

Changes in v1.2:
  - FileChange.status supports "U" (unknown) for stdin mode
  - PhaseMetrics.file_status_available flag
  - IntentInference.confidence_score (numeric 0.0–1.0)
  - RiskLevel enum + RiskAssessment dataclass
  - AnalysisResult.risks field
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class PhaseType(str, Enum):
    FEATURE = "feature_development"
    BUGFIX = "bug_fixing"
    REFACTOR = "refactoring"
    INFRASTRUCTURE = "infrastructure"
    DOCUMENTATION = "documentation"
    INITIAL = "initial_setup"
    MIXED = "mixed"
    HOTFIX = "hotfix_sprint"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class FileChange:
    """A single file changed in a single commit."""

    path: str
    additions: int = 0
    deletions: int = 0
    status: str = "M"  # A=added, M=modified, D=deleted, R=renamed, U=unknown

    @property
    def churn(self) -> int:
        return self.additions + self.deletions

    @property
    def is_new_file(self) -> bool:
        """True only when git reports the file as newly Added."""
        return self.status == "A"

    @property
    def is_status_known(self) -> bool:
        """False when file came from stdin with no name-status data."""
        return self.status != "U"


@dataclass
class Commit:
    """A single parsed git commit with metadata and file changes."""

    hash: str
    author: str
    email: str
    timestamp: datetime  # always UTC
    message: str
    file_changes: list[FileChange] = field(default_factory=list)
    author_tz_offset_hours: Optional[float] = None

    @property
    def total_additions(self) -> int:
        return sum(fc.additions for fc in self.file_changes)

    @property
    def total_deletions(self) -> int:
        return sum(fc.deletions for fc in self.file_changes)

    @property
    def total_churn(self) -> int:
        return self.total_additions + self.total_deletions

    @property
    def files_touched(self) -> int:
        return len(self.file_changes)

    @property
    def message_word_count(self) -> int:
        return len(self.message.split())

    @property
    def tz_known(self) -> bool:
        return self.author_tz_offset_hours is not None


@dataclass
class PhaseMetrics:
    """Aggregate metrics for a development phase."""

    commit_count: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_churn: int = 0
    unique_authors: int = 0
    avg_commit_interval_hours: float = 0.0
    avg_message_length_words: float = 0.0
    files_most_changed: list[str] = field(default_factory=list)
    dominant_extensions: list[str] = field(default_factory=list)
    commit_frequency_per_day: float = 0.0
    new_files_added: int = 0
    file_status_available: bool = True  # False when all statuses are "U" (stdin)


@dataclass
class Phase:
    """A detected development phase."""

    phase_number: int
    phase_type: PhaseType
    start_date: datetime
    end_date: datetime
    commits: list[Commit] = field(default_factory=list)
    metrics: PhaseMetrics = field(default_factory=PhaseMetrics)
    boundary_reason: str = ""

    @property
    def duration_days(self) -> float:
        delta = self.end_date - self.start_date
        return max(delta.total_seconds() / 86400, 0.01)


@dataclass
class Evidence:
    """A single piece of evidence supporting an inference."""

    signal: str
    detail: str
    commits_involved: int = 0


@dataclass
class IntentInference:
    """The inferred intent for a single phase, with full reasoning chain."""

    phase_number: int
    intent_summary: str
    confidence: Confidence
    confidence_score: float = 0.0  # 0.0–1.0 numeric score
    reasoning: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    observation: str = ""
    pattern: str = ""


@dataclass
class RiskAssessment:
    """A risk finding for a phase or cross-phase pattern."""

    risk_id: str
    phase_number: int  # 0 = cross-phase / repo-wide
    risk_level: RiskLevel
    title: str
    signals: list[str] = field(default_factory=list)
    inference: str = ""
    impact: str = ""
    commits_involved: int = 0


@dataclass
class AnalysisResult:
    """Top-level container for the entire analysis output."""

    repo_name: str
    total_commits: int
    date_range_start: datetime
    date_range_end: datetime
    unique_authors: list[str]
    phases: list[Phase] = field(default_factory=list)
    inferences: list[IntentInference] = field(default_factory=list)
    risks: list[RiskAssessment] = field(default_factory=list)
    narrative: str = ""
    timeline_ascii: str = ""
    timeline_svg: str = ""

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_convert(i) for i in obj]
            if hasattr(obj, "__dataclass_fields__"):
                return {
                    k: _convert(v)
                    for k, v in obj.__dict__.items()
                    if not k.startswith("_")
                }
            return obj

        return _convert(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
