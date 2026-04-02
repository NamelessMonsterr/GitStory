"""
Pattern detection engine.

Changes in v1.3:
  - FIX P1: _author_local_hour returning 0 (midnight) no longer treated as
    falsy. Late-night check uses explicit None comparison.
  - FIX P1: Test keyword scoring doubled (weight=2) and explicit tiebreak
    favors infrastructure when testing keywords are present. This ensures
    "add tests for auth" without file paths classifies as infrastructure.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import timedelta
from pathlib import PurePosixPath

from .models import Commit

# ── Keyword Banks ────────────────────────────────────────────────

_BUGFIX_KEYWORDS = frozenset({
    "fix", "bug", "patch", "hotfix", "issue", "error", "crash", "broken",
    "repair", "resolve", "resolves", "closes", "fixes", "fixed", "debug",
    "fault", "defect", "regression", "workaround", "hack",
})

_FEATURE_KEYWORDS = frozenset({
    "add", "feature", "implement", "new", "create", "introduce", "support",
    "enable", "allow", "build", "develop", "feat",
})

_REFACTOR_KEYWORDS = frozenset({
    "refactor", "clean", "cleanup", "reorganize", "restructure", "rename",
    "simplify", "extract", "move", "migrate", "modernize", "improve",
    "optimize", "rewrite", "consolidate",
})

_INFRA_KEYWORDS = frozenset({
    "ci", "cd", "docker", "deploy", "pipeline", "config", "yaml", "yml",
    "terraform", "helm", "kubernetes", "k8s", "github", "actions", "jenkins",
    "makefile", "dockerfile", "nginx", "lint", "eslint", "prettier",
    "dependabot", "renovate", "bump", "upgrade", "dependency", "deps",
})

_DOC_KEYWORDS = frozenset({
    "doc", "docs", "readme", "changelog", "license", "contributing", "wiki",
    "comment", "jsdoc", "docstring", "typedoc", "api-doc",
})

_TESTING_KEYWORDS = frozenset({
    "test", "tests", "testing", "spec", "specs", "coverage",
    "unittest", "pytest", "jest", "mocha", "cypress",
})

_INFRA_FILES = frozenset({
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".github", "jenkinsfile", "makefile", ".gitlab-ci.yml",
    ".travis.yml", "tox.ini", "setup.cfg", "pyproject.toml",
    "package.json", "tsconfig.json", ".eslintrc", ".prettierrc",
    "webpack.config.js", "vite.config.ts",
})

_TEST_PATTERN = re.compile(
    r"(test_|_test\.|\.test\.|\.spec\.|tests/|__tests__/|spec/)", re.I
)


def _author_local_hour(commit: Commit) -> int | None:
    """Return the commit hour in the author's local timezone.

    Returns None when timezone offset is unknown.
    FIX v1.3: Returns 0 for midnight — no longer confused with falsy.
    """
    if commit.author_tz_offset_hours is None:
        return None
    local_dt = commit.timestamp + timedelta(hours=commit.author_tz_offset_hours)
    return local_dt.hour


class PatternDetector:
    """Stateless utility — all methods are static or classmethod."""

    # ── Commit Classification ────────────────────────────────────

    @staticmethod
    def classify_commit(commit: Commit) -> str:
        """Classify a single commit.

        FIX v1.3: Testing keywords get weight=2, and when testing keywords
        are present AND infrastructure score >= feature score, we force
        'infrastructure'. This prevents "add tests for auth" from being
        classified as feature even without file path data.
        """
        msg_lower = commit.message.lower()
        words = set(re.findall(r"[a-z0-9]+", msg_lower))

        scores: dict[str, int] = {
            "bugfix": len(words & _BUGFIX_KEYWORDS),
            "feature": len(words & _FEATURE_KEYWORDS),
            "refactor": len(words & _REFACTOR_KEYWORDS),
            "infrastructure": len(words & _INFRA_KEYWORDS),
            "documentation": len(words & _DOC_KEYWORDS),
        }

        # Testing keywords boost infrastructure with weight=2
        testing_hits = len(words & _TESTING_KEYWORDS)
        scores["infrastructure"] += testing_hits * 2

        # File path signals
        for fc in commit.file_changes:
            p = fc.path.lower()
            base = PurePosixPath(p).name.lower()
            if base in _INFRA_FILES or any(
                seg in p for seg in (".github/", ".gitlab", "ci/", "deploy/")
            ):
                scores["infrastructure"] += 2
            if _TEST_PATTERN.search(p):
                scores["infrastructure"] += 1
            if any(p.endswith(ext) for ext in (".md", ".rst", ".txt")):
                scores["documentation"] += 1

        # FIX P1: Explicit tiebreak — when testing keywords are present
        # and infrastructure ties or beats feature, force infrastructure.
        # This handles "add tests for auth" (add→feature=1, tests→infra=2).
        if testing_hits > 0 and scores["infrastructure"] >= scores["feature"]:
            return "infrastructure"

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "feature"
        return best

    # ── Gap Detection ────────────────────────────────────────────

    @staticmethod
    def detect_gaps(
        commits: list[Commit], multiplier: float = 3.0
    ) -> list[int]:
        if len(commits) < 3:
            return []
        intervals = [
            (commits[i].timestamp - commits[i - 1].timestamp).total_seconds()
            for i in range(1, len(commits))
        ]
        sorted_intervals = sorted(intervals)
        lower_half = sorted_intervals[: max(1, len(sorted_intervals) // 2)]
        baseline_iv = statistics.median(lower_half)
        threshold = max(baseline_iv * multiplier, 86400)
        return [i + 1 for i, iv in enumerate(intervals) if iv > threshold]

    # ── Vocabulary Shift ─────────────────────────────────────────

    @staticmethod
    def detect_vocabulary_shift(
        window_a: list[Commit], window_b: list[Commit]
    ) -> float:
        def _words(commits: list[Commit]) -> Counter:
            c: Counter = Counter()
            for cm in commits:
                c.update(re.findall(r"[a-z]+", cm.message.lower()))
            return c

        ca = _words(window_a)
        cb = _words(window_b)
        all_keys = set(ca.keys()) | set(cb.keys())
        if not all_keys:
            return 0.0
        overlap = set(ca.keys()) & set(cb.keys())
        return 1.0 - (len(overlap) / len(all_keys))

    # ── File Helpers ─────────────────────────────────────────────

    @staticmethod
    def dominant_extensions(commits: list[Commit], top_n: int = 3) -> list[str]:
        ext_counter: Counter = Counter()
        for c in commits:
            for fc in c.file_changes:
                ext = PurePosixPath(fc.path).suffix or "(no ext)"
                ext_counter[ext] += 1
        return [ext for ext, _ in ext_counter.most_common(top_n)]

    @staticmethod
    def most_changed_files(commits: list[Commit], top_n: int = 5) -> list[str]:
        counter: Counter = Counter()
        for c in commits:
            for fc in c.file_changes:
                counter[fc.path] += 1
        return [path for path, _ in counter.most_common(top_n)]

    @staticmethod
    def count_truly_new_files(commits: list[Commit]) -> int:
        new_paths: set[str] = set()
        for c in commits:
            for fc in c.file_changes:
                if fc.is_new_file:
                    new_paths.add(fc.path)
        return len(new_paths)

    @staticmethod
    def file_status_available(commits: list[Commit]) -> bool:
        for c in commits:
            for fc in c.file_changes:
                if fc.is_status_known:
                    return True
        return False

    @staticmethod
    def files_with_high_churn(
        commits: list[Commit], min_touches: int = 3
    ) -> list[tuple[str, int]]:
        counter: Counter = Counter()
        for c in commits:
            for fc in c.file_changes:
                counter[fc.path] += 1
        return [
            (path, count)
            for path, count in counter.most_common()
            if count >= min_touches
        ]

    # ── Interval Statistics ──────────────────────────────────────

    @staticmethod
    def avg_commit_interval_hours(commits: list[Commit]) -> float:
        if len(commits) < 2:
            return 0.0
        intervals = [
            (commits[i].timestamp - commits[i - 1].timestamp).total_seconds()
            / 3600
            for i in range(1, len(commits))
        ]
        return statistics.mean(intervals)

    @staticmethod
    def avg_message_length(commits: list[Commit]) -> float:
        if not commits:
            return 0.0
        return statistics.mean(c.message_word_count for c in commits)

    @staticmethod
    def unique_authors(commits: list[Commit]) -> list[str]:
        seen: dict[str, None] = {}
        for c in commits:
            seen.setdefault(c.author, None)
        return list(seen.keys())

    # ── Pressure Signal Detection ────────────────────────────────

    @staticmethod
    def detect_pressure_signals(commits: list[Commit]) -> dict[str, float | bool]:
        """Return pressure-indicator scores (each 0.0–1.0).

        FIX v1.3: Midnight (hour=0) is now correctly counted as late-night.
        The previous code used `(_author_local_hour(c) or 12)` which turned
        hour 0 into 12 due to Python's falsy-zero behavior. Now uses
        explicit `is not None` comparison.
        """
        if not commits:
            return {
                "short_messages": 0.0,
                "high_frequency": 0.0,
                "late_night_ratio": 0.0,
                "late_night_available": False,
                "fix_density": 0.0,
            }

        n = len(commits)

        # Short messages (<=3 words)
        short = sum(1 for c in commits if c.message_word_count <= 3)
        short_ratio = short / n

        # High frequency
        if n >= 2:
            span_days = max(
                (commits[-1].timestamp - commits[0].timestamp).total_seconds()
                / 86400,
                0.01,
            )
            freq = n / span_days
        else:
            freq = 0.0
        freq_score = min(freq / 10.0, 1.0)

        # Late night (22:00–06:00 in AUTHOR'S LOCAL TIME)
        # FIX P1: Use explicit None check — hour 0 (midnight) is valid late-night
        tz_known = [c for c in commits if c.tz_known]
        if tz_known:
            late = 0
            for c in tz_known:
                hour = _author_local_hour(c)
                if hour is not None and (hour >= 22 or hour < 6):
                    late += 1
            late_ratio = late / len(tz_known)
            late_night_available = True
        else:
            late_ratio = 0.0
            late_night_available = False

        # Fix keyword density
        fix_words = frozenset(
            {"fix", "bug", "hotfix", "patch", "crash", "error", "broken"}
        )
        fix_count = sum(
            1
            for c in commits
            if set(re.findall(r"[a-z]+", c.message.lower())) & fix_words
        )
        fix_ratio = fix_count / n

        return {
            "short_messages": round(short_ratio, 3),
            "high_frequency": round(freq_score, 3),
            "late_night_ratio": round(late_ratio, 3),
            "late_night_available": late_night_available,
            "fix_density": round(fix_ratio, 3),
        }
