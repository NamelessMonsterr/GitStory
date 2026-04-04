"""
Tests for pattern_detector — classification, gaps, pressure, vocabulary, utilities.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from core.models import Commit, FileChange
from core.pattern_detector import (
    MAX_KEYWORD_HITS_PER_CATEGORY,
    PatternDetector,
    _keyword_score,
)


def _make_commit(
    message: str,
    hours_offset: int = 0,
    files: list[tuple[str, int, int, str]] | None = None,
    author: str = "dev",
    tz_offset_hours: float | None = None,
) -> Commit:
    ts = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
        hours=hours_offset
    )
    file_changes = []
    if files:
        for path, adds, dels, status in files:
            file_changes.append(
                FileChange(path=path, additions=adds, deletions=dels, status=status)
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


# ── Classification ───────────────────────────────────────────────

class TestClassifyCommit:
    def test_bugfix_keywords(self):
        assert PatternDetector.classify_commit(
            _make_commit("fix crash on login page")
        ) == "bugfix"

    def test_feature_keywords(self):
        assert PatternDetector.classify_commit(
            _make_commit("add new dashboard widget")
        ) == "feature"

    def test_refactor_keywords(self):
        assert PatternDetector.classify_commit(
            _make_commit("refactor authentication module")
        ) == "refactor"

    def test_infra_keywords(self):
        assert PatternDetector.classify_commit(
            _make_commit("update docker configuration")
        ) == "infrastructure"

    def test_doc_keywords(self):
        assert PatternDetector.classify_commit(
            _make_commit("update readme with examples")
        ) == "documentation"

    def test_fix_pipeline_is_infrastructure(self):
        c = _make_commit(
            "fix pipeline config",
            files=[(".github/workflows/ci.yml", 2, 1, "M")],
        )
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_fix_formatting_is_refactor(self):
        c = _make_commit(
            "fix formatting in dashboard",
            files=[("src/dashboard.py", 3, 2, "M")],
        )
        assert PatternDetector.classify_commit(c) == "refactor"

    def test_fix_readme_bug_is_documentation(self):
        c = _make_commit(
            "fix readme formatting bug",
            files=[("README.md", 4, 1, "M")],
        )
        assert PatternDetector.classify_commit(c) == "documentation"

    def test_handle_null_pointer_is_bugfix_without_fix_keyword(self):
        c = _make_commit(
            "handle null pointer in payment flow",
            files=[("src/payment/checkout.py", 2, 4, "M")],
        )
        assert PatternDetector.classify_commit(c) == "bugfix"

    def test_guard_edge_case_is_bugfix_without_fix_keyword(self):
        c = _make_commit(
            "guard edge case in auth callback",
            files=[("src/auth/callback.py", 1, 3, "M")],
        )
        assert PatternDetector.classify_commit(c) == "bugfix"

    def test_retry_logic_in_checkout_is_bugfix_not_feature(self):
        c = _make_commit(
            "add retry logic for checkout",
            files=[("src/payment/retry.py", 2, 3, "M")],
        )
        assert PatternDetector.classify_commit(c) == "bugfix"

    def test_keyword_score_saturates(self):
        words = {"fix", "bug", "patch", "hotfix", "error"}
        assert _keyword_score(words, frozenset(words)) == MAX_KEYWORD_HITS_PER_CATEGORY

    def test_ambiguous_defaults_to_feature(self):
        assert PatternDetector.classify_commit(
            _make_commit("updated stuff")
        ) == "feature"

    def test_file_path_boosts_infra(self):
        c = _make_commit("update config", files=[("Dockerfile", 5, 2, "M")])
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_file_path_boosts_docs(self):
        c = _make_commit("updated notes", files=[("CHANGELOG.md", 10, 0, "M")])
        assert PatternDetector.classify_commit(c) == "documentation"

    def test_test_files_with_paths_boost_infra(self):
        c = _make_commit(
            "add tests for auth",
            files=[("tests/test_auth.py", 50, 0, "A"), ("tests/test_login.py", 30, 0, "A")],
        )
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_testing_keyword_boosts_infra(self):
        c = _make_commit("testing coverage improvements")
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_add_tests_no_files_is_infrastructure(self):
        """'add tests for auth' with NO file paths must NOT be feature."""
        c = _make_commit("add tests for auth")
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_pure_test_phase_no_files_not_feature(self):
        commits = [_make_commit(f"add tests for module {i}", hours_offset=i) for i in range(6)]
        classifications = [PatternDetector.classify_commit(c) for c in commits]
        assert classifications.count("infrastructure") > classifications.count("feature")

    def test_add_feature_still_feature(self):
        c = _make_commit("add new feature for dashboard")
        assert PatternDetector.classify_commit(c) == "feature"

    def test_add_test_coverage_no_files(self):
        c = _make_commit("add test coverage for utils")
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_multiple_keyword_categories(self):
        """When multiple categories match, highest score wins."""
        c = _make_commit("fix and refactor the auth module")
        result = PatternDetector.classify_commit(c)
        assert result in ("bugfix", "refactor")

    def test_ci_file_path(self):
        c = _make_commit("update workflow", files=[(".github/workflows/ci.yml", 5, 2, "M")])
        assert PatternDetector.classify_commit(c) == "infrastructure"

    def test_empty_message(self):
        c = _make_commit("")
        assert PatternDetector.classify_commit(c) == "feature"  # default


# ── Gap Detection ────────────────────────────────────────────────

class TestDetectGaps:
    def test_no_gaps_uniform(self):
        commits = [_make_commit(f"c{i}", hours_offset=i) for i in range(10)]
        assert PatternDetector.detect_gaps(commits, multiplier=3.0) == []

    def test_detects_large_gap(self):
        commits = [
            _make_commit("c1", hours_offset=0),
            _make_commit("c2", hours_offset=1),
            _make_commit("c3", hours_offset=2),
            _make_commit("c4", hours_offset=200),
            _make_commit("c5", hours_offset=201),
        ]
        assert 3 in PatternDetector.detect_gaps(commits, multiplier=3.0)

    def test_too_few_commits(self):
        commits = [_make_commit("c1"), _make_commit("c2", hours_offset=1)]
        assert PatternDetector.detect_gaps(commits) == []

    def test_multiple_gaps(self):
        commits = [
            _make_commit("c1", hours_offset=0),
            _make_commit("c2", hours_offset=1),
            _make_commit("c3", hours_offset=200),
            _make_commit("c4", hours_offset=201),
            _make_commit("c5", hours_offset=400),
        ]
        gaps = PatternDetector.detect_gaps(commits, multiplier=3.0)
        assert 2 in gaps
        assert 4 in gaps

    def test_single_commit(self):
        assert PatternDetector.detect_gaps([_make_commit("c1")]) == []

    def test_empty_list(self):
        assert PatternDetector.detect_gaps([]) == []


# ── New File Counting ────────────────────────────────────────────

class TestCountTrulyNewFiles:
    def test_counts_only_status_A(self):
        commits = [_make_commit("init", files=[
            ("README.md", 10, 0, "A"),
            ("src/app.py", 50, 0, "A"),
            ("config.yml", 5, 0, "M"),
        ])]
        assert PatternDetector.count_truly_new_files(commits) == 2

    def test_addition_only_edit_not_counted(self):
        commits = [_make_commit("append", files=[("README.md", 20, 0, "M")])]
        assert PatternDetector.count_truly_new_files(commits) == 0

    def test_unknown_status_not_counted(self):
        commits = [_make_commit("add", files=[("new.py", 30, 0, "U")])]
        assert PatternDetector.count_truly_new_files(commits) == 0

    def test_deduplicates(self):
        commits = [
            _make_commit("create", files=[("app.py", 30, 0, "A")]),
            _make_commit("edit", files=[("app.py", 5, 2, "M")], hours_offset=1),
        ]
        assert PatternDetector.count_truly_new_files(commits) == 1

    def test_empty_commits(self):
        assert PatternDetector.count_truly_new_files([]) == 0

    def test_no_file_changes(self):
        commits = [_make_commit("empty commit")]
        assert PatternDetector.count_truly_new_files(commits) == 0


# ── File Status Available ────────────────────────────────────────

class TestFileStatusAvailable:
    def test_known(self):
        commits = [_make_commit("c1", files=[("a.py", 1, 0, "A")])]
        assert PatternDetector.file_status_available(commits) is True

    def test_unknown(self):
        commits = [_make_commit("c1", files=[("a.py", 1, 0, "U")])]
        assert PatternDetector.file_status_available(commits) is False

    def test_mixed(self):
        commits = [_make_commit("c1", files=[("a.py", 1, 0, "U"), ("b.py", 1, 0, "A")])]
        assert PatternDetector.file_status_available(commits) is True

    def test_empty(self):
        assert PatternDetector.file_status_available([]) is False

    def test_no_files(self):
        commits = [_make_commit("no files")]
        assert PatternDetector.file_status_available(commits) is False


# ── Pressure Signals ─────────────────────────────────────────────

class TestPressureSignals:
    def test_late_night_not_fabricated_without_tz(self):
        commits = [_make_commit("fix", hours_offset=i, tz_offset_hours=None) for i in range(5)]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["late_night_ratio"] == 0.0
        assert result["late_night_available"] is False

    def test_late_night_uses_local_time(self):
        commits = [_make_commit("work", hours_offset=0, tz_offset_hours=5.5)]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["late_night_ratio"] == 0.0

    def test_actual_late_night_23h(self):
        c = _make_commit("urgent fix", hours_offset=0, tz_offset_hours=0.0)
        c.timestamp = datetime(2024, 3, 1, 23, 0, 0, tzinfo=timezone.utc)
        result = PatternDetector.detect_pressure_signals([c])
        assert result["late_night_ratio"] == 1.0

    def test_midnight_is_late_night(self):
        """Hour 0 (midnight) MUST be counted as late-night."""
        c = _make_commit("emergency fix", hours_offset=0, tz_offset_hours=0.0)
        c.timestamp = datetime(2024, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
        result = PatternDetector.detect_pressure_signals([c])
        assert result["late_night_ratio"] == 1.0

    def test_midnight_plus_5am_both_late(self):
        c0 = _make_commit("fix 1", hours_offset=0, tz_offset_hours=0.0)
        c0.timestamp = datetime(2024, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
        c5 = _make_commit("fix 2", hours_offset=1, tz_offset_hours=0.0)
        c5.timestamp = datetime(2024, 3, 2, 5, 0, 0, tzinfo=timezone.utc)
        result = PatternDetector.detect_pressure_signals([c0, c5])
        assert result["late_night_ratio"] == 1.0

    def test_6am_not_late_night(self):
        c = _make_commit("morning", hours_offset=0, tz_offset_hours=0.0)
        c.timestamp = datetime(2024, 3, 2, 6, 0, 0, tzinfo=timezone.utc)
        result = PatternDetector.detect_pressure_signals([c])
        assert result["late_night_ratio"] == 0.0

    def test_10pm_is_late_night(self):
        c = _make_commit("late work", hours_offset=0, tz_offset_hours=0.0)
        c.timestamp = datetime(2024, 3, 2, 22, 0, 0, tzinfo=timezone.utc)
        result = PatternDetector.detect_pressure_signals([c])
        assert result["late_night_ratio"] == 1.0

    def test_short_message_detection(self):
        commits = [_make_commit("fix"), _make_commit("wip"), _make_commit("longer msg here")]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["short_messages"] > 0.6

    def test_fix_density(self):
        commits = [
            _make_commit("fix login bug"),
            _make_commit("fix crash"),
            _make_commit("add new feature"),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["fix_density"] > 0.6

    def test_fix_diversity_penalizes_repeated_single_token(self):
        commits = [
            _make_commit("fix fix fix"),
            _make_commit("fix fix fix", hours_offset=1),
            _make_commit("fix fix fix", hours_offset=2),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["fix_density"] >= 0.7
        assert result["fix_diversity"] < 0.3
        assert result["fix_pressure"] < result["fix_density"]

    def test_fix_diversity_stays_high_for_richer_bugfix_language(self):
        commits = [
            _make_commit("fix login bug"),
            _make_commit("patch crash regression", hours_offset=1),
            _make_commit("hotfix broken auth flow", hours_offset=2),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["fix_density"] == 1.0
        assert result["fix_diversity"] >= 0.75
        assert result["fix_pressure"] >= 0.5

    def test_cleanup_fix_commits_have_low_semantic_alignment(self):
        commits = [
            _make_commit(
                "fix pipeline config",
                files=[(".github/workflows/ci.yml", 1, 1, "M")],
            ),
            _make_commit(
                "fix formatting",
                hours_offset=1,
                files=[("src/dashboard.py", 1, 1, "M")],
            ),
            _make_commit(
                "fix docs wording",
                hours_offset=2,
                files=[("docs/guide.md", 1, 1, "M")],
            ),
            _make_commit(
                "fix flaky test",
                hours_offset=3,
                files=[("tests/test_auth.py", 1, 1, "M")],
            ),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["semantic_alignment"] < 0.3
        assert result["cleanup_bias"] > 0.7
        assert result["fix_pressure"] < 0.2

    def test_clustered_product_bugfixes_have_coherence(self):
        commits = [
            _make_commit(
                "fix auth crash",
                files=[("src/auth/login.py", 2, 4, "M")],
            ),
            _make_commit(
                "patch broken auth token",
                hours_offset=1,
                files=[("src/auth/token.py", 2, 3, "M")],
            ),
            _make_commit(
                "hotfix auth redirect bug",
                hours_offset=2,
                files=[("src/auth/router.py", 1, 4, "M")],
            ),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["semantic_alignment"] == 1.0
        assert result["fix_coherence"] >= 0.66
        assert result["fix_pressure"] >= 0.8

    def test_implicit_bug_signals_raise_pressure_for_silent_critical_work(self):
        commits = [
            _make_commit(
                "handle null pointer in payment flow",
                hours_offset=0,
                files=[("src/payment/checkout.py", 1, 4, "M")],
            ),
            _make_commit(
                "add retry logic for checkout",
                hours_offset=1,
                files=[("src/payment/retry.py", 2, 3, "M")],
            ),
            _make_commit(
                "guard edge case in auth callback",
                hours_offset=2,
                files=[("src/auth/callback.py", 1, 3, "M")],
            ),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["implicit_fix_density"] >= 0.6
        assert result["impact_weight"] >= 0.8
        assert result["cleanup_bias"] <= 0.2

    def test_distributed_cleanup_keeps_low_impact_and_low_pressure(self):
        commits = [
            _make_commit("fix lint in api", hours_offset=0, files=[("src/api.py", 1, 1, "M")]),
            _make_commit("fix formatting in ui", hours_offset=1, files=[("src/ui.py", 1, 1, "M")]),
            _make_commit("fix style in db", hours_offset=2, files=[("src/db.py", 1, 1, "M")]),
            _make_commit("fix lint in cache", hours_offset=3, files=[("src/cache.py", 1, 1, "M")]),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["impact_weight"] <= 0.3
        assert result["cleanup_bias"] >= 0.7
        assert result["fix_pressure"] <= 0.15

    def test_proactive_resilience_prefers_proactive_over_reactive_pressure(self):
        commits = [
            _make_commit(
                "add retry logic for payment refresh",
                hours_offset=0,
                files=[("src/payment/retry.py", 3, 1, "M")],
            ),
            _make_commit(
                "improve error handling in checkout",
                hours_offset=2,
                files=[("src/payment/checkout.py", 3, 1, "M")],
            ),
            _make_commit(
                "add fallback for auth failures",
                hours_offset=4,
                files=[("src/auth/fallback.py", 3, 1, "M")],
            ),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["proactive_ratio"] > result["reactive_ratio"]
        assert result["proactive_pressure"] > result["reactive_pressure"]
        assert result["burst_pressure"] < 0.35

    def test_burst_pressure_detects_compressed_firefight(self):
        compressed = [
            _make_commit("fix auth crash now", hours_offset=0, files=[("src/auth.py", 1, 4, "M")]),
            _make_commit("patch session failure now", hours_offset=0, files=[("src/session.py", 1, 4, "M")]),
            _make_commit("hotfix broken checkout redirect", hours_offset=0, files=[("src/checkout.py", 1, 4, "M")]),
            _make_commit("fix payment crash now", hours_offset=1, files=[("src/payment.py", 1, 4, "M")]),
        ]
        spaced = [
            _make_commit("fix auth crash now", hours_offset=0, files=[("src/auth.py", 1, 4, "M")]),
            _make_commit("patch session failure now", hours_offset=12, files=[("src/session.py", 1, 4, "M")]),
            _make_commit("hotfix broken checkout redirect", hours_offset=24, files=[("src/checkout.py", 1, 4, "M")]),
            _make_commit("fix payment crash now", hours_offset=36, files=[("src/payment.py", 1, 4, "M")]),
        ]
        compressed_result = PatternDetector.detect_pressure_signals(compressed)
        spaced_result = PatternDetector.detect_pressure_signals(spaced)
        assert compressed_result["burst_pressure"] > spaced_result["burst_pressure"]
        assert compressed_result["reactive_pressure"] > spaced_result["reactive_pressure"]

    def test_alternation_score_rises_for_switching_intents(self):
        commits = [
            _make_commit("add dashboard widget", hours_offset=0, files=[("src/dashboard.py", 4, 1, "M")]),
            _make_commit("fix dashboard crash", hours_offset=1, files=[("src/dashboard.py", 1, 4, "M")]),
            _make_commit("add audit export", hours_offset=2, files=[("src/export.py", 4, 1, "M")]),
            _make_commit("handle null pointer in export flow", hours_offset=3, files=[("src/export.py", 1, 4, "M")]),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["alternation_score"] >= 0.6

    def test_conflict_alternation_ignores_maintenance_only_switches(self):
        commits = [
            _make_commit("fix docs wording", hours_offset=0, files=[("docs/guide.md", 1, 1, "M")]),
            _make_commit("fix lint warnings", hours_offset=1, files=[("src/api.py", 1, 1, "M")]),
            _make_commit("update ci config", hours_offset=2, files=[(".github/workflows/ci.yml", 1, 1, "M")]),
            _make_commit("fix readme format", hours_offset=3, files=[("README.md", 1, 1, "M")]),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["raw_alternation_score"] >= 0.75
        assert result["alternation_score"] < 0.4

    def test_conflict_alternation_weights_feature_bug_above_feature_cleanup(self):
        feature_bug = [
            _make_commit("add dashboard widget", hours_offset=0, files=[("src/dashboard.py", 4, 1, "M")]),
            _make_commit("fix dashboard crash", hours_offset=1, files=[("src/dashboard.py", 1, 4, "M")]),
            _make_commit("add export page", hours_offset=2, files=[("src/export.py", 4, 1, "M")]),
            _make_commit("patch export timeout", hours_offset=3, files=[("src/export.py", 1, 4, "M")]),
        ]
        feature_cleanup = [
            _make_commit("add dashboard widget", hours_offset=0, files=[("src/dashboard.py", 4, 1, "M")]),
            _make_commit("fix docs wording", hours_offset=1, files=[("docs/guide.md", 1, 1, "M")]),
            _make_commit("add export page", hours_offset=2, files=[("src/export.py", 4, 1, "M")]),
            _make_commit("fix lint warnings", hours_offset=3, files=[("src/export.py", 1, 1, "M")]),
        ]
        feature_bug_result = PatternDetector.detect_pressure_signals(feature_bug)
        feature_cleanup_result = PatternDetector.detect_pressure_signals(feature_cleanup)
        assert feature_bug_result["alternation_score"] > feature_cleanup_result["alternation_score"]

    def test_temporal_noise_filter_dampens_cleanup_bursts(self):
        commits = [
            _make_commit("fix docs typo", hours_offset=0, files=[("docs/guide.md", 1, 1, "M")]),
            _make_commit("fix lint warnings", hours_offset=0, files=[("src/api.py", 1, 1, "M")]),
            _make_commit("fix formatting", hours_offset=0, files=[("src/ui.py", 1, 1, "M")]),
            _make_commit("fix ci config", hours_offset=1, files=[(".github/workflows/ci.yml", 1, 1, "M")]),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["raw_burst_pressure"] > 0.4
        assert result["burst_pressure"] < 0.2
        assert result["temporal_urgency"] == 0.0

    def test_scattered_product_bugfixes_do_not_look_like_crisis(self):
        commits = [
            _make_commit("fix api timeout", files=[("src/api.py", 2, 3, "M")]),
            _make_commit("fix ui overflow", hours_offset=1, files=[("src/ui.py", 2, 3, "M")]),
            _make_commit("fix cache invalidation", hours_offset=2, files=[("src/cache.py", 2, 3, "M")]),
            _make_commit("fix db cursor", hours_offset=3, files=[("src/db.py", 2, 3, "M")]),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["semantic_alignment"] == 1.0
        assert result["fix_coherence"] < 0.5
        assert result["fix_pressure"] < 0.4

    def test_no_file_bugfixes_default_to_full_coherence(self):
        commits = [
            _make_commit("fix login bug"),
            _make_commit("patch crash regression", hours_offset=1),
            _make_commit("hotfix broken auth flow", hours_offset=2),
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["fix_coherence"] >= 0.55

    def test_empty(self):
        result = PatternDetector.detect_pressure_signals([])
        assert result["short_messages"] == 0.0
        assert result["late_night_available"] is False
        assert result["fix_diversity"] == 0.0
        assert result["fix_pressure"] == 0.0
        assert result["semantic_alignment"] == 0.0
        assert result["fix_coherence"] == 0.0

    def test_all_long_messages_low_pressure(self):
        commits = [
            _make_commit(f"implement comprehensive feature number {i} with full test coverage")
            for i in range(5)
        ]
        result = PatternDetector.detect_pressure_signals(commits)
        assert result["short_messages"] == 0.0

    def test_mixed_tz_commits(self):
        """Some commits have tz, some don't — only tz-known used for late-night."""
        c1 = _make_commit("fix 1", hours_offset=0, tz_offset_hours=0.0)
        c1.timestamp = datetime(2024, 3, 1, 23, 0, 0, tzinfo=timezone.utc)
        c2 = _make_commit("fix 2", hours_offset=1, tz_offset_hours=None)
        result = PatternDetector.detect_pressure_signals([c1, c2])
        assert result["late_night_available"] is True
        assert result["late_night_ratio"] == 1.0  # 1 out of 1 tz-known


