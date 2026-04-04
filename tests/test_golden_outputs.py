"""Golden contract tests for stable inference behavior."""

from __future__ import annotations

import statistics
import time

import pytest

from tests.golden import (
    CONSISTENCY_RUNS,
    MAX_PHASES_SPARSE,
    MAX_RUNTIME_MS,
    MAX_RUNTIME_SCALE_FACTOR,
    MAX_SPIKE_SCORE,
    PERFORMANCE_COMMIT_SIZES,
    PERTURBATION_EPSILON,
    PERTURBATION_FLOOR_DELTA,
    max_phase_bound,
    analyze_fixture,
    analyze_log_text,
    build_high_volume_log,
    compare_golden_view,
    load_expected_json,
    load_fixture_text,
    split_commit_blocks,
    to_golden_view,
)


STRICT_GOLDEN_FIXTURES = [
    "bugfix_spike",
    "growth_cleanup",
    "regression_lock",
]

ADVERSARIAL_GOLDEN_FIXTURES = [
    "noisy_real_world",
    "keyword_poisoning",
    "semantic_ambiguity",
    "cleanup_vs_crisis",
    "silent_critical_work",
    "distributed_cleanup",
    "proactive_resilience",
    "burst_firefight",
    "contradiction_churn",
    "burst_illusion",
    "sparse_history",
]


@pytest.mark.parametrize("name", STRICT_GOLDEN_FIXTURES + ADVERSARIAL_GOLDEN_FIXTURES)
def test_fixture_matches_expected_golden_contract(name: str) -> None:
    actual = to_golden_view(analyze_fixture(name))
    expected = load_expected_json(name)
    compare_golden_view(actual, expected)


def test_empty_fixture_is_safe() -> None:
    actual = to_golden_view(analyze_fixture("empty"))
    assert actual == {
        "phase_count": 0,
        "canonical_phase_count": 0,
        "phase_sequence": [],
        "phases": [],
        "transitions": [],
        "risks": [],
    }


def test_malformed_fixture_recovers_without_crashing() -> None:
    actual = to_golden_view(analyze_fixture("malformed"))

    assert actual["phase_count"] == 1
    assert actual["phase_sequence"] == ["initial_setup"]
    assert actual["phases"][0]["confidence_bucket"] == "medium"
    assert actual["phases"][0]["dominant_signal"] == "feature_push"


def test_ordering_invariance_after_chronological_normalization() -> None:
    ordered = to_golden_view(analyze_fixture("regression_lock"))

    shuffled_log = "\n".join(reversed(split_commit_blocks(load_fixture_text("regression_lock"))))
    shuffled = to_golden_view(analyze_log_text(shuffled_log, name="regression_lock_shuffled"))

    assert shuffled == ordered


def test_same_timestamp_fixture_is_deterministic_across_runs() -> None:
    baseline = to_golden_view(analyze_fixture("same_timestamp_ties"))

    for _ in range(CONSISTENCY_RUNS):
        assert to_golden_view(analyze_fixture("same_timestamp_ties")) == baseline

    shuffled_log = "\n".join(
        reversed(split_commit_blocks(load_fixture_text("same_timestamp_ties")))
    )
    shuffled = to_golden_view(analyze_log_text(shuffled_log, name="same_timestamp_shuffled"))
    assert shuffled == baseline


def test_sparse_history_respects_phase_and_spike_limits() -> None:
    actual = to_golden_view(analyze_fixture("sparse_history"))

    assert actual["phase_count"] <= MAX_PHASES_SPARSE
    assert actual["canonical_phase_count"] <= MAX_PHASES_SPARSE
    assert actual["phases"][0]["signal_scores"]["urgency_pressure"] <= MAX_SPIKE_SCORE


