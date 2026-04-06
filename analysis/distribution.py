from __future__ import annotations

from collections import Counter
from typing import Iterable

from core.models import Phase, IntentInference, TransitionInsight, RiskAssessment


def _bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def distribution_summary(
    phases: Iterable[Phase],
    inferences: Iterable[IntentInference],
    transitions: Iterable[TransitionInsight],
    risks: Iterable[RiskAssessment],
    urgency_scores: Iterable[float],
) -> dict[str, object]:
    phase_types = Counter(phase.phase_type.value for phase in phases)
    transition_titles = Counter(t.title for t in transitions)
    risk_titles = Counter(r.title for r in risks)
    urgency_buckets = Counter(_bucket(score) for score in urgency_scores)

    return {
        "phase_frequency": dict(phase_types),
        "transition_frequency": dict(transition_titles),
        "risk_frequency": dict(risk_titles),
        "urgency_distribution": dict(urgency_buckets),
        "phase_count": sum(phase_types.values()),
        "transition_count": sum(transition_titles.values()),
        "risk_count": sum(risk_titles.values()),
    }
