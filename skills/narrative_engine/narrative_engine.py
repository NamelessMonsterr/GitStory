"""
Skill 3 (now skill 4 in pipeline): Narrative Engine

Changes in v1.2:
  - Evidence block rendered as structured data in both tones
  - Risk assessments integrated as dedicated section
  - Confidence score shown alongside categorical label
  - Sharper language throughout
"""

from __future__ import annotations

from core.models import (
    Confidence,
    IntentInference,
    Phase,
    PhaseType,
    RiskAssessment,
    RiskLevel,
)


class NarrativeEngine:

    def run(
        self,
        phases: list[Phase],
        inferences: list[IntentInference],
        repo_name: str,
        tone: str = "story",
        risks: list[RiskAssessment] | None = None,
    ) -> str:
        if not phases:
            return f"# {repo_name}\n\nNo phases detected.\n"
        if tone == "professional":
            return self._professional(phases, inferences, repo_name, risks or [])
        return self._story(phases, inferences, repo_name, risks or [])

    # ══════════════════════════════════════════════════════════════
    #  PROFESSIONAL
    # ══════════════════════════════════════════════════════════════

    def _professional(
        self,
        phases: list[Phase],
        inferences: list[IntentInference],
        repo_name: str,
        risks: list[RiskAssessment],
    ) -> str:
        lines: list[str] = []
        inf_map = {i.phase_number: i for i in inferences}

        total_commits = sum(p.metrics.commit_count for p in phases)
        all_authors = sorted({c.author for p in phases for c in p.commits})
        start = phases[0].start_date.strftime("%Y-%m-%d")
        end = phases[-1].end_date.strftime("%Y-%m-%d")
        total_churn = sum(p.metrics.total_churn for p in phases)

        lines.append(f"# Repository Analysis: {repo_name}")
        lines.append("")
        lines.append(f"**Period:** {start} to {end}")
        lines.append(f"**Total Commits:** {total_commits}")
        lines.append(f"**Development Phases:** {len(phases)}")
        lines.append(f"**Contributors:** {len(all_authors)}")
        lines.append(f"**Total Churn:** {total_churn:,} lines")
        if risks:
            crit = sum(1 for r in risks if r.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH))
            lines.append(f"**Risk Findings:** {len(risks)} ({crit} critical/high)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Phase Analysis
        lines.append("## Phase Analysis")
        lines.append("")

        for phase in phases:
            inf = inf_map.get(phase.phase_number)
            m = phase.metrics
            s = phase.start_date.strftime("%Y-%m-%d")
            e = phase.end_date.strftime("%Y-%m-%d")

            lines.append(
                f"### Phase {phase.phase_number}: "
                f"{phase.phase_type.value.replace('_', ' ').title()}"
            )
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Period | {s} to {e} ({phase.duration_days:.1f} days) |")
            lines.append(f"| Commits | {m.commit_count} |")
            lines.append(f"| Churn | +{m.total_additions} / -{m.total_deletions} |")
            if m.file_status_available:
                lines.append(f"| New Files | {m.new_files_added} (git status=A) |")
            else:
                lines.append(f"| New Files | unavailable (stdin) |")
            lines.append(f"| Authors | {m.unique_authors} |")
            lines.append(f"| Frequency | {m.commit_frequency_per_day:.1f} commits/day |")
            lines.append(f"| Avg Message | {m.avg_message_length_words:.1f} words |")
            lines.append("")

            if inf:
                badge = _conf_badge(inf.confidence)
                lines.append(
                    f"**Intent** ({badge}, score: {inf.confidence_score:.2f}):"
                )
                lines.append(f"> {inf.intent_summary}")
                lines.append("")

                if inf.evidence:
                    lines.append("**Evidence:**")
                    for ev in inf.evidence:
                        lines.append(
                            f"- **{ev.signal}** — {ev.detail} "
                            f"({ev.commits_involved} commits)"
                        )
                    lines.append("")

            lines.append("---")
            lines.append("")

        # Risk Section
        if risks:
            lines.extend(self._render_risks(risks))

        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════
    #  STORY
    # ══════════════════════════════════════════════════════════════

    def _story(
        self,
        phases: list[Phase],
        inferences: list[IntentInference],
        repo_name: str,
        risks: list[RiskAssessment],
    ) -> str:
        lines: list[str] = []
        inf_map = {i.phase_number: i for i in inferences}

        total_commits = sum(p.metrics.commit_count for p in phases)
        all_authors = sorted({c.author for p in phases for c in p.commits})
        start = phases[0].start_date.strftime("%B %d, %Y")
        end = phases[-1].end_date.strftime("%B %d, %Y")
        total_churn = sum(p.metrics.total_churn for p in phases)

        lines.append(f"# The Story of `{repo_name}`")
        lines.append("")
        lines.append(
            f"*{total_commits} commits. "
            f"{len(all_authors)} contributor(s). "
            f"{total_churn:,} lines of churn. "
            f"From {start} to {end}.*"
        )
        lines.append("")

        if len(phases) == 1:
            lines.append(
                "One phase. One story. Either this project is brand new, "
                "or someone is remarkably consistent."
            )
        elif len(phases) <= 3:
            lines.append(
                f"This repository has lived {len(phases)} lives. "
                "Each one left marks in the commit log."
            )
        else:
            lines.append(
                f"This repository has been through {len(phases)} distinct "
                "phases. It's seen ambition, panic, cleanup, and everything "
                "between. Here's the record."
            )
        lines.append("")
        lines.append("---")
        lines.append("")

        for phase in phases:
            inf = inf_map.get(phase.phase_number)
            m = phase.metrics
            s = phase.start_date.strftime("%B %d")
            e = phase.end_date.strftime("%B %d, %Y")

            title = _chapter_title(phase)
            lines.append(f"## Chapter {phase.phase_number}: {title}")
            lines.append(
                f"*{s} — {e} · "
                f"{m.commit_count} commits · "
                f"{phase.duration_days:.0f} days · "
                f"{m.commit_frequency_per_day:.1f}/day*"
            )
            lines.append("")

            if inf:
                lines.append(inf.observation)
                lines.append("")
                lines.append(inf.intent_summary)
                lines.append("")

                conf_text = _conf_text(inf.confidence)
                lines.append(
                    f"*{conf_text} (score: {inf.confidence_score:.2f}).*"
                )
                lines.append("")

                if inf.reasoning:
                    lines.append("**What I'm seeing:**")
                    for r in inf.reasoning:
                        lines.append(f"- {r}")
                    lines.append("")

            if m.files_most_changed:
                top = m.files_most_changed[:3]
                lines.append(f"The action centered on: `{'`, `'.join(top)}`")
                lines.append("")

            # Inline phase risks
            phase_risks = [
                r for r in risks if r.phase_number == phase.phase_number
            ]
            if phase_risks:
                for risk in phase_risks:
                    marker = _risk_marker(risk.risk_level)
                    lines.append(f"> {marker} **{risk.title}**")
                    lines.append(f"> {risk.inference}")
                    lines.append("")

            lines.append("---")
            lines.append("")

        # Cross-phase risks
        cross_risks = [r for r in risks if r.phase_number == 0]
        if cross_risks:
            lines.append("## ⚠️ Cross-Phase Risk Findings")
            lines.append("")
            for risk in cross_risks:
                marker = _risk_marker(risk.risk_level)
                lines.append(f"### {marker} {risk.title}")
                lines.append("")
                for sig in risk.signals:
                    lines.append(f"- {sig}")
                lines.append("")
                lines.append(f"**Inference:** {risk.inference}")
                lines.append("")
                lines.append(f"**Impact:** {risk.impact}")
                lines.append("")
                lines.append("---")
                lines.append("")

        # Closing
        lines.append("## The Big Picture")
        lines.append("")
        lines.append(_closing_remarks(phases, inferences, risks))
        lines.append("")

        return "\n".join(lines)

    # ── Risk Rendering (professional) ────────────────────────────

    @staticmethod
    def _render_risks(risks: list[RiskAssessment]) -> list[str]:
        lines: list[str] = []
        lines.append("## Risk Assessment")
        lines.append("")

        for risk in risks:
            marker = _risk_marker(risk.risk_level)
            scope = (
                f"Phase {risk.phase_number}"
                if risk.phase_number > 0
                else "Cross-Phase"
            )
            lines.append(f"### {marker} {risk.risk_id}: {risk.title}")
            lines.append("")
            lines.append(f"**Scope:** {scope} · **Commits:** {risk.commits_involved}")
            lines.append("")
            lines.append("**Signals:**")
            for sig in risk.signals:
                lines.append(f"- {sig}")
            lines.append("")
            lines.append(f"**Inference:** {risk.inference}")
            lines.append("")
            lines.append(f"**Impact:** {risk.impact}")
            lines.append("")
            lines.append("---")
            lines.append("")

        return lines


# ── Module-level Helpers ─────────────────────────────────────────

def _conf_badge(conf: Confidence) -> str:
    return {
        Confidence.HIGH: "🟢 HIGH",
        Confidence.MEDIUM: "🟡 MEDIUM",
        Confidence.LOW: "🔴 LOW",
    }[conf]


def _conf_text(conf: Confidence) -> str:
    return {
        Confidence.HIGH: "The signals are clear. I'm confident about this one",
        Confidence.MEDIUM: "Two corroborating signals. Reasonably sure, not certain",
        Confidence.LOW: "Weak signal — take this as informed speculation, not fact",
    }[conf]


def _chapter_title(phase: Phase) -> str:
    return {
        PhaseType.INITIAL: "Genesis",
        PhaseType.FEATURE: "Building",
        PhaseType.BUGFIX: "Patching the Cracks",
        PhaseType.REFACTOR: "Cleaning House",
        PhaseType.INFRASTRUCTURE: "Laying Pipes",
        PhaseType.DOCUMENTATION: "Writing It Down",
        PhaseType.HOTFIX: "Fire Fighting",
        PhaseType.MIXED: "A Bit of Everything",
    }.get(phase.phase_type, "Uncharted Territory")


def _risk_marker(level: RiskLevel) -> str:
    return {
        RiskLevel.CRITICAL: "🔴",
        RiskLevel.HIGH: "🟠",
        RiskLevel.MEDIUM: "🟡",
        RiskLevel.LOW: "🔵",
        RiskLevel.NONE: "⚪",
    }[level]


def _closing_remarks(
    phases: list[Phase],
    inferences: list[IntentInference],
    risks: list[RiskAssessment],
) -> str:
    n = len(phases)
    high_conf = sum(1 for i in inferences if i.confidence == Confidence.HIGH)
    hotfix_n = sum(1 for p in phases if p.phase_type == PhaseType.HOTFIX)
    feature_n = sum(1 for p in phases if p.phase_type == PhaseType.FEATURE)
    refactor_n = sum(1 for p in phases if p.phase_type == PhaseType.REFACTOR)
    total_adds = sum(p.metrics.total_additions for p in phases)
    total_dels = sum(p.metrics.total_deletions for p in phases)
    crit_risks = sum(
        1 for r in risks if r.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
    )

    parts: list[str] = []

    if feature_n > n / 2:
        parts.append(
            "This codebase is growth-oriented — most of its history is "
            "about building new things, not maintaining old ones."
        )
    elif hotfix_n > n / 3:
        parts.append(
            "A lot of this repository's life has been reactive — "
            "fixing things that broke. That's not necessarily bad, "
            "it means the project is used enough to break."
        )

    if refactor_n >= 1:
        parts.append(
            "At least one phase was dedicated to refactoring. "
            "That takes discipline — most teams skip this."
        )

    if total_dels > total_adds * 0.8:
        parts.append(
            "This repo deletes almost as much as it adds. Someone "
            "fights code bloat. Respect."
        )

    if crit_risks > 0:
        parts.append(
            f"⚠️ {crit_risks} critical/high risk finding(s) detected — "
            f"these deserve attention."
        )

    if high_conf >= n / 2:
        parts.append(
            f"{high_conf}/{n} phases have high-confidence readings. "
            f"The commit patterns tell a clear story."
        )

    if not parts:
        parts.append(
            "Steady, incremental development. No drama in the commit log "
            "— just consistent work getting done."
        )

    return " ".join(parts)
