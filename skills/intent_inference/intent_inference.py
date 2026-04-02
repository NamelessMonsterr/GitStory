"""
Skill 2: Intent Inference Engine

Changes in v1.2:
  - P1: Unknown file status (stdin) → new-file count shown as "unavailable"
  - Numeric confidence_score (0.0–1.0) computed from signal strengths
  - Sharper narrative language
"""

from __future__ import annotations

import re

from core.models import (
    Confidence,
    Evidence,
    IntentInference,
    Phase,
    PhaseType,
)
from core.pattern_detector import PatternDetector


class IntentInferenceEngine:

    def run(self, phases: list[Phase]) -> list[IntentInference]:
        return [self._analyze_phase(phase) for phase in phases]

    def _analyze_phase(self, phase: Phase) -> IntentInference:
        signals = self._gather_signals(phase)
        observation = self._build_observation(phase)
        pattern = self._build_pattern(signals)
        intent_summary, confidence, confidence_score = self._synthesize(
            phase, signals
        )

        reasoning = [
            f"[{name}] {data['description']}"
            for name, data in signals.items()
            if data["active"]
        ]
        evidence = [
            Evidence(
                signal=name,
                detail=data["description"],
                commits_involved=data.get("commits_involved", 0),
            )
            for name, data in signals.items()
            if data["active"]
        ]

        return IntentInference(
            phase_number=phase.phase_number,
            intent_summary=intent_summary,
            confidence=confidence,
            confidence_score=round(confidence_score, 2),
            reasoning=reasoning,
            evidence=evidence,
            observation=observation,
            pattern=pattern,
        )

    # ── Signal Gathering ─────────────────────────────────────────

    def _gather_signals(self, phase: Phase) -> dict[str, dict]:
        commits = phase.commits
        m = phase.metrics
        pressure = PatternDetector.detect_pressure_signals(commits)
        n = max(len(commits), 1)

        signals: dict[str, dict] = {}

        # 1. Urgency / Pressure
        late_weight = 0.20 if pressure.get("late_night_available", False) else 0.0
        remaining = 1.0 - late_weight
        pressure_score = (
            pressure["short_messages"] * (remaining * 0.30)
            + pressure["high_frequency"] * (remaining * 0.35)
            + pressure["late_night_ratio"] * late_weight
            + pressure["fix_density"] * (remaining * 0.35)
        )
        fix_commits = sum(
            1
            for c in commits
            if set(re.findall(r"[a-z]+", c.message.lower()))
            & {"fix", "bug", "hotfix", "patch", "crash", "error", "broken"}
        )
        late_detail = (
            f"late-night={pressure['late_night_ratio']:.0%} (author-local)"
            if pressure.get("late_night_available")
            else "late-night=unavailable (no tz data)"
        )
        signals["urgency_pressure"] = {
            "active": pressure_score > 0.35,
            "score": round(pressure_score, 3),
            "description": (
                f"Pressure score {pressure_score:.2f} — "
                f"short msgs={pressure['short_messages']:.0%}, "
                f"frequency={pressure['high_frequency']:.2f}, "
                f"{late_detail}, "
                f"fix-density={pressure['fix_density']:.0%}"
            ),
            "commits_involved": fix_commits,
        }

        # 2. Feature Push
        feature_commits = sum(
            1
            for c in commits
            if PatternDetector.classify_commit(c) == "feature"
        )
        feature_ratio = feature_commits / n

        # FIX P1: distinguish known vs unknown file status
        if m.file_status_available:
            new_files_desc = (
                f"{m.new_files_added} genuinely new files (git status=A)"
            )
        else:
            new_files_desc = "new file count unavailable (stdin mode)"

        signals["feature_push"] = {
            "active": feature_ratio > 0.5 and m.total_additions > m.total_deletions,
            "score": round(feature_ratio, 3),
            "description": (
                f"{feature_commits}/{len(commits)} commits classified as feature, "
                f"{new_files_desc}, "
                f"+{m.total_additions}/-{m.total_deletions} line balance"
            ),
            "commits_involved": feature_commits,
        }

        # 3. Tech Debt Payoff
        refactor_commits = sum(
            1
            for c in commits
            if PatternDetector.classify_commit(c) == "refactor"
        )
        deletion_heavy = m.total_deletions > m.total_additions * 0.8
        signals["tech_debt_payoff"] = {
            "active": refactor_commits >= 3 or (
                refactor_commits >= 2 and deletion_heavy
            ),
            "score": round(refactor_commits / n, 3),
            "description": (
                f"{refactor_commits} refactor commits, "
                f"deletion-heavy={deletion_heavy} "
                f"(+{m.total_additions}/-{m.total_deletions})"
            ),
            "commits_involved": refactor_commits,
        }

        # 4. Stabilization
        test_file_changes = sum(
            1
            for c in commits
            for fc in c.file_changes
            if re.search(
                r"(test_|_test\.|\.test\.|\.spec\.|tests/|__tests__/)",
                fc.path, re.I,
            )
        )
        ci_file_changes = sum(
            1
            for c in commits
            for fc in c.file_changes
            if any(
                kw in fc.path.lower()
                for kw in (".github/", "ci/", "jenkinsfile", ".gitlab-ci", "tox.ini")
            )
        )
        signals["stabilization"] = {
            "active": test_file_changes >= 3 or ci_file_changes >= 2,
            "score": round((test_file_changes + ci_file_changes) / n, 3),
            "description": (
                f"{test_file_changes} test-related file changes, "
                f"{ci_file_changes} CI/infra file changes"
            ),
            "commits_involved": test_file_changes + ci_file_changes,
        }

        # 5. Documentation Push
        doc_commits = sum(
            1
            for c in commits
            if PatternDetector.classify_commit(c) == "documentation"
        )
        signals["documentation_push"] = {
            "active": doc_commits >= 3 or (doc_commits / n > 0.4),
            "score": round(doc_commits / n, 3),
            "description": f"{doc_commits}/{len(commits)} commits are documentation-focused",
            "commits_involved": doc_commits,
        }

        # 6. Team Change / Handoff
        authors = PatternDetector.unique_authors(commits)
        signals["team_change"] = {
            "active": len(authors) >= 3 or (
                m.unique_authors >= 2 and signals["documentation_push"]["active"]
            ),
            "score": round(len(authors) / n, 3),
            "description": (
                f"{len(authors)} unique authors in this phase: "
                f"{', '.join(authors[:5])}"
            ),
            "commits_involved": len(commits),
        }

        return signals

    # ── Observation ──────────────────────────────────────────────

    @staticmethod
    def _build_observation(phase: Phase) -> str:
        m = phase.metrics
        s = phase.start_date.strftime("%Y-%m-%d")
        e = phase.end_date.strftime("%Y-%m-%d")

        if m.file_status_available:
            new_file_text = f"New files introduced: {m.new_files_added}."
        else:
            new_file_text = "New file count: unavailable (stdin mode, no git status data)."

        return (
            f"Phase {phase.phase_number} spans {s} to {e} "
            f"({phase.duration_days:.1f} days). "
            f"{m.commit_count} commits by {m.unique_authors} author(s). "
            f"+{m.total_additions}/-{m.total_deletions} lines "
            f"({m.total_churn} total churn). "
            f"Avg commit interval: {m.avg_commit_interval_hours:.1f}h. "
            f"Avg message length: {m.avg_message_length_words:.1f} words. "
            f"{new_file_text}"
        )

    # ── Pattern ──────────────────────────────────────────────────

    @staticmethod
    def _build_pattern(signals: dict[str, dict]) -> str:
        active = [name for name, s in signals.items() if s["active"]]
        if not active:
            return "No strong patterns detected in this phase."

        descriptions = {
            "urgency_pressure": "pressure indicators elevated — terse messages, high frequency, fix-heavy vocabulary",
            "feature_push": "feature-heavy profile with net code growth",
            "tech_debt_payoff": "deliberate refactoring with significant code removal",
            "stabilization": "testing and CI infrastructure being reinforced",
            "documentation_push": "documentation is a primary focus",
            "team_change": "multiple contributors active, possible handoff",
        }
        parts = [descriptions[a] for a in active if a in descriptions]
        return "Detected patterns: " + "; ".join(parts) + "."

    # ── Synthesis ────────────────────────────────────────────────

    def _synthesize(
        self, phase: Phase, signals: dict[str, dict]
    ) -> tuple[str, Confidence, float]:
        """Returns (summary, categorical confidence, numeric score)."""
        active = {name: s for name, s in signals.items() if s["active"]}
        count = len(active)

        if count >= 3:
            confidence = Confidence.HIGH
        elif count >= 2:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        # Numeric confidence: base 0.25 + signal contributions
        total_signal_score = sum(s["score"] for s in active.values())
        confidence_score = min(
            0.25 + (count * 0.15) + (total_signal_score * 0.08), 0.95
        )

        m = phase.metrics

        # INITIAL checked FIRST — cannot be overridden
        if phase.phase_type == PhaseType.INITIAL:
            if m.file_status_available:
                new_detail = (
                    f"{m.new_files_added} new files were created in "
                    f"{m.commit_count} commits"
                )
            else:
                new_detail = f"{m.commit_count} commits laid the groundwork"
            return (
                f"Initial repository setup. Foundational files and project "
                f"scaffolding are being established. {new_detail} — "
                f"this is the project's origin point."
            ), confidence, confidence_score

        has_urgency = "urgency_pressure" in active
        has_feature = "feature_push" in active
        has_debt = "tech_debt_payoff" in active
        has_stable = "stabilization" in active
        has_docs = "documentation_push" in active
        has_team = "team_change" in active

        if phase.phase_type == PhaseType.REFACTOR or has_debt:
            summary = (
                "Someone is cleaning house. Refactoring keywords dominate, "
                f"and the deletion-to-addition ratio "
                f"(+{m.total_additions}/-{m.total_deletions}) shows "
                f"code consolidation, not growth. This is deliberate "
                f"technical debt reduction — the kind that happens when "
                f"someone finally wins the argument about code quality."
            )
        elif has_urgency and not has_feature:
            summary = (
                "This isn't planned development — it's damage control. "
                f"High-frequency, low-diff commits over a compressed window "
                f"({m.commit_frequency_per_day:.1f}/day) with terse messages "
                f"(avg {m.avg_message_length_words:.1f} words) and fix-heavy "
                f"vocabulary. The pattern is textbook reactive bug fixing — "
                f"likely post-release stabilization or production incident response."
            )
        elif has_feature and not has_urgency:
            summary = (
                "This is a deliberate feature development cycle. "
                f"Net code growth is strongly positive "
                f"(+{m.total_additions}/-{m.total_deletions}), "
                f"commit messages reference new functionality, and the pace "
                f"({m.commit_frequency_per_day:.1f}/day, avg "
                f"{m.avg_message_length_words:.1f} words/msg) suggests "
                f"planned, methodical work — not reactive."
            )
        elif has_feature and has_urgency:
            summary = (
                "Feature development under time pressure. New code is "
                "landing fast with commit messages getting shorter. "
                "This pattern is consistent with a deadline-driven sprint — "
                "someone is building against a clock. "
                f"{m.commit_frequency_per_day:.1f} commits/day with "
                f"+{m.total_additions} lines says ambition. "
                f"Avg message length of {m.avg_message_length_words:.1f} "
                f"words says urgency."
            )
        elif has_stable:
            summary = (
                "Stabilization mode. Tests are being added, CI pipelines "
                "tuned, reliability reinforced. This typically follows "
                "a feature push or incident — the shift from "
                "'make it work' to 'make it solid.' The commit frequency "
                f"({m.commit_frequency_per_day:.1f}/day) is measured, not frantic."
            )
        elif has_docs:
            summary = (
                "Documentation is the primary activity — preparation for "
                "a release, onboarding, or post-development sweep. "
                f"{m.commit_count} doc-focused commits suggests intent, "
                f"not afterthought."
            )
        elif has_team:
            summary = (
                "Multiple new contributors appeared. The commit patterns "
                "suggest team expansion or a handoff period with active "
                "knowledge transfer."
            )
        else:
            summary = (
                "Mixed activity without a dominant signal. Steady, routine "
                "development — incremental improvements, minor fixes, "
                "regular maintenance. Nothing dramatic. Just work."
            )

        return summary, confidence, confidence_score
