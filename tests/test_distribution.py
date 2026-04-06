from __future__ import annotations

from analysis.distribution import distribution_summary
from evaluation.evaluator import build_commits
from skills.deep_history_analysis import DeepHistoryAnalysis
from skills.intent_inference import IntentInferenceEngine
from skills.risk_detection import RiskDetectionEngine
from skills.transition_analysis import TransitionAnalysisEngine


def test_distribution_summary_basic() -> None:
    records = [
        {
            "commit_id": "d1",
            "message": "add api",
            "phase": "feature",
            "urgency": "medium",
            "conflict": False,
        },
        {
            "commit_id": "d2",
            "message": "fix crash",
            "phase": "bugfix",
            "urgency": "high",
            "conflict": True,
        },
    ]
    commits = build_commits(records)
    analysis = DeepHistoryAnalysis(commits=commits)
    phases = analysis.run()
    inferences = IntentInferenceEngine().run(phases)
    transitions = TransitionAnalysisEngine().run(phases, inferences)
    risks = RiskDetectionEngine().run(phases, inferences)
    summary = distribution_summary(
        phases=phases,
        inferences=inferences,
        transitions=transitions,
        risks=risks,
        urgency_scores=[0.2, 0.8],
    )
    assert "phase_frequency" in summary
    assert summary["phase_count"] == len(phases)
