"""
Core package — data models, git parsing, pattern detection.
"""

from .models import (
    AnalysisResult,
    Commit,
    Confidence,
    Evidence,
    FileChange,
    IntentInference,
    Phase,
    PhaseMetrics,
    PhaseType,
    RiskLevel,
    RiskAssessment,
    TransitionInsight,
)
from .git_parser import GitParser
from .pattern_detector import PatternDetector

__all__ = [
    "AnalysisResult",
    "Commit",
    "Confidence",
    "Evidence",
    "FileChange",
    "IntentInference",
    "Phase",
    "PhaseMetrics",
    "PhaseType",
    "RiskLevel",
    "RiskAssessment",
    "TransitionInsight",
    "GitParser",
    "PatternDetector",
]
