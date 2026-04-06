"""
Skill 5: Risk Detection Engine
Flags unstable, fragile, or high-risk development patterns.
Transforms retrospective analysis into decision intelligence.
"""

from __future__ import annotations

import re
from collections import Counter

from analysis.calibration import load_calibrator
from core.models import (
    Phase,
    PhaseType,
    IntentInference,
    RiskLevel,
    RiskAssessment,
)
from core.pattern_detector import PatternDetector

MIN_CHURN_RISK_COMMITS = 7


class RiskDetectionEngine:
    """Evaluates phases and cross-phase patterns for risk signals."""

    def run(
        self,
        phases: list[Phase],
        inferences: list[IntentInference],
    ) -> list[RiskAssessment]:
        risks: list[RiskAssessment] = []
        risk_counter = 0

        # Per-phase risks
        for phase in phases:
            phase_risks = self._assess_phase(phase, risk_counter)
            risks.extend(phase_risks)
            risk_counter += len(phase_risks)

        # Cross-phase risks
        cross_risks = self._assess_cross_phase(phases, inferences, risk_counter)
        risks.extend(cross_risks)

        # Sort by severity
        severity_order = {
            RiskLevel.CRITICAL: 0,
            RiskLevel.HIGH: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.LOW: 3,
            RiskLevel.NONE: 4,
        }
        risks.sort(key=lambda r: severity_order[r.risk_level])

        return risks

    # ── Per-Phase Assessment ─────────────────────────────────────

    def _assess_phase(
        self, phase: Phase, start_id: int
    ) -> list[RiskAssessment]:
        risks: list[RiskAssessment] = []
        m = phase.metrics
        commits = phase.commits
        pressure = PatternDetector.detect_pressure_signals(commits)
        calibrator = load_calibrator()
        temporal_urgency = pressure.get("temporal_urgency", pressure["burst_pressure"])
        idx = start_id

        # ── Risk: Production Instability ─────────────────────────
        if (
            phase.phase_type in (PhaseType.HOTFIX, PhaseType.BUGFIX)
            and (
                pressure["fix_density"] > 0.5
                or (
                    pressure["fix_density"] >= 0.45
                    and pressure["alternation_score"] >= 0.8
                )
            )
            and (
                pressure["high_frequency"] > 0.3
                or temporal_urgency > calibrator.temporal_hotfix_min()
            )
            and (
                pressure["fix_diversity"] >= 0.5
                or pressure["implicit_fix_density"] >= 0.3
            )
            and pressure["semantic_alignment"] >= 0.6
            and (
                pressure["fix_coherence"] >= 0.35
                or pressure["implicit_fix_density"] >= 0.50
                or pressure["alternation_score"] >= 0.80
            )
            and pressure["impact_weight"] >= 0.75
            and pressure["cleanup_bias"] <= 0.35
            and (
                pressure["reactive_pressure"] >= pressure["proactive_pressure"]
                or (
                    pressure["implicit_fix_density"] >= 0.30
                    and temporal_urgency >= calibrator.temporal_hotfix_high()
                )
                or (
                    pressure["buglike_density"] >= 0.90
                    and pressure["fix_density"] >= 0.70
                    and pressure["high_frequency"] >= 0.80
                    and pressure["cleanup_bias"] <= 0.20
                )
            )
        ):
            level = (
                RiskLevel.CRITICAL
                if pressure["reactive_pressure"] > 0.35
                and (
                    m.commit_frequency_per_day > 5
                    or temporal_urgency > calibrator.temporal_hotfix_high()
                )
                else RiskLevel.HIGH
            )
            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=phase.phase_number,
                    risk_level=level,
                    title="Production Instability Detected",
                    signals=[
                        f"{m.commit_count} commits in {phase.duration_days:.1f} days",
                        f"Fix-related keyword density: {pressure['fix_density']:.0%}",
                        f"Implicit bug density: {pressure['implicit_fix_density']:.0%}",
                        f"Semantic alignment: {pressure['semantic_alignment']:.0%}",
                        f"Fix coherence: {pressure['fix_coherence']:.0%}",
                        f"Impact weight: {pressure['impact_weight']:.0%}",
                        f"Temporal urgency: {temporal_urgency:.0%}",
                        f"Burst pressure (adjusted): {pressure['burst_pressure']:.0%}",
                        f"Burst pressure (raw): {pressure.get('raw_burst_pressure', pressure['burst_pressure']):.0%}",
                        f"Reactive pressure: {pressure['reactive_pressure']:.0%}",
                        f"Proactive pressure: {pressure['proactive_pressure']:.0%}",
                        f"Cleanup bias: {pressure['cleanup_bias']:.0%}",
                        f"Commit frequency: {m.commit_frequency_per_day:.1f}/day",
                        f"Average message length: {m.avg_message_length_words:.1f} words (terse)",
                    ],
                    inference=(
                        "This pattern strongly indicates reactive fixes under "
                        "production pressure. The combination of high frequency, "
                        "high-impact bug handling, and short messages is textbook "
                        "incident response."
                    ),
                    impact=(
                        "Potential instability in production systems. "
                        "Code changes made under this pressure may introduce "
                        "new defects."
                    ),
                    commits_involved=m.commit_count,
                )
            )
            idx += 1

        # ── Risk: Fragile Code (high churn concentration) ────────
        high_churn_files = PatternDetector.files_with_high_churn(
            commits, min_touches=4
        )
        if high_churn_files and (
            m.commit_count >= MIN_CHURN_RISK_COMMITS
            or m.total_churn >= 500
        ):
            top_fragile = high_churn_files[:5]
            file_details = [
                f"`{path}` modified {count} times"
                for path, count in top_fragile
            ]
            max_touches = top_fragile[0][1]
            level = RiskLevel.HIGH if max_touches >= 6 else RiskLevel.MEDIUM

            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=phase.phase_number,
                    risk_level=level,
                    title="Fragile Code — Concentrated File Churn",
                    signals=file_details,
                    inference=(
                        "Repeated modifications to the same files suggest "
                        "either incomplete fixes, evolving requirements, or "
                        "architectural fragility. These files are change magnets."
                    ),
                    impact=(
                        "High regression risk. These files should be "
                        "prioritized for review, testing, and potential "
                        "refactoring."
                    ),
                    commits_involved=sum(c for _, c in top_fragile),
                )
            )
            idx += 1

        # ── Risk: Quality Erosion (high churn, no tests) ─────────
        test_changes = sum(
            1
            for c in commits
            for fc in c.file_changes
            if re.search(
                r"(test_|_test\.|\.test\.|\.spec\.|tests/|__tests__/)",
                fc.path, re.I,
            )
        )
        if m.total_churn > 500 and test_changes == 0:
            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=phase.phase_number,
                    risk_level=RiskLevel.MEDIUM,
                    title="Quality Erosion — No Test Coverage in High-Churn Phase",
                    signals=[
                        f"Total code churn: {m.total_churn} lines",
                        f"Test file changes: 0",
                        f"Phase type: {phase.phase_type.value}",
                    ],
                    inference=(
                        "Significant code changes landed without any "
                        "corresponding test modifications. This increases "
                        "the risk of undetected regressions."
                    ),
                    impact="Potential untested behavior in modified code paths.",
                    commits_involved=m.commit_count,
                )
            )
            idx += 1

        # ── Risk: Bus Factor ────────────────────────────────────
        if m.commit_count >= 10 and m.unique_authors == 1:
            author = PatternDetector.unique_authors(commits)[0]
            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=phase.phase_number,
                    risk_level=RiskLevel.MEDIUM,
                    title="Bus Factor Risk — Single Author Phase",
                    signals=[
                        f"All {m.commit_count} commits by {author}",
                        f"Code churn: {m.total_churn} lines",
                        f"Duration: {phase.duration_days:.0f} days",
                    ],
                    inference=(
                        "One person owns all changes in this phase. "
                        "If this contributor becomes unavailable, knowledge "
                        "of these changes may be lost."
                    ),
                    impact="Knowledge concentration risk. Consider code review or documentation.",
                    commits_involved=m.commit_count,
                )
            )
            idx += 1

        # ── Risk: Fatigue Signal ─────────────────────────────────
        if len(commits) >= 8:
            first_half = commits[: len(commits) // 2]
            second_half = commits[len(commits) // 2 :]
            avg_len_first = PatternDetector.avg_message_length(first_half)
            avg_len_second = PatternDetector.avg_message_length(second_half)

            if avg_len_first > 0 and avg_len_second / max(avg_len_first, 0.1) < 0.5:
                risks.append(
                    RiskAssessment(
                        risk_id=f"RSK-{idx:03d}",
                        phase_number=phase.phase_number,
                        risk_level=RiskLevel.MEDIUM,
                        title="Fatigue Signal — Declining Message Quality",
                        signals=[
                            f"First half avg message: {avg_len_first:.1f} words",
                            f"Second half avg message: {avg_len_second:.1f} words",
                            f"Decline ratio: {avg_len_second / max(avg_len_first, 0.1):.0%}",
                        ],
                        inference=(
                            "Commit message quality dropped significantly "
                            "as the phase progressed. This pattern correlates "
                            "with developer fatigue, time pressure, or "
                            "declining engagement."
                        ),
                        impact="Later commits in this phase may have received less careful attention.",
                        commits_involved=len(second_half),
                    )
                )
                idx += 1

        return risks

    # ── Cross-Phase Assessment ───────────────────────────────────

    def _assess_cross_phase(
        self,
        phases: list[Phase],
        inferences: list[IntentInference],
        start_id: int,
    ) -> list[RiskAssessment]:
        risks: list[RiskAssessment] = []
        idx = start_id

        if len(phases) < 2:
            return risks

        # ── Risk: Feature → Hotfix (quality gap) ─────────────────
        for i in range(len(phases) - 1):
            current = phases[i]
            next_phase = phases[i + 1]
            if (
                current.phase_type == PhaseType.FEATURE
                and next_phase.phase_type in (PhaseType.HOTFIX, PhaseType.BUGFIX)
            ):
                risks.append(
                    RiskAssessment(
                        risk_id=f"RSK-{idx:03d}",
                        phase_number=0,  # cross-phase
                        risk_level=RiskLevel.HIGH,
                        title="Quality Gap — Feature Push Followed by Hotfix",
                        signals=[
                            f"Phase {current.phase_number}: {current.phase_type.value} "
                            f"({current.metrics.commit_count} commits)",
                            f"Phase {next_phase.phase_number}: {next_phase.phase_type.value} "
                            f"({next_phase.metrics.commit_count} commits)",
                            "Immediate transition from feature development to firefighting",
                        ],
                        inference=(
                            "Features shipped in phase "
                            f"{current.phase_number} appear to have "
                            "introduced instability, triggering reactive "
                            f"fixes in phase {next_phase.phase_number}. "
                            "This is a classic ship-then-fix pattern."
                        ),
                        impact="Suggests insufficient testing or review before deployment.",
                        commits_involved=(
                            current.metrics.commit_count
                            + next_phase.metrics.commit_count
                        ),
                    )
                )
                idx += 1

        # ── Risk: No Stabilization Phase in History ──────────────
        phase_types = {p.phase_type for p in phases}
        has_stabilization = phase_types & {
            PhaseType.INFRASTRUCTURE,
            PhaseType.REFACTOR,
        }
        has_feature = PhaseType.FEATURE in phase_types
        if has_feature and not has_stabilization and len(phases) >= 3:
            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=0,
                    risk_level=RiskLevel.LOW,
                    title="No Stabilization Phase Detected",
                    signals=[
                        f"{len(phases)} phases analyzed",
                        "No dedicated refactoring or infrastructure phases found",
                        "Feature development without consolidation",
                    ],
                    inference=(
                        "The repository shows feature development but no "
                        "dedicated stabilization or refactoring effort. "
                        "Technical debt may be accumulating."
                    ),
                    impact="Long-term maintainability concern.",
                    commits_involved=sum(
                        p.metrics.commit_count for p in phases
                    ),
                )
            )
            idx += 1

        # ── Risk: Repo-wide Bus Factor ───────────────────────────
        all_commits = [c for p in phases for c in p.commits]
        all_authors = PatternDetector.unique_authors(all_commits)
        if len(all_authors) == 1 and len(all_commits) >= 20:
            risks.append(
                RiskAssessment(
                    risk_id=f"RSK-{idx:03d}",
                    phase_number=0,
                    risk_level=RiskLevel.HIGH,
                    title="Critical Bus Factor — Entire Repository is Single-Author",
                    signals=[
                        f"All {len(all_commits)} commits by {all_authors[0]}",
                        f"Across {len(phases)} phases",
                        "No other contributors in recorded history",
                    ],
                    inference=(
                        "The entire codebase knowledge is concentrated in "
                        "one person. This is a significant organizational risk."
                    ),
                    impact="Complete knowledge loss if this contributor becomes unavailable.",
                    commits_involved=len(all_commits),
                )
            )
            idx += 1

        return risks
