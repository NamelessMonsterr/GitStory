"""
Core package — data models, git parsing, pattern detection.
"""

from .models import (
    Commit,
    FileChange,
    Phase,
    PhaseMetrics,
    PhaseType,
    IntentInference,
    Evidence,
    Confidence,
    AnalysisResult,
    RiskLevel,
    RiskAssessment,
)
from .git_parser import GitParser
from .pattern_detector import PatternDetector

__all__ = [
    "Commit",
    "FileChange",
    "Phase",
    "PhaseMetrics",
    "PhaseType",
    "IntentInference",
    "Evidence",
    "Confidence",
    "AnalysisResult",
    "RiskLevel",
    "RiskAssessment",
    "GitParser",
    "PatternDetector",
]
