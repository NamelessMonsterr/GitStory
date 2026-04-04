"""Robustness tests for perturbation, anti-gaming, and scaling behavior."""

from __future__ import annotations

import math
import statistics
import time

from tests.golden import (
    CONSISTENCY_RUNS,
    MAX_GAMED_CONFIDENCE,
    MAX_PHASE_COUNT_SQRT_FACTOR,
    PERTURBATION_EPSILON,
    PERTURBATION_FLOOR_DELTA,
    SCALING_COMMIT_SIZES,
    analyze_log_text,
    build_high_volume_log,
    to_golden_view,
)


def _build_log(
    messages: list[str],
    diffs: list[tuple[int, int]],
    *,
    path: str = "src/auth.py",
    step_seconds: int = 7200,
) -> str:
    base_ts = 1704067200
    lines: list[str] = []
    for idx, (message, (adds, deletes)) in enumerate(zip(messages, diffs)):
        ts = base_ts + (idx * step_seconds)
        lines.append(f"{idx + 1:040x}|dev|dev@test.com|{ts}|{message}")
        lines.append(f"{adds}\t{deletes}\t{path}")
    return "\n".join(lines)


def _phase_confidence(log_text: str, name: str) -> float:
    view = to_golden_view(analyze_log_text(log_text, name=name))
    return view["phases"][0]["confidence_score"]


def _assert_bounded_perturbation(original: float, perturbed: float) -> None:
    assert perturbed <= original + PERTURBATION_EPSILON
    assert perturbed >= original - PERTURBATION_FLOOR_DELTA


def _median_runtime_ms(commit_count: int) -> tuple[float, dict]:
    log_text = build_high_volume_log(commit_count)

    # Warmup run to reduce one-time interpreter and import noise.
    to_golden_view(analyze_log_text(log_text, name=f"warmup_{commit_count}"))

    times: list[float] = []
    last_view: dict = {}
    for run_idx in range(3):
        start = time.perf_counter()
        last_view = to_golden_view(
            analyze_log_text(log_text, name=f"scale_{commit_count}_{run_idx}")
        )
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), last_view


def test_same_timestamp_analysis_is_deterministic_across_reordering_and_repeats() -> None:
    log_a = (
        "fff|bob|b@test.com|1704067200|build export workflow\n"
        "4\t1\tsrc/export.py\n"
        "aaa|alice|a@test.com|1704067200|add dashboard widget\n"
        "5\t1\tsrc/dashboard.py\n"
        "bbb|alice|a@test.com|1704067200|create account panel\n"
        "6\t1\tsrc/account.py\n"
    )
    log_b = (
        "bbb|alice|a@test.com|1704067200|create account panel\n"
        "6\t1\tsrc/account.py\n"
        "fff|bob|b@test.com|1704067200|build export workflow\n"
        "4\t1\tsrc/export.py\n"
        "aaa|alice|a@test.com|1704067200|add dashboard widget\n"
        "5\t1\tsrc/dashboard.py\n"
    )

    baseline = to_golden_view(analyze_log_text(log_a, name="same_ts_a"))
    assert baseline == to_golden_view(analyze_log_text(log_b, name="same_ts_b"))

    for _ in range(CONSISTENCY_RUNS):
        assert baseline == to_golden_view(analyze_log_text(log_a, name="same_ts_repeat"))


def test_drop_commits_perturbation_does_not_increase_confidence() -> None:
    base_messages = [
        "fix auth crash now",
        "patch broken session path",
        "fix login redirect bug",
        "hotfix api timeout issue",
        "patch auth error guard",
        "fix crash in export",
        "fix broken auth token",
        "patch session error flow",
    ]
    base_diffs = [(2, 4), (2, 5), (1, 4), (1, 4), (2, 5), (2, 4), (2, 5), (1, 4)]

    baseline = _phase_confidence(_build_log(base_messages, base_diffs), "perturb_base")
    reduced = _phase_confidence(
        _build_log(
            [base_messages[i] for i in [0, 1, 2, 4, 5, 7]],
            [base_diffs[i] for i in [0, 1, 2, 4, 5, 7]],
        ),
        "perturb_drop",
    )

    _assert_bounded_perturbation(baseline, reduced)


def test_remove_keywords_perturbation_reduces_confidence() -> None:
    base_messages = [
        "fix auth crash now",
        "patch broken session path",
        "fix login redirect bug",
        "hotfix api timeout issue",
        "patch auth error guard",
        "fix crash in export",
        "fix broken auth token",
        "patch session error flow",
    ]
    no_keyword_messages = [
        "adjust auth path now",
        "update session routing flow",
        "revise login redirect path",
        "update api timeout handling",
        "adjust auth error guard",
        "tune export flow today",
        "revise auth token path",
        "update session error flow",
    ]
    diffs = [(2, 4), (2, 5), (1, 4), (1, 4), (2, 5), (2, 4), (2, 5), (1, 4)]

    baseline = _phase_confidence(_build_log(base_messages, diffs), "perturb_kw_base")
    perturbed = _phase_confidence(
        _build_log(no_keyword_messages, diffs),
        "perturb_kw_removed",
    )

    _assert_bounded_perturbation(baseline, perturbed)
    assert perturbed < baseline