def _median_analysis_runtime_ms(commit_count: int) -> tuple[float, dict]:
    log_text = build_high_volume_log(commit_count)
    warmup = to_golden_view(analyze_log_text(log_text, name=f"perf_warmup_{commit_count}"))
    assert warmup["phase_count"] <= max_phase_bound(commit_count)

    samples: list[float] = []
    last_view = warmup
    for run_index in range(3):
        start = time.perf_counter()
        last_view = to_golden_view(
            analyze_log_text(log_text, name=f"perf_{commit_count}_{run_index}")
        )
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples), last_view


def test_high_volume_scaling_stays_bounded() -> None:
    medians: dict[int, float] = {}
    views: dict[int, dict] = {}

    for commit_count in PERFORMANCE_COMMIT_SIZES:
        median_ms, view = _median_analysis_runtime_ms(commit_count)
        medians[commit_count] = median_ms
        views[commit_count] = view

        assert median_ms <= MAX_RUNTIME_MS
        assert view["phase_sequence"] == ["feature_development"]
        assert view["phases"][0]["dominant_signal"] == "feature_push"
        assert view["phases"][0]["confidence_bucket"] == "medium"
        assert view["phase_count"] <= max_phase_bound(commit_count)
        assert view["canonical_phase_count"] <= max_phase_bound(commit_count)

    base = PERFORMANCE_COMMIT_SIZES[0]
    for commit_count in PERFORMANCE_COMMIT_SIZES[1:]:
        growth_ratio = medians[commit_count] / max(medians[base], 1.0)
        expected_ratio = commit_count / base
        assert growth_ratio <= expected_ratio * MAX_RUNTIME_SCALE_FACTOR