# ── Vocabulary Shift ─────────────────────────────────────────────

class TestVocabularyShift:
    def test_identical(self):
        w = [_make_commit("add feature login") for _ in range(5)]
        assert PatternDetector.detect_vocabulary_shift(w, w) == 0.0

    def test_completely_different(self):
        a = [_make_commit("add feature login") for _ in range(5)]
        b = [_make_commit("fix crash error bug") for _ in range(5)]
        assert PatternDetector.detect_vocabulary_shift(a, b) > 0.5

    def test_partially_overlapping(self):
        a = [_make_commit("add feature") for _ in range(5)]
        b = [_make_commit("add bugfix") for _ in range(5)]
        shift = PatternDetector.detect_vocabulary_shift(a, b)
        assert 0.0 < shift < 1.0

    def test_empty_windows(self):
        assert PatternDetector.detect_vocabulary_shift([], []) == 0.0


# ── Utilities ────────────────────────────────────────────────────

class TestUtilities:
    def test_unique_authors_preserves_order(self):
        commits = [
            _make_commit("c1", author="alice"),
            _make_commit("c2", author="bob", hours_offset=1),
            _make_commit("c3", author="alice", hours_offset=2),
        ]
        assert PatternDetector.unique_authors(commits) == ["alice", "bob"]

    def test_unique_authors_empty(self):
        assert PatternDetector.unique_authors([]) == []

    def test_most_changed_files(self):
        commits = [
            _make_commit("c1", files=[("a.py", 1, 0, "M"), ("b.py", 1, 0, "M")]),
            _make_commit("c2", files=[("a.py", 1, 0, "M")], hours_offset=1),
        ]
        assert PatternDetector.most_changed_files(commits, top_n=1) == ["a.py"]

    def test_most_changed_files_empty(self):
        assert PatternDetector.most_changed_files([], top_n=3) == []

    def test_dominant_extensions(self):
        commits = [_make_commit("c1", files=[
            ("a.py", 1, 0, "M"), ("b.py", 1, 0, "M"), ("c.js", 1, 0, "M"),
        ])]
        assert PatternDetector.dominant_extensions(commits, top_n=1) == [".py"]

    def test_dominant_extensions_empty(self):
        assert PatternDetector.dominant_extensions([], top_n=1) == []

    def test_avg_message_length(self):
        commits = [_make_commit("one"), _make_commit("two words here")]
        assert PatternDetector.avg_message_length(commits) == 2.0

    def test_avg_message_length_empty(self):
        assert PatternDetector.avg_message_length([]) == 0.0

    def test_avg_commit_interval(self):
        commits = [
            _make_commit("c1", hours_offset=0),
            _make_commit("c2", hours_offset=2),
            _make_commit("c3", hours_offset=4),
        ]
        assert PatternDetector.avg_commit_interval_hours(commits) == 2.0

    def test_avg_commit_interval_single(self):
        assert PatternDetector.avg_commit_interval_hours([_make_commit("c1")]) == 0.0

    def test_files_with_high_churn(self):
        commits = [
            _make_commit(f"c{i}", files=[("hot.py", 1, 0, "M")], hours_offset=i)
            for i in range(5)
        ]
        result = PatternDetector.files_with_high_churn(commits, min_touches=3)
        assert len(result) == 1
        assert result[0] == ("hot.py", 5)

    def test_files_with_high_churn_none_qualify(self):
        commits = [
            _make_commit("c1", files=[("a.py", 1, 0, "M")]),
            _make_commit("c2", files=[("b.py", 1, 0, "M")], hours_offset=1),
        ]
        assert PatternDetector.files_with_high_churn(commits, min_touches=3) == []