def test_inject_noise_perturbation_does_not_increase_confidence() -> None:
    base_messages = [
        "fix auth crash now",
        "patch broken session path",
        "fix login redirect bug",
        "hotfix api timeout issue",
        "patch auth error guard",
        "fix crash in export",
        "fix broken auth token",
        "patch session error flow",
    ]
    base_diffs = [(2, 4), (2, 5), (1, 4), (1, 4), (2, 5), (2, 4), (2, 5), (1, 4)]

    noisy_messages = base_messages + [
        "update docs wording",
        "sync review notes",
        "adjust readme examples",
    ]
    noisy_diffs = base_diffs + [(1, 1), (1, 1), (1, 1)]

    baseline = _phase_confidence(_build_log(base_messages, base_diffs), "perturb_noise_base")
    noisy = _phase_confidence(_build_log(noisy_messages, noisy_diffs), "perturb_noise")

    _assert_bounded_perturbation(baseline, noisy)


def test_reduce_churn_perturbation_reduces_confidence() -> None:
    feature_messages = [
        "implement auth workflow",
        "add dashboard widget",
        "create export view",
        "support filter presets",
        "build metrics panel",
        "enable account overview",
    ]
    feature_diffs = [(8, 1), (7, 1), (9, 2), (8, 1), (7, 1), (8, 1)]

    baseline = _phase_confidence(
        _build_log(feature_messages, feature_diffs, path="src/feature.py", step_seconds=10800),
        "perturb_churn_base",
    )
    reduced = _phase_confidence(
        _build_log(
            feature_messages,
            [(1, 1)] * len(feature_messages),
            path="src/feature.py",
            step_seconds=10800,
        ),
        "perturb_churn_low",
    )

    _assert_bounded_perturbation(baseline, reduced)
    assert reduced < baseline


def test_repeated_token_spam_cannot_reach_high_confidence() -> None:
    spam_log = "\n".join(
        [
            "spam001|alice|a@test.com|1704067200|fix fix fix fix fix",
            "1\t1\tsrc/a.py",
            "spam002|alice|a@test.com|1704070800|critical bug fix fix fix",
            "1\t1\tsrc/b.py",
            "spam003|alice|a@test.com|1704074400|fix bug patch hotfix error",
            "1\t1\tsrc/c.py",
            "spam004|alice|a@test.com|1704078000|fix fix fix fix fix",
            "1\t1\tsrc/d.py",
            "spam005|alice|a@test.com|1704081600|fix bug patch hotfix error",
            "1\t1\tsrc/e.py",
            "spam006|alice|a@test.com|1704085200|fix fix critical bug fix",
            "1\t1\tsrc/f.py",
        ]
    )

    view = to_golden_view(analyze_log_text(spam_log, name="spam_attack"))
    assert view["phases"][0]["confidence_bucket"] != "high"
    assert view["phases"][0]["confidence_score"] <= MAX_GAMED_CONFIDENCE


def test_mixed_fix_semantics_do_not_collapse_into_bugfix_phase() -> None:
    mixed_log = "\n".join(
        [
            "mix001|alice|a@test.com|1704067200|fix critical bug",
            "1\t0\tREADME.md",
            "mix002|alice|a@test.com|1704153600|docs: fix typo",
            "1\t0\tdocs/guide.md",
            "mix003|alice|a@test.com|1704240000|fix lint",
            "1\t0\tpyproject.toml",
            "mix004|alice|a@test.com|1704326400|fix formatting",
            "1\t0\tsrc/format.py",
            "mix005|alice|a@test.com|1704412800|fix readme wording",
            "1\t0\tREADME.md",
            "mix006|alice|a@test.com|1704499200|fix ci comment",
            "1\t0\t.github/workflows/ci.yml",
        ]
    )

    view = to_golden_view(analyze_log_text(mixed_log, name="mixed_fix"))
    assert view["phase_sequence"][0] in {"mixed", "documentation", "infrastructure"}
    assert view["phase_sequence"][0] != "hotfix_sprint"
    assert view["phases"][0]["dominant_signal"] in {
        None,
        "documentation_push",
        "maintenance_cleanup",
    }
    assert view["phases"][0]["confidence_score"] <= MAX_GAMED_CONFIDENCE


def test_scaling_runtime_and_phase_count_remain_bounded() -> None:
    timings: dict[int, float] = {}

    for commit_count in SCALING_COMMIT_SIZES:
        median_ms, view = _median_runtime_ms(commit_count)
        timings[commit_count] = median_ms
        assert view["phase_count"] <= MAX_PHASE_COUNT_SQRT_FACTOR * math.sqrt(commit_count)

    base = SCALING_COMMIT_SIZES[0]
    for commit_count in SCALING_COMMIT_SIZES[1:]:
        assert timings[commit_count] / timings[base] <= 14.0