def test_confidence_perturbations_remain_bounded() -> None:
    baseline_log = "\n".join(
        [
            "hot001|alice|alice@example.com|1704758400|2024-01-09T00:00:00+00:00|fix auth crash now",
            "2\t5\tsrc/auth.py",
            "hot002|alice|alice@example.com|1704760200|2024-01-09T00:30:00+00:00|hotfix session bug now",
            "2\t4\tsrc/session.py",
            "hot003|alice|alice@example.com|1704762000|2024-01-09T01:00:00+00:00|patch api timeout now",
            "1\t4\tsrc/api.py",
            "hot004|alice|alice@example.com|1704763800|2024-01-09T01:30:00+00:00|fix broken redirect now",
            "1\t3\tsrc/router.py",
            "hot005|alice|alice@example.com|1704765600|2024-01-09T02:00:00+00:00|crash in auth flow",
            "1\t4\tsrc/auth.py",
            "hot006|alice|alice@example.com|1704767400|2024-01-09T02:30:00+00:00|patch session panic now",
            "1\t3\tsrc/session.py",
        ]
    )
    baseline = to_golden_view(analyze_log_text(baseline_log, name="hotfix_baseline"))
    baseline_confidence = baseline["phases"][0]["confidence_score"]

    dropped_blocks = split_commit_blocks(baseline_log)
    drop_commits = "\n".join(dropped_blocks[:-1])
    drop_view = to_golden_view(analyze_log_text(drop_commits, name="hotfix_drop"))

    remove_keywords_log = baseline_log
    for old, new in [
        ("fix auth crash now", "touch auth path now"),
        ("hotfix session bug now", "tune session path now"),
        ("patch api timeout now", "adjust api timeout now"),
        ("fix broken redirect now", "adjust redirect flow now"),
        ("crash in auth flow", "review auth flow"),
        ("patch session panic now", "review session path now"),
    ]:
        remove_keywords_log = remove_keywords_log.replace(old, new)
    remove_keywords_view = to_golden_view(
        analyze_log_text(remove_keywords_log, name="hotfix_no_keywords")
    )

    noisy_log = baseline_log + "\n" + "\n".join(
        [
            "noise001|bob|bob@example.com|1704769200|2024-01-09T03:00:00+00:00|sync branch notes later",
            "1\t1\tsrc/notes.py",
            "noise002|bob|bob@example.com|1704771000|2024-01-09T03:30:00+00:00|adjust followup state now",
            "1\t1\tsrc/state.py",
        ]
    )
    noise_view = to_golden_view(analyze_log_text(noisy_log, name="hotfix_noise"))

    feature_log = "\n".join(
        [
            "feat001|alice|alice@example.com|1704326400|2024-01-04T00:00:00+00:00|implement dashboard shell",
            "20\t1\tsrc/dashboard.py",
            "feat002|alice|alice@example.com|1704333600|2024-01-04T02:00:00+00:00|add api client",
            "18\t1\tsrc/api.py",
            "feat003|alice|alice@example.com|1704340800|2024-01-04T04:00:00+00:00|build auth flow",
            "16\t1\tsrc/auth.py",
            "feat004|alice|alice@example.com|1704348000|2024-01-04T06:00:00+00:00|create reporting page",
            "14\t1\tsrc/reporting.py",
            "feat005|alice|alice@example.com|1704355200|2024-01-04T08:00:00+00:00|support filters panel",
            "12\t1\tsrc/filters.py",
            "feat006|alice|alice@example.com|1704362400|2024-01-04T10:00:00+00:00|enable account summary",
            "10\t1\tsrc/account.py",
        ]
    )
    feature_baseline = to_golden_view(analyze_log_text(feature_log, name="feature_baseline"))
    feature_zero_churn = to_golden_view(
        analyze_log_text(
            feature_log.replace("20\t1", "0\t0")
            .replace("18\t1", "0\t0")
            .replace("16\t1", "0\t0")
            .replace("14\t1", "0\t0")
            .replace("12\t1", "0\t0")
            .replace("10\t1", "0\t0"),
            name="feature_zero_churn",
        )
    )

    for perturbed in (
        drop_view["phases"][0]["confidence_score"],
        remove_keywords_view["phases"][0]["confidence_score"],
        noise_view["phases"][0]["confidence_score"],
    ):
        assert perturbed <= baseline_confidence + PERTURBATION_EPSILON
        assert perturbed >= baseline_confidence - PERTURBATION_FLOOR_DELTA

    assert remove_keywords_view["phases"][0]["confidence_score"] <= baseline_confidence
    assert feature_zero_churn["phases"][0]["confidence_score"] <= (
        feature_baseline["phases"][0]["confidence_score"] + PERTURBATION_EPSILON
    )
    assert feature_zero_churn["phases"][0]["confidence_score"] >= (
        feature_baseline["phases"][0]["confidence_score"] - PERTURBATION_FLOOR_DELTA
    )


def test_keyword_spam_does_not_exceed_medium_confidence() -> None:
    actual = to_golden_view(analyze_fixture("keyword_spam"))

    assert actual["phases"][0]["confidence_score"] < 0.7
    assert actual["phases"][0]["dominant_signal"] is None
    assert actual["phases"][0]["signal_scores"]["urgency_pressure"] < 0.7
    assert actual["risks"] == []


def test_mixed_fix_semantics_do_not_become_bugfix_firefight() -> None:
    actual = to_golden_view(analyze_fixture("mixed_fix_semantics"))

    assert actual["phase_sequence"][0] != "hotfix_sprint"
    assert actual["phases"][0]["dominant_signal"] in (
        None,
        "documentation_push",
        "maintenance_cleanup",
    )
    assert actual["phases"][0]["confidence_score"] <= 0.75


