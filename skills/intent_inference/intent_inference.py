"""
Skill 2: Intent Inference Engine

Changes in v1.2:
  - P1: Unknown file status (stdin) → new-file count shown as "unavailable"
  - Numeric confidence_score (0.0–1.0) computed from signal strengths
  - Sharper narrative language
"""

from __future__ import annotations

import re

from analysis.calibration import load_calibrator
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
            signal_scores={
                name: round(data["score"], 3) for name, data in signals.items()
            },
            reasoning=reasoning,
            evidence=evidence,
            observation=observation,
            pattern=pattern,
        )

    # ── Signal Gathering ─────────────────────────────────────────

    def _gather_signals(self, phase: Phase) -> dict[str, dict]:
        calibrator = load_calibrator()
        commits = phase.commits
        m = phase.metrics
        pressure = PatternDetector.detect_pressure_signals(commits)
        n = max(len(commits), 1)

        signals: dict[str, dict] = {}

        # 1. Urgency / Pressure
        late_weight = 0.20 if pressure.get("late_night_available", False) else 0.0
        remaining = 1.0 - late_weight
        temporal_urgency = pressure.get("temporal_urgency", pressure["burst_pressure"])
        base_pressure_score = (
            pressure["short_messages"] * (remaining * 0.18)
            + pressure["high_frequency"] * (remaining * 0.18)
            + temporal_urgency * (remaining * 0.24)
            + pressure["late_night_ratio"] * late_weight
            + pressure["reactive_pressure"] * (remaining * 0.30)
            + pressure["fix_pressure"] * (remaining * 0.10)
        )
        pressure_score = (
            base_pressure_score
            * max(0.15, 1.0 - pressure["cleanup_bias"])
            * max(0.25, pressure["impact_weight"])
            * max(0.35, pressure["reactive_ratio"] + 0.15)
        )
        if pressure["implicit_fix_density"] >= 0.25 and pressure["impact_weight"] >= 0.75:
            pressure_score = max(
                pressure_score,
                (temporal_urgency * 0.60)
                + (pressure["implicit_fix_density"] * 0.30)
                + (pressure["semantic_alignment"] * 0.10),
            )
        urgency_suppressed = (
            (pressure["impact_weight"] < 0.4 and pressure["cleanup_bias"] > 0.6)
            or (
                temporal_urgency < calibrator.temporal_signal_min()
                and pressure["reactive_pressure"] < 0.15
            )
        )
        fix_commits = sum(
            1
            for c in commits
            if set(re.findall(r"[a-z]+", c.message.lower()))
            & {"fix", "bug", "hotfix", "patch", "crash", "error", "broken"}
        )
        bug_signal_commits = max(
            fix_commits,
            int(round(pressure.get("buglike_density", 0.0) * len(commits))),
        )
        late_detail = (
            f"late-night={pressure['late_night_ratio']:.0%} (author-local)"
            if pressure.get("late_night_available")
            else "late-night=unavailable (no tz data)"
        )
        signals["urgency_pressure"] = {
            "active": (
                not urgency_suppressed
                and temporal_urgency >= calibrator.temporal_signal_min()
                and pressure_score >= calibrator.urgency_signal_min()
                and (len(commits) >= 2 or pressure["fix_pressure"] > 0.5)
                and (
                    pressure["reactive_pressure"] > 0.15
                    or pressure["fix_pressure"] > 0.2
                    or pressure["semantic_alignment"] > 0.4
                    or pressure["implicit_fix_density"] > 0.2
                    or pressure["late_night_ratio"] > 0.3
                )
            ),
            "score": round(pressure_score, 3),
            "description": (
                f"Pressure score {pressure_score:.2f} — "
                f"short msgs={pressure['short_messages']:.0%}, "
                f"frequency={pressure['high_frequency']:.2f}, "
                f"burst-adjusted={pressure['burst_pressure']:.2f}, "
                f"burst-raw={pressure.get('raw_burst_pressure', pressure['burst_pressure']):.2f}, "
                f"compression={pressure['compression_ratio']:.2f}, "
                f"{late_detail}, "
                f"fix-density={pressure['fix_density']:.0%}, "
                f"implicit-fix-density={pressure['implicit_fix_density']:.0%}, "
                f"fix-diversity={pressure['fix_diversity']:.2f}, "
                f"fix-pressure={pressure['fix_pressure']:.0%}, "
                f"reactive-pressure={pressure['reactive_pressure']:.0%}, "
                f"semantic-alignment={pressure['semantic_alignment']:.0%}, "
                f"reactive-ratio={pressure['reactive_ratio']:.0%}, "
                f"proactive-ratio={pressure['proactive_ratio']:.0%}, "
                f"alternation={pressure['alternation_score']:.0%}, "
                f"coherence={pressure['fix_coherence']:.0%}, "
                f"impact-weight={pressure['impact_weight']:.0%}, "
                f"cleanup-bias={pressure['cleanup_bias']:.0%}"
            ),
            "commits_involved": bug_signal_commits,
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
            "active": (
                doc_commits >= 3 or (doc_commits / n > 0.4)
            )
            and not (
                pressure["cleanup_bias"] >= 0.75
                and temporal_urgency < calibrator.temporal_signal_min()
            ),
            "score": round(doc_commits / n, 3),
            "description": f"{doc_commits}/{len(commits)} commits are documentation-focused",
            "commits_involved": doc_commits,
        }

        # 6. Maintenance Cleanup
        cleanup_score = (
            max(pressure["cleanup_bias"], 1.0 - pressure["impact_weight"])
            * max(pressure["fix_coherence"], 0.60)
        )
        signals["maintenance_cleanup"] = {
            "active": (
                cleanup_score > 0.40
                and pressure["cleanup_bias"] >= 0.55
                and (
                    pressure["impact_weight"] <= 0.55
                    or (
                        pressure["cleanup_bias"] >= 0.75
                        and temporal_urgency < calibrator.temporal_signal_min()
                    )
                )
            ),
            "score": round(cleanup_score, 3),
            "description": (
                f"Cleanup score {cleanup_score:.2f} — "
                f"cleanup-bias={pressure['cleanup_bias']:.0%}, "
                f"impact-weight={pressure['impact_weight']:.0%}, "
                f"coherence={pressure['fix_coherence']:.0%}, "
                f"cleanup-fix-commits={pressure['cleanup_fix_commits']}"
            ),
            "commits_involved": pressure["cleanup_fix_commits"],
        }

        # 7. Planned Resilience
        resilience_score = (
            pressure["proactive_pressure"]
            * max(0.35, pressure["impact_weight"])
            * max(0.25, 1.0 - pressure["burst_pressure"])
            * max(0.25, 1.0 - pressure["cleanup_bias"])
        )
        signals["planned_resilience"] = {
            "active": (
                resilience_score > 0.18
                and len(commits) >= 2
                and pressure["proactive_ratio"] > pressure["reactive_ratio"]
                and pressure["impact_weight"] >= 0.6
                and pressure["burst_pressure"] < 0.45
                and pressure.get("proactive_resilience_density", 0.0) >= 0.25
            ),
            "score": round(resilience_score, 3),
            "description": (
                f"Resilience score {resilience_score:.2f} — "
                f"proactive-pressure={pressure['proactive_pressure']:.0%}, "
                f"proactive-ratio={pressure['proactive_ratio']:.0%}, "
                f"burst={pressure['burst_pressure']:.0%}, "
                f"impact-weight={pressure['impact_weight']:.0%}, "
                f"alternation={pressure['alternation_score']:.0%}"
            ),
            "commits_involved": bug_signal_commits,
        }

        # 8. Team Change / Handoff
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
            "urgency_pressure": "pressure indicators elevated — reactive bug work compressed into a tight burst",
            "feature_push": "feature-heavy profile with net code growth",
            "tech_debt_payoff": "deliberate refactoring with significant code removal",
            "stabilization": "testing and CI infrastructure being reinforced",
            "documentation_push": "documentation is a primary focus",
            "maintenance_cleanup": "coherent low-impact cleanup dominates the phase",
            "planned_resilience": "proactive hardening and resilience work is being layered in deliberately",
            "team_change": "multiple contributors active, possible handoff",
        }
        parts = [descriptions[a] for a in active if a in descriptions]
        return "Detected patterns: " + "; ".join(parts) + "."

    # ── Synthesis ────────────────────────────────────────────────

    def _synthesize(
        self, phase: Phase, signals: dict[str, dict]
    ) -> tuple[str, Confidence, float]:
        """Returns (summary, categorical confidence, numeric score)."""
        pressure = PatternDetector.detect_pressure_signals(phase.commits)
        calibrator = load_calibrator()
        active = {name: s for name, s in signals.items() if s["active"]}
        count = len(active)

        if count >= 3:
            confidence = Confidence.HIGH
        elif count >= 2:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        signal_weights = {
            "urgency_pressure": 1.25,
            "feature_push": 1.0,
            "tech_debt_payoff": 1.0,
            "stabilization": 0.85,
            "documentation_push": 0.70,
            "maintenance_cleanup": 0.70,
            "planned_resilience": 0.85,
            "team_change": 0.60,
        }
        signal_groups = {
            "urgency_pressure": "pressure",
            "feature_push": "growth",
            "tech_debt_payoff": "debt",
            "stabilization": "stability",
            "documentation_push": "cleanup",
            "maintenance_cleanup": "cleanup",
            "planned_resilience": "resilience",
            "team_change": "team",
        }

        if not active:
            confidence_score = 0.25
        else:
            weighted_scores = [
                min(data["score"] * signal_weights.get(name, 1.0), 1.0)
                for name, data in active.items()
            ]
            top_signal = max(weighted_scores)
            mean_signal = sum(weighted_scores) / len(weighted_scores)
            distinct_groups = len(
                {signal_groups.get(name, name) for name in active}
            )
            confidence_score = min(
                0.15
                + (top_signal * 0.45)
                + (mean_signal * 0.05)
                + (max(distinct_groups - 1, 0) * 0.12),
                0.95,
            )
            if (
                phase.phase_type in {PhaseType.HOTFIX, PhaseType.BUGFIX}
                and signals["urgency_pressure"]["score"] >= calibrator.urgency_boost_min()
            ):
                confidence_score = max(confidence_score, 0.5)
            if (
                phase.phase_type in {PhaseType.HOTFIX, PhaseType.BUGFIX}
                and signals["urgency_pressure"]["score"] >= calibrator.urgency_boost_high()
                and "maintenance_cleanup" not in active
                and "planned_resilience" not in active
            ):
                confidence_score = max(confidence_score, 0.8)

        if (
            phase.phase_type in {PhaseType.HOTFIX, PhaseType.BUGFIX}
            and pressure["implicit_fix_density"] >= 0.25
            and pressure["semantic_alignment"] >= 0.55
            and pressure["impact_weight"] >= 0.75
        ):
            semantic_floor = min(
                0.58,
                0.18
                + (pressure["implicit_fix_density"] * 0.24)
                + (pressure["reactive_ratio"] * 0.08)
                + (pressure["impact_weight"] * 0.08),
            )
            confidence_score = max(confidence_score, semantic_floor)

        if (
            phase.phase_type in {PhaseType.HOTFIX, PhaseType.BUGFIX}
            and pressure["buglike_density"] >= 0.85
            and pressure["fix_density"] >= 0.60
            and pressure["semantic_alignment"] >= 0.75
            and pressure["reactive_ratio"] >= 0.70
        ):
            confidence_score = max(confidence_score, 0.35)

        if (
            phase.phase_type == PhaseType.REFACTOR
            and pressure.get("temporal_urgency", pressure["burst_pressure"])
            < calibrator.temporal_quiet_max()
            and pressure["reactive_ratio"] < 0.3
        ):
            confidence_score *= 0.92

        if (
            phase.phase_type == PhaseType.FEATURE
            and signals["maintenance_cleanup"]["active"]
            and pressure["alternation_score"] < 0.4
            and pressure["raw_alternation_score"] > pressure["alternation_score"]
            and pressure.get("temporal_urgency", pressure["burst_pressure"])
            < calibrator.temporal_signal_min()
        ):
            confidence_score = max(confidence_score, 0.45)

        if (
            phase.phase_type in {PhaseType.HOTFIX, PhaseType.BUGFIX}
            and pressure.get("temporal_urgency", pressure["burst_pressure"])
            < calibrator.temporal_signal_min()
            and (pressure["fix_diversity"] * pressure["impact_weight"]) < 0.3
        ):
            confidence_score *= 0.9

        if (
            "maintenance_cleanup" in active
            and phase.phase_type != PhaseType.FEATURE
            and pressure.get("temporal_urgency", pressure["burst_pressure"])
            < calibrator.temporal_signal_min()
        ):
            confidence_score *= 0.8

        confidence_score = round(min(max(confidence_score, 0.0), 0.95), 3)
        confidence_bucket = calibrator.map_confidence(confidence_score)
        confidence = {
            "high": Confidence.HIGH,
            "medium": Confidence.MEDIUM,
            "low": Confidence.LOW,
        }[confidence_bucket]

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
        has_cleanup = "maintenance_cleanup" in active
        has_resilience = "planned_resilience" in active
        has_team = "team_change" in active
        cleanup_heavy = (
            has_cleanup
            or (
                phase.phase_type
                in {
                    PhaseType.MIXED,
                    PhaseType.INFRASTRUCTURE,
                    PhaseType.DOCUMENTATION,
                    PhaseType.REFACTOR,
                }
                and signals["urgency_pressure"]["score"] < calibrator.urgency_signal_min()
                and pressure["cleanup_bias"] >= 0.7
            )
        )

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
                f"(avg {m.avg_message_length_words:.1f} words) and concentrated "
                f"bug-handling signals. The pattern is textbook reactive bug fixing — "
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
        elif has_resilience and not has_urgency:
            summary = (
                "This looks like proactive hardening, not reactive firefighting. "
                "The commits concentrate on retries, fallbacks, and defensive behavior, "
                "but the temporal profile stays controlled rather than bursty. "
                "That pattern fits planned resilience work around critical paths."
            )
        elif has_stable:
            summary = (
                "Stabilization mode. Tests are being added, CI pipelines "
                "tuned, reliability reinforced. This typically follows "
                "a feature push or incident — the shift from "
                "'make it work' to 'make it solid.' The commit frequency "
                f"({m.commit_frequency_per_day:.1f}/day) is measured, not frantic."
            )
        elif cleanup_heavy:
            summary = (
                "Maintenance cleanup, not firefighting. The phase is dominated "
                "by documentation, infrastructure, and style-oriented fixes, "
                "with low semantic bug pressure. This looks like deliberate "
                "housekeeping rather than product instability."
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