def test_change_point_sensitivity_detects_feature_to_bugfix_shift() -> None:
    feature_messages = [f"implement dashboard module {i}" for i in range(12)]
    bugfix_messages = [
        "fix auth crash now",
        "patch auth token bug",
        "hotfix session redirect",
        "fix broken auth flow",
        "patch session panic",
        "fix login crash guard",
        "hotfix auth router bug",
        "fix broken auth state",
        "patch session timeout bug",
        "fix auth crash loop",
        "hotfix login redirect",
        "fix broken session restore",
    ]
    lines: list[str] = []
    base_ts = 1704067200

    for idx, message in enumerate(feature_messages):
        ts = base_ts + (idx * 3600)
        lines.append(f"feat{idx:03d}|dev|dev@test.com|{ts}|{message}")
        lines.append(f"8\t1\tsrc/feature_{idx}.py")

    for idx, message in enumerate(bugfix_messages, start=len(feature_messages)):
        ts = base_ts + (idx * 3600)
        lines.append(f"fix{idx:03d}|dev|dev@test.com|{ts}|{message}")
        lines.append(f"2\t4\tsrc/auth/auth_{idx}.py")

    result = analyze_log_text("\n".join(lines), name="change_point")
    view = to_golden_view(result)
    assert view["phase_sequence"][0] == "feature_development"
    assert any(
        phase_type in {"bug_fixing", "hotfix_sprint"}
        for phase_type in view["phase_sequence"][1:]
    )
    assert view["canonical_phase_count"] >= 2


def test_change_point_sensitivity_detects_feature_to_implicit_bug_shift() -> None:
    feature_messages = [f"implement checkout module {i}" for i in range(10)]
    implicit_bug_messages = [
        "handle null pointer in checkout flow",
        "add retry logic for payment refresh",
        "guard edge case in auth callback",
        "prevent timeout in session refresh",
        "recover missing token in checkout",
        "avoid race in checkout redirect",
    ]
    lines: list[str] = []
    base_ts = 1704067200

    for idx, message in enumerate(feature_messages):
        ts = base_ts + (idx * 3600)
        lines.append(f"ifeat{idx:03d}|dev|dev@test.com|{ts}|{message}")
        lines.append(f"8\t1\tsrc/feature_{idx}.py")

    for idx, message in enumerate(implicit_bug_messages, start=len(feature_messages)):
        ts = base_ts + (idx * 3600)
        lines.append(f"ifix{idx:03d}|dev|dev@test.com|{ts}|{message}")
        lines.append(f"2\t4\tsrc/payment/auth_{idx}.py")

    result = analyze_log_text("\n".join(lines), name="implicit_change_point")
    view = to_golden_view(result)
    assert view["phase_sequence"][0] == "feature_development"
    assert any(
        phase_type in {"bug_fixing", "hotfix_sprint"}
        for phase_type in view["phase_sequence"][1:]
    )
    assert view["canonical_phase_count"] >= 2


def test_phase_persistence_merges_single_commit_micro_phase() -> None:
    lines = [
        "feat001|alice|alice@example.com|1704067200|implement dashboard widget",
        "8\t1\tsrc/dashboard.py",
        "feat002|alice|alice@example.com|1704070800|add reporting chart",
        "8\t1\tsrc/reporting.py",
        "feat003|alice|alice@example.com|1704074400|build export flow",
        "8\t1\tsrc/export.py",
        "docs001|alice|alice@example.com|1704075300|fix docs wording",
        "1\t1\tdocs/guide.md",
        "feat004|alice|alice@example.com|1704076200|support filter presets",
        "8\t1\tsrc/filters.py",
        "feat005|alice|alice@example.com|1704079800|enable saved views",
        "8\t1\tsrc/views.py",
        "feat006|alice|alice@example.com|1704083400|add account summary",
        "8\t1\tsrc/account.py",
    ]
    view = to_golden_view(
        analyze_log_text("\n".join(lines), name="persistence_micro_phase")
    )
    assert view["canonical_phase_count"] == 1
    assert view["phase_sequence"] == ["feature_development"]


def test_confidence_separates_strong_signal_from_mixed_and_noise() -> None:
    strong_bugfix = _phase_confidence(
        _build_log(
            [
                "fix auth crash",
                "patch session bug",
                "fix login loop",
                "hotfix api timeout",
                "patch auth error",
                "fix export crash",
                "fix auth token",
                "patch session error",
            ],
            [(2, 4), (2, 5), (1, 4), (1, 4), (2, 5), (2, 4), (2, 5), (1, 4)],
            step_seconds=900,
        ),
        "confidence_strong",
    )

    real_work_log = "\n".join(
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
    mixed = _phase_confidence(real_work_log, "confidence_real_work")

    low_noise = _phase_confidence(
        _build_log(
            [
                "update notes",
                "sync branch",
                "minor cleanup",
                "revise copy",
                "touch module",
                "adjust wording",
            ],
            [(1, 1)] * 6,
            path="src/misc.py",
            step_seconds=86400,
        ),
        "confidence_noise",
    )

    assert strong_bugfix >= 0.8
    assert 0.45 <= mixed < 0.7
    assert low_noise < 0.4
    assert strong_bugfix > mixed > low_noise