def test_confidence_separates_strong_mixed_and_noisy_cases() -> None:
    strong_log = "\n".join(
        [
            "strong001|alice|alice@example.com|1704758400|2024-01-09T00:00:00+00:00|fix auth crash",
            "2\t4\tsrc/auth.py",
            "strong002|alice|alice@example.com|1704759300|2024-01-09T00:15:00+00:00|patch session bug",
            "2\t5\tsrc/auth.py",
            "strong003|alice|alice@example.com|1704760200|2024-01-09T00:30:00+00:00|fix login loop",
            "1\t4\tsrc/auth.py",
            "strong004|alice|alice@example.com|1704761100|2024-01-09T00:45:00+00:00|hotfix api timeout",
            "1\t4\tsrc/auth.py",
            "strong005|alice|alice@example.com|1704762000|2024-01-09T01:00:00+00:00|patch auth error",
            "2\t5\tsrc/auth.py",
            "strong006|alice|alice@example.com|1704762900|2024-01-09T01:15:00+00:00|fix export crash",
            "2\t4\tsrc/auth.py",
            "strong007|alice|alice@example.com|1704763800|2024-01-09T01:30:00+00:00|fix auth token",
            "2\t5\tsrc/auth.py",
            "strong008|alice|alice@example.com|1704764700|2024-01-09T01:45:00+00:00|patch session error",
            "1\t4\tsrc/auth.py",
        ]
    )
    mixed_log = "\n".join(
        [
            "real001|alice|alice@example.com|1704067200|add dashboard widget",
            "8\t1\tsrc/dashboard.py",
            "real002|alice|alice@example.com|1704074400|implement auth shell",
            "7\t1\tsrc/auth.py",
            "real003|alice|alice@example.com|1704081600|add session audit trail",
            "8\t1\tsrc/audit.py",
            "real004|alice|alice@example.com|1704088800|build export view",
            "8\t1\tsrc/export.py",
            "real005|alice|alice@example.com|1704096000|support filter presets",
            "8\t1\tsrc/filters.py",
            "real006|alice|alice@example.com|1704103200|enable account summary",
            "8\t1\tsrc/account.py",
        ]
    )
    noisy_log = "\n".join(
        [
            "noise001|alice|alice@example.com|1704877200|2024-01-10T09:00:00+00:00|wip",
            "1\t1\tsrc/a.py",
            "noise002|alice|alice@example.com|1704880800|2024-01-10T10:00:00+00:00|update stuff",
            "1\t1\tsrc/b.py",
            "noise003|alice|alice@example.com|1704884400|2024-01-10T11:00:00+00:00|final",
            "1\t1\tsrc/c.py",
        ]
    )

    strong = to_golden_view(analyze_log_text(strong_log, name="strong_confidence"))
    mixed = to_golden_view(analyze_log_text(mixed_log, name="mixed_confidence"))
    noisy = to_golden_view(analyze_log_text(noisy_log, name="noise_confidence"))

    assert strong["phases"][0]["confidence_score"] >= 0.8
    assert 0.45 <= mixed["phases"][0]["confidence_score"] <= 0.7
    assert noisy["phases"][0]["confidence_score"] < 0.4


def test_cleanup_fix_mix_stays_low_risk_and_low_urgency() -> None:
    cleanup_log = "\n".join(
        [
            "clean001|alice|alice@example.com|1704877200|2024-01-10T09:00:00+00:00|fix pipeline config",
            "1\t1\t.github/workflows/ci.yml",
            "clean002|alice|alice@example.com|1704880800|2024-01-10T10:00:00+00:00|fix lint warnings",
            "1\t1\tpyproject.toml",
            "clean003|alice|alice@example.com|1704884400|2024-01-10T11:00:00+00:00|fix docs wording",
            "1\t1\tdocs/guide.md",
            "clean004|alice|alice@example.com|1704888000|2024-01-10T12:00:00+00:00|fix flaky test naming",
            "1\t1\ttests/test_auth.py",
        ]
    )

    actual = to_golden_view(analyze_log_text(cleanup_log, name="cleanup_not_crisis"))
    first_phase = actual["phases"][0]

    assert actual["phase_sequence"][0] != "hotfix_sprint"
    assert first_phase["signal_scores"]["urgency_pressure"] < 0.35
    assert first_phase["dominant_signal"] in {None, "stabilization", "maintenance_cleanup"}
    assert actual["risks"] == []
