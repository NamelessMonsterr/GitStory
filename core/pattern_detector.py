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

_REACTIVE_INTENT_TERMS = frozenset({
    "fix", "patch", "hotfix", "bug", "error", "crash", "broken", "fail",
    "failure", "failed", "panic", "fault", "rollback", "incident",
    "regression",
})

_PROACTIVE_RESILIENCE_TERMS = frozenset({
    "improve", "optimize", "enhance", "harden", "retry", "fallback",
    "resilience", "graceful", "robust", "prevent", "avoid", "protect",
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

_STYLE_KEYWORDS = frozenset({
    "lint", "format", "formatting", "style", "styling", "whitespace",
    "prettier", "black", "ruff", "isort", "flake8", "cleanup",
})

_IMPLICIT_BUG_VERBS = frozenset({
    "handle", "guard", "prevent", "avoid", "retry", "recover", "fallback",
    "mitigate", "harden", "sanitize",
})

_IMPLICIT_BUG_NOUNS = frozenset({
    "null", "nullptr", "nil", "panic", "timeout", "failure", "fail",
    "exception", "edge", "case", "race", "deadlock", "overflow",
    "underflow", "missing", "invalid",
})

_IMPLICIT_BUG_PHRASES = (
    "edge case",
    "null pointer",
    "retry logic",
    "fallback logic",
    "guard against",
)

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

_FIX_SIGNAL_DIVERSITY_TARGET = 4.0
_MAX_TOKEN_CONTRIBUTION = 0.30
MAX_KEYWORD_HITS_PER_CATEGORY = 3
_CONTEXT_IMPACT_WEIGHTS = {
    "documentation": 0.20,
    "style": 0.20,
    "testing": 0.40,
    "infrastructure": 0.50,
    "product": 1.00,
}
_PRODUCT_CODE_ROOTS = frozenset({
    "src", "app", "lib", "pkg", "packages", "service", "services",
    "server", "client",
})
_NON_PRODUCT_PATH_MARKERS = (
    "docs/", "doc/", "tests/", "test/", "__tests__/", ".github/",
    ".gitlab/", "ci/", "coverage/",
)
_DOC_EXTENSIONS = (".md", ".rst", ".txt")
_CONFLICT_GROUPS = {
    "bugfix": "bug",
    "feature": "feature",
    "refactor": "maintenance",
    "infrastructure": "maintenance",
    "documentation": "maintenance",
}
_CONFLICT_TRANSITION_WEIGHTS = {
    frozenset({"feature", "bug"}): 1.0,
    frozenset({"bug", "maintenance"}): 0.65,
    frozenset({"feature", "maintenance"}): 0.30,
}


def _keyword_score(words: set[str], keyword_bank: frozenset[str]) -> int:
    """Cap per-category keyword influence to avoid message-level over-weighting."""
    return min(len(words & keyword_bank), MAX_KEYWORD_HITS_PER_CATEGORY)


def _path_context_scores(path: str) -> dict[str, int]:
    p = path.lower()
    base = PurePosixPath(p).name.lower()
    scores = {
        "documentation": 0,
        "infrastructure": 0,
        "testing": 0,
        "style": 0,
    }

    if base in _INFRA_FILES or any(
        seg in p for seg in (".github/", ".gitlab", "ci/", "deploy/")
    ):
        scores["infrastructure"] += 2
    if _TEST_PATTERN.search(p):
        scores["testing"] += 2
        scores["infrastructure"] += 1
    if any(p.endswith(ext) for ext in _DOC_EXTENSIONS) or "/docs/" in p:
        scores["documentation"] += 2
    if any(
        token in p
        for token in ("lint", "format", "style", "prettier", "black", "ruff", "isort")
    ):
        scores["style"] += 2

    return scores


def _is_product_like_path(path: str) -> bool:
    p = path.lower()
    if any(marker in p for marker in _NON_PRODUCT_PATH_MARKERS):
        return False

    parts = PurePosixPath(p).parts
    if not parts:
        return False

    root = parts[0]
    if root in _PRODUCT_CODE_ROOTS:
        return True
    if any(p.endswith(ext) for ext in _DOC_EXTENSIONS):
        return False
    return root not in {".github", ".gitlab", "docs", "tests", "ci"}


def _path_area_key(path: str) -> str:
    p = PurePosixPath(path.lower())
    parts = p.parts
    if not parts:
        return "(root)"
    if len(parts) == 1:
        return p.stem or p.name
    second = PurePosixPath(parts[1]).stem if "." in parts[1] else parts[1]
    return f"{parts[0]}/{second}"


def _tokenize_message(message: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", message.lower()))


def _implicit_bug_indicators(message: str, words: set[str]) -> set[str]:
    message_lower = message.lower()
    indicators: set[str] = set()

    if (words & _IMPLICIT_BUG_VERBS) and (words & _IMPLICIT_BUG_NOUNS):
        indicators.add("guarded_fault")
    if {"retry", "logic"} <= words:
        indicators.add("retry_logic")
    if {"null", "pointer"} <= words or "nullptr" in words:
        indicators.add("null_pointer")
    if {"edge", "case"} <= words:
        indicators.add("edge_case")
    for phrase in _IMPLICIT_BUG_PHRASES:
        if phrase in message_lower:
            indicators.add(phrase.replace(" ", "_"))
    return indicators


def _impact_weight_for_context(name: str) -> float:
    return _CONTEXT_IMPACT_WEIGHTS.get(name, 1.0)


def _burst_metrics(commits: list[Commit]) -> tuple[float, float]:
    if len(commits) < 3:
        return 0.0, 1.0

    total_hours = max(
        (commits[-1].timestamp - commits[0].timestamp).total_seconds() / 3600,
        0.25,
    )
    average_rate = len(commits) / total_hours
    max_window_rate = average_rate

    for window_size in range(3, min(5, len(commits)) + 1):
        for idx in range(0, len(commits) - window_size + 1):
            window_hours = max(
                (
                    commits[idx + window_size - 1].timestamp
                    - commits[idx].timestamp
                ).total_seconds()
                / 3600,
                0.05,
            )
            max_window_rate = max(max_window_rate, window_size / window_hours)

    compression_ratio = max_window_rate / max(average_rate, 0.1)
    relative_pressure = min(max((compression_ratio - 1.0) / 3.0, 0.0), 1.0)
    absolute_pressure = min(max_window_rate / 8.0, 1.0)
    burst_pressure = max(relative_pressure, absolute_pressure)
    return round(burst_pressure, 3), round(compression_ratio, 3)


def _alternation_ratio(labels: list[str]) -> float:
    if len(labels) < 2:
        return 0.0
    switches = sum(1 for left, right in zip(labels, labels[1:]) if left != right)
    return round(switches / (len(labels) - 1), 3)


def _conflict_group(label: str) -> str:
    return _CONFLICT_GROUPS.get(label, label)


def _conflict_transition_weight(left_group: str, right_group: str) -> float:
    if left_group == right_group:
        return 0.0
    return _CONFLICT_TRANSITION_WEIGHTS.get(
        frozenset({left_group, right_group}),
        0.0,
    )


def _conflict_alternation_ratio(labels: list[str]) -> float:
    if len(labels) < 2:
        return 0.0

    weighted_switches = 0.0
    for left, right in zip(labels, labels[1:]):
        left_group = _conflict_group(left)
        right_group = _conflict_group(right)
        weighted_switches += _conflict_transition_weight(left_group, right_group)
    return round(weighted_switches / (len(labels) - 1), 3)


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
        words = _tokenize_message(commit.message)

        scores: dict[str, int] = {
            "bugfix": _keyword_score(words, _BUGFIX_KEYWORDS),
            "feature": _keyword_score(words, _FEATURE_KEYWORDS),
            "refactor": _keyword_score(words, _REFACTOR_KEYWORDS),
            "infrastructure": _keyword_score(words, _INFRA_KEYWORDS),
            "documentation": _keyword_score(words, _DOC_KEYWORDS),
        }

        # Testing keywords boost infrastructure with weight=2
        testing_hits = _keyword_score(words, _TESTING_KEYWORDS)
        scores["infrastructure"] += testing_hits * 2
        scores["refactor"] += _keyword_score(words, _STYLE_KEYWORDS) * 2

        # File path signals
        for fc in commit.file_changes:
            path_scores = _path_context_scores(fc.path)
            scores["documentation"] += path_scores["documentation"]
            scores["infrastructure"] += path_scores["infrastructure"]
            scores["refactor"] += path_scores["style"]

        # FIX P1: Explicit tiebreak — when testing keywords are present
        # and infrastructure ties or beats feature, force infrastructure.
        # This handles "add tests for auth" (add→feature=1, tests→infra=2).
        if testing_hits > 0 and scores["infrastructure"] >= scores["feature"]:
            return "infrastructure"

        semantic_context = PatternDetector.fix_context(commit)
        if scores["bugfix"] > 0 or semantic_context["implicit_bug_candidate"]:
            if semantic_context["cleanup_fix_candidate"]:
                dominant_context = semantic_context["dominant"]
                if dominant_context == "documentation":
                    return "documentation"
                if dominant_context in {"infrastructure", "testing"}:
                    return "infrastructure"
                if dominant_context == "style":
                    return "refactor"
            elif semantic_context["product_fix_candidate"]:
                return "bugfix"

            dominant_context = semantic_context["dominant"]
            if dominant_context == "documentation":
                return "documentation"
            if dominant_context in {"infrastructure", "testing"}:
                return "infrastructure"
            if dominant_context == "style":
                return "refactor"

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "feature"
        return best

    @staticmethod
    def conflict_alternation_ratio(labels: list[str]) -> float:
        return _conflict_alternation_ratio(labels)

    @staticmethod
    def fix_context(commit: Commit) -> dict[str, object]:
        """Infer whether a fix-like commit is product-facing or cleanup-oriented."""
        words = _tokenize_message(commit.message)
        explicit_bug_hits = _keyword_score(words, _BUGFIX_KEYWORDS)
        implicit_bug_indicators = sorted(
            _implicit_bug_indicators(commit.message, words)
        )
        explicit_bug_strength = (
            min(0.50 + (explicit_bug_hits * 0.25), 1.0)
            if explicit_bug_hits
            else 0.0
        )
        implicit_bug_strength = (
            min(0.40 + (len(implicit_bug_indicators) * 0.20), 1.0)
            if implicit_bug_indicators
            else 0.0
        )
        reactive_hits = _keyword_score(words, _REACTIVE_INTENT_TERMS)
        proactive_hits = _keyword_score(words, _PROACTIVE_RESILIENCE_TERMS)
        if any(
            indicator in implicit_bug_indicators
            for indicator in ("guarded_fault", "null_pointer", "edge_case")
        ):
            reactive_hits += 1
        if any(
            indicator in implicit_bug_indicators
            for indicator in ("retry_logic", "fallback_logic")
        ):
            proactive_hits += 1
        reactive_score = min(
            (reactive_hits / 3.0) + (explicit_bug_strength * 0.5),
            1.0,
        )
        proactive_score = min(
            (proactive_hits / 3.0) + (implicit_bug_strength * 0.35),
            1.0,
        )
        context_scores = {
            "documentation": _keyword_score(words, _DOC_KEYWORDS),
            "infrastructure": _keyword_score(words, _INFRA_KEYWORDS),
            "testing": _keyword_score(words, _TESTING_KEYWORDS) * 2,
            "style": _keyword_score(words, _STYLE_KEYWORDS) * 2,
        }

        product_like_paths = 0
        area_keys: set[str] = set()
        for fc in commit.file_changes:
            for name, value in _path_context_scores(fc.path).items():
                context_scores[name] += value
            if _is_product_like_path(fc.path):
                product_like_paths += 1
                area_keys.add(_path_area_key(fc.path))

        dominant_name, dominant_score = max(
            context_scores.items(), key=lambda item: item[1]
        )
        if dominant_score == 0:
            dominant = "product"
        elif product_like_paths > 0 and dominant_score <= 1:
            dominant = "product"
        else:
            dominant = dominant_name

        cleanup_score = context_scores[dominant_name]
        impact_weight = _impact_weight_for_context(dominant)
        has_bug_signal = explicit_bug_strength > 0.0 or implicit_bug_strength > 0.0
        product_fix_candidate = (
            has_bug_signal
            and (
                dominant == "product"
                or product_like_paths > cleanup_score
                or (product_like_paths > 0 and cleanup_score == 0)
            )
        )
        cleanup_fix_candidate = (
            explicit_bug_strength > 0.0
            and cleanup_score >= max(product_like_paths, 1)
            and impact_weight < 0.75
        )
        if reactive_score >= proactive_score + 0.15:
            bug_reactivity = "reactive"
        elif proactive_score >= reactive_score + 0.15:
            bug_reactivity = "proactive"
        elif max(reactive_score, proactive_score) > 0:
            bug_reactivity = "mixed"
        else:
            bug_reactivity = "neutral"

        return {
            "dominant": dominant,
            "scores": context_scores,
            "impact_weight": impact_weight,
            "product_like_paths": product_like_paths,
            "area_keys": sorted(area_keys),
            "product_fix_candidate": product_fix_candidate,
            "cleanup_fix_candidate": cleanup_fix_candidate,
            "implicit_bug_candidate": implicit_bug_strength > 0.0,
            "implicit_bug_strength": round(implicit_bug_strength, 3),
            "implicit_bug_indicators": implicit_bug_indicators,
            "explicit_bug_hits": explicit_bug_hits,
            "reactive_score": round(reactive_score, 3),
            "proactive_score": round(proactive_score, 3),
            "bug_reactivity": bug_reactivity,
            "bug_signal_strength": round(
                max(explicit_bug_strength, implicit_bug_strength), 3
            ),
        }

    @staticmethod
    def phase_fix_semantics(
        commits: list[Commit],
    ) -> dict[str, float | dict[str, int]]:
        total_commits = max(len(commits), 1)
        fix_like_commits = 0
        semantic_fix_commits = 0
        implicit_fix_commits = 0
        cleanup_fix_commits = 0
        resilience_commits = 0
        unique_fix_terms: set[str] = set()
        area_counter: Counter = Counter()
        cleanup_counter: Counter = Counter()
        product_signal_total = 0.0
        cleanup_signal_total = 0.0
        product_impact_total = 0.0
        reactive_signal_total = 0.0
        proactive_signal_total = 0.0
        classifications: list[str] = []

        for commit in commits:
            classifications.append(PatternDetector.classify_commit(commit))
            context = PatternDetector.fix_context(commit)
            is_resilience_candidate = (
                context["bug_signal_strength"] <= 0
                and context["proactive_score"] > 0.25
                and context["dominant"] == "product"
            )
            if context["bug_signal_strength"] <= 0 and not is_resilience_candidate:
                continue

            if context["bug_signal_strength"] > 0:
                fix_like_commits += 1
            if context["product_fix_candidate"]:
                semantic_fix_commits += 1
                product_signal_total += (
                    context["bug_signal_strength"] * context["impact_weight"]
                )
                product_impact_total += context["impact_weight"]
                reactive_signal_total += (
                    context["bug_signal_strength"]
                    * context["impact_weight"]
                    * max(context["reactive_score"], 0.15)
                )
                proactive_signal_total += (
                    context["bug_signal_strength"]
                    * context["impact_weight"]
                    * max(context["proactive_score"], 0.15)
                )
                if context["implicit_bug_candidate"] and not context["explicit_bug_hits"]:
                    implicit_fix_commits += 1
                words = _tokenize_message(commit.message)
                unique_fix_terms.update(words & _BUGFIX_KEYWORDS)
                unique_fix_terms.update(context["implicit_bug_indicators"])
                for area in context["area_keys"]:
                    area_counter[area] += 1
            elif is_resilience_candidate:
                resilience_commits += 1
                product_impact_total += context["impact_weight"]
                proactive_signal_total += (
                    context["impact_weight"] * max(context["proactive_score"], 0.25)
                )
                for area in context["area_keys"]:
                    area_counter[area] += 1
            elif context["cleanup_fix_candidate"]:
                cleanup_fix_commits += 1
                cleanup_signal_total += max(context["bug_signal_strength"], 0.25)
                cleanup_counter[context["dominant"]] += 1

        fix_diversity = min(
            len(unique_fix_terms) / _FIX_SIGNAL_DIVERSITY_TARGET,
            1.0,
        )
        product_semantic_commits = semantic_fix_commits + resilience_commits
        fix_coherence = 0.0
        if product_semantic_commits == 1:
            fix_coherence = 1.0
        elif product_semantic_commits > 1 and area_counter:
            fix_coherence = (
                area_counter.most_common(1)[0][1] / product_semantic_commits
            )
        elif product_semantic_commits > 1:
            fix_coherence = 0.55

        total_bug_pressure = product_signal_total + cleanup_signal_total
        semantic_alignment = (
            product_signal_total / total_bug_pressure if total_bug_pressure else 0.0
        )
        impact_weight = (
            product_impact_total / product_semantic_commits
            if product_semantic_commits else 0.0
        )
        total_intent_signal = reactive_signal_total + proactive_signal_total
        reactive_ratio = (
            reactive_signal_total / total_intent_signal if total_intent_signal else 0.0
        )
        proactive_ratio = (
            proactive_signal_total / total_intent_signal if total_intent_signal else 0.0
        )
        alternation_score = _alternation_ratio(classifications)
        conflict_alternation = _conflict_alternation_ratio(classifications)

        return {
            "fix_density": round(min(product_signal_total / total_commits, 1.0), 3),
            "semantic_fix_density": round(semantic_fix_commits / total_commits, 3),
            "implicit_fix_density": round(implicit_fix_commits / total_commits, 3),
            "buglike_density": round(fix_like_commits / total_commits, 3),
            "fix_diversity": round(fix_diversity, 3),
            "cleanup_fix_ratio": round(
                cleanup_signal_total / max(total_bug_pressure, 1e-6), 3
            ),
            "fix_coherence": round(fix_coherence, 3),
            "cleanup_context_counts": dict(cleanup_counter),
            "semantic_alignment": round(semantic_alignment, 3),
            "impact_weight": round(impact_weight, 3),
            "cleanup_fix_commits": cleanup_fix_commits,
            "reactive_ratio": round(reactive_ratio, 3),
            "proactive_ratio": round(proactive_ratio, 3),
            "alternation_score": round(alternation_score, 3),
            "conflict_alternation_score": round(conflict_alternation, 3),
            "proactive_resilience_density": round(
                resilience_commits / total_commits, 3
            ),
        }

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
                "fix_diversity": 0.0,
                "fix_pressure": 0.0,
                "semantic_alignment": 0.0,
                "semantic_fix_density": 0.0,
                "implicit_fix_density": 0.0,
                "fix_coherence": 0.0,
                "cleanup_bias": 0.0,
                "cleanup_fix_ratio": 0.0,
                "impact_weight": 0.0,
                "buglike_density": 0.0,
                "cleanup_fix_commits": 0,
                "reactive_ratio": 0.0,
                "proactive_ratio": 0.0,
                "burst_pressure": 0.0,
                "raw_burst_pressure": 0.0,
                "temporal_urgency": 0.0,
                "compression_ratio": 1.0,
                "alternation_score": 0.0,
                "raw_alternation_score": 0.0,
                "reactive_pressure": 0.0,
                "proactive_pressure": 0.0,
                "proactive_resilience_density": 0.0,
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

        semantics = PatternDetector.phase_fix_semantics(commits)
        burst_pressure, compression_ratio = _burst_metrics(commits)
        fix_ratio = semantics["fix_density"]
        fix_diversity = semantics["fix_diversity"]
        semantic_alignment = semantics["semantic_alignment"]
        cleanup_bias = semantics["cleanup_fix_ratio"]
        fix_coherence = semantics["fix_coherence"]
        impact_weight = semantics["impact_weight"]
        conflict_alternation = semantics["conflict_alternation_score"]
        temporal_weight = (
            max(0.25, impact_weight)
            * max(0.35, semantics["reactive_ratio"])
            * max(0.35, semantic_alignment)
        )
        if impact_weight < 0.5 or cleanup_bias >= 0.6 or semantic_alignment < 0.5:
            temporal_weight *= 0.3
        if semantics["proactive_ratio"] > semantics["reactive_ratio"]:
            temporal_weight *= 0.6
        cleanup_suppressed = impact_weight < 0.40 and cleanup_bias > 0.60
        if cleanup_suppressed:
            adjusted_burst = 0.0
        else:
            adjusted_burst = round(
                min(burst_pressure, burst_pressure * temporal_weight),
                3,
            )
        if cleanup_bias >= 0.75:
            adjusted_burst = round(adjusted_burst * 0.5, 3)
        implicit_reactive_boost = (
            semantics["implicit_fix_density"]
            * max(0.50, impact_weight)
            * max(0.55, semantics["reactive_ratio"])
        )
        temporal_urgency = (
            adjusted_burst
            * max(0.4, semantics["reactive_ratio"])
            * max(0.55, 0.65 + (conflict_alternation * 0.35))
        ) + (implicit_reactive_boost * 0.6)
        if burst_pressure < 0.25:
            temporal_urgency += implicit_reactive_boost * 0.4
        if burst_pressure > 0.50 and semantics["implicit_fix_density"] >= 0.50:
            temporal_urgency += implicit_reactive_boost * 0.45
        if burst_pressure < 0.15 and freq_score < 0.15:
            temporal_urgency = min(temporal_urgency, 0.08)
        if cleanup_suppressed:
            temporal_urgency = 0.0
        temporal_urgency = round(min(temporal_urgency, 1.0), 3)

        base_fix_pressure = min(fix_ratio, fix_diversity + _MAX_TOKEN_CONTRIBUTION)
        fix_pressure = (
            base_fix_pressure
            * semantic_alignment
            * max(0.25, fix_coherence)
        )
        reactive_time_factor = max(
            0.10,
            min(1.0, (adjusted_burst * 0.6) + (temporal_urgency * 0.8)),
        )
        reactive_pressure = (
            fix_pressure
            * semantics["reactive_ratio"]
            * reactive_time_factor
        )
        proactive_pressure = (
            max(
                semantics["proactive_resilience_density"],
                semantics["semantic_fix_density"] * semantics["proactive_ratio"],
            )
            * max(0.35, semantics["proactive_ratio"])
            * max(0.25, impact_weight)
            * max(0.25, 1.0 - burst_pressure)
            * min(len(commits) / 4.0, 1.0)
        )

        return {
            "short_messages": round(short_ratio, 3),
            "high_frequency": round(freq_score, 3),
            "late_night_ratio": round(late_ratio, 3),
            "late_night_available": late_night_available,
            "fix_density": round(fix_ratio, 3),
            "fix_diversity": round(fix_diversity, 3),
            "fix_pressure": round(fix_pressure, 3),
            "semantic_alignment": round(semantic_alignment, 3),
            "semantic_fix_density": round(semantics["semantic_fix_density"], 3),
            "implicit_fix_density": round(semantics["implicit_fix_density"], 3),
            "fix_coherence": round(fix_coherence, 3),
            "cleanup_bias": round(cleanup_bias, 3),
            "cleanup_fix_ratio": round(cleanup_bias, 3),
            "impact_weight": round(impact_weight, 3),
            "buglike_density": round(semantics["buglike_density"], 3),
            "cleanup_fix_commits": semantics["cleanup_fix_commits"],
            "reactive_ratio": round(semantics["reactive_ratio"], 3),
            "proactive_ratio": round(semantics["proactive_ratio"], 3),
            "burst_pressure": adjusted_burst,
            "raw_burst_pressure": round(burst_pressure, 3),
            "temporal_urgency": temporal_urgency,
            "compression_ratio": round(compression_ratio, 3),
            "alternation_score": round(semantics["conflict_alternation_score"], 3),
            "raw_alternation_score": round(semantics["alternation_score"], 3),
            "reactive_pressure": round(reactive_pressure, 3),
            "proactive_pressure": round(proactive_pressure, 3),
            "proactive_resilience_density": round(
                semantics["proactive_resilience_density"], 3
            ),
            "implicit_reactive_boost": round(implicit_reactive_boost, 3),
        }
