"""
Skill 5 (now pipeline position 5): Visual Timeline
Now accepts risk data for inline markers.
"""

from __future__ import annotations

from core.models import Phase, PhaseType, RiskAssessment, RiskLevel

_PHASE_COLORS: dict[PhaseType, str] = {
    PhaseType.FEATURE: "#4A90D9",
    PhaseType.BUGFIX: "#D94A4A",
    PhaseType.HOTFIX: "#D94A4A",
    PhaseType.REFACTOR: "#D9A84A",
    PhaseType.INFRASTRUCTURE: "#4AD97A",
    PhaseType.DOCUMENTATION: "#9B59B6",
    PhaseType.INITIAL: "#95A5A6",
    PhaseType.MIXED: "#BDC3C7",
}

_PHASE_LABELS: dict[PhaseType, str] = {
    PhaseType.FEATURE: "feature",
    PhaseType.BUGFIX: "bugfix",
    PhaseType.HOTFIX: "hotfix",
    PhaseType.REFACTOR: "refactor",
    PhaseType.INFRASTRUCTURE: "infra",
    PhaseType.DOCUMENTATION: "docs",
    PhaseType.INITIAL: "init",
    PhaseType.MIXED: "mixed",
}


def _density_marker(cpd: float) -> str:
    if cpd >= 8:
        return " 🔥"
    if cpd >= 5:
        return " ⚡"
    if cpd >= 2:
        return ""
    return " ·"


def _risk_icon(phase_number: int, risks: list[RiskAssessment]) -> str:
    phase_risks = [r for r in risks if r.phase_number == phase_number]
    if not phase_risks:
        return ""

    severity_order = {
        RiskLevel.CRITICAL: 0,
        RiskLevel.HIGH: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.LOW: 3,
        RiskLevel.NONE: 4,
    }
    worst = min(phase_risks, key=lambda r: severity_order[r.risk_level])

    if worst.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
        return " ⚠️"
    if worst.risk_level == RiskLevel.MEDIUM:
        return " ⚡"
    return ""


class VisualTimeline:
    def ascii(
        self,
        phases: list[Phase],
        risks: list[RiskAssessment] | None = None,
        max_bar_width: int = 35,
    ) -> str:
        if not phases:
            return "(no phases to display)"

        risks = risks or []
        max_commits = max(p.metrics.commit_count for p in phases)
        lines: list[str] = []
        sep = "═" * 78

        lines.append("Repository Timeline")
        lines.append(sep)
        lines.append("")

        for phase in phases:
            commits = phase.metrics.commit_count
            bar_len = max(int((commits / max(max_commits, 1)) * max_bar_width), 1)
            bar = "█" * bar_len

            start_s = phase.start_date.strftime("%b %d")
            end_s = phase.end_date.strftime("%b %d")
            label = _PHASE_LABELS.get(phase.phase_type, "???")
            cpd = phase.metrics.commit_frequency_per_day
            density = _density_marker(cpd)
            risk = _risk_icon(phase.phase_number, risks)

            lines.append(
                f"  Phase {phase.phase_number:<2} "
                f"▐{bar}▌ "
                f"{start_s} — {end_s}  "
                f"{label} ({commits} commits, {cpd:.1f}/day)"
                f"{density}{risk}"
            )

        lines.append("")
        lines.append(
            "  · = low activity  ⚡ = high pace  🔥 = intense  ⚠️  = risk detected"
        )
        lines.append(sep)
        return "\n".join(lines)

    def svg(
        self,
        phases: list[Phase],
        risks: list[RiskAssessment] | None = None,
        width: int = 820,
        row_height: int = 52,
        padding: int = 20,
    ) -> str:
        if not phases:
            return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

        risks = risks or []
        legend_h = 35
        height = padding * 2 + len(phases) * row_height + 44 + legend_h
        max_commits = max(p.metrics.commit_count for p in phases)
        bar_area = width - padding * 2 - 260

        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" '
            f'font-family="Consolas,Monaco,monospace" font-size="13">'
        )
        parts.append(
            f'  <rect width="{width}" height="{height}" fill="#1a1a2e" rx="8"/>'
        )
        parts.append(
            f'  <text x="{padding}" y="{padding + 16}" '
            f'fill="#e0e0e0" font-size="16" font-weight="bold">'
            f"Repository Timeline</text>"
        )

        y = padding + 42

        for phase in phases:
            count = phase.metrics.commit_count
            bar_w = max(int((count / max(max_commits, 1)) * bar_area), 6)
            color = _PHASE_COLORS.get(phase.phase_type, "#BDC3C7")
            label = _PHASE_LABELS.get(phase.phase_type, "???")
            start = phase.start_date.strftime("%b %d")
            end = phase.end_date.strftime("%b %d")
            cpd = phase.metrics.commit_frequency_per_day
            risk_icon = _risk_icon(phase.phase_number, risks)

            parts.append(
                f'  <text x="{padding}" y="{y + 20}" fill="#c0c0c0">'
                f"Phase {phase.phase_number}</text>"
            )

            bar_x = padding + 75
            phase_risks = [r for r in risks if r.phase_number == phase.phase_number]
            has_critical = any(
                r.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
                for r in phase_risks
            )
            if has_critical:
                parts.append(
                    f'  <rect x="{bar_x - 2}" y="{y + 3}" '
                    f'width="{bar_w + 4}" height="26" '
                    f'fill="none" stroke="#ff4444" stroke-width="2" rx="4"/>'
                )

            parts.append(
                f'  <rect x="{bar_x}" y="{y + 5}" '
                f'width="{bar_w}" height="22" '
                f'fill="{color}" rx="3" opacity="0.85"/>'
            )

            if bar_w > 35:
                parts.append(
                    f'  <text x="{bar_x + 6}" y="{y + 21}" '
                    f'fill="#fff" font-size="11">{count}</text>'
                )

            info_x = bar_x + bar_w + 10
            parts.append(
                f'  <text x="{info_x}" y="{y + 20}" '
                f'fill="#a0a0a0" font-size="11">'
                f"{start} – {end} · {label} · {cpd:.1f}/day{risk_icon}</text>"
            )

            y += row_height

        legend_y = y + 12
        items = [
            ("feature", "#4A90D9"),
            ("bugfix", "#D94A4A"),
            ("refactor", "#D9A84A"),
            ("infra", "#4AD97A"),
            ("docs", "#9B59B6"),
            ("mixed", "#BDC3C7"),
        ]
        legend_x = padding
        for label, color in items:
            parts.append(
                f'  <rect x="{legend_x}" y="{legend_y}" '
                f'width="10" height="10" fill="{color}" rx="2"/>'
            )
            parts.append(
                f'  <text x="{legend_x + 14}" y="{legend_y + 9}" '
                f'fill="#808080" font-size="10">{label}</text>'
            )
            legend_x += 90

        parts.append("</svg>")
        return "\n".join(parts)
