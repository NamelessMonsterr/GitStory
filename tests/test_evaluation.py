from __future__ import annotations

from evaluation.evaluator import evaluate


def test_evaluation_metrics_shape() -> None:
    records = [
        {
            "commit_id": "a1",
            "message": "add dashboard",
            "phase": "feature",
            "urgency": "medium",
            "conflict": False,
            "timestamp": "2024-01-01T10:00:00Z",
        },
        {
            "commit_id": "a2",
            "message": "fix auth crash",
            "phase": "bugfix",
            "urgency": "high",
            "conflict": True,
            "timestamp": "2024-01-01T11:00:00Z",
        },
        {
            "commit_id": "a3",
            "message": "fix lint warnings",
            "phase": "cleanup",
            "urgency": "low",
            "conflict": False,
            "timestamp": "2024-01-01T12:00:00Z",
        },
    ]

    result = evaluate(records)
    metrics = result.metrics
    assert "phase_accuracy" in metrics
    assert "urgency_match_rate" in metrics
    assert "conflict_precision" in metrics
    assert "conflict_f1" in metrics
    assert 0.0 <= metrics["phase_accuracy"] <= 1.0
    assert 0.0 <= metrics["urgency_match_rate"] <= 1.0
    assert 0.0 <= metrics["conflict_precision"] <= 1.0
    assert 0.0 <= metrics["conflict_f1"] <= 1.0
