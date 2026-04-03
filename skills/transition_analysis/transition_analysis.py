"""
Skill: Transition Analysis
Interprets adjacent phase changes and explains what the shift likely means.
"""

from __future__ import annotations

from core.models import Confidence, Phase, PhaseType, TransitionInsight


class TransitionAnalysisEngine:
    """Derives meaning from adjacent phase transitions."""

    def run(
        self,
        phases: list[Phase],
        _inferences: object | None = None,
    ) -> list[TransitionInsight]:
        if len(phases) < 2:
            return []

        transitions: list[TransitionInsight] = []
        for left, right in zip(phases, phases[1:]):
            insight = self._analyze_pair(left, right)
            if insight is not None:
                transitions.append(insight)
        return transitions

    def _analyze_pair(
        self, left: Phase, right: Phase
    ) -> TransitionInsight | None:
        pattern = self._match_pattern(left.phase_type, right.phase_type)
        if pattern is None:
            return None

        title, summary, impact, base_score = pattern
        signals = self._build_signals(left, right)
        signal_bonus = min(len(signals) * 0.04, 0.16)
        confidence_score = min(base_score + signal_bonus, 0.95)
        confidence = self._categorize_confidence(confidence_score)

        return TransitionInsight(
            from_phase_number=left.phase_number,
            to_phase_number=right.phase_number,
            title=title,
            summary=summary,
            signals=signals,
            confidence=confidence,
            confidence_score=round(confidence_score, 2),
            impact=impact,
        )

    @staticmethod
    def _match_pattern(
        left: PhaseType, right: PhaseType
    ) -> tuple[str, str, str, float] | None:
        if left == PhaseType.INITIAL and right == PhaseType.FEATURE:
            return (
                "Scaffolding Gave Way to Build-Out",
                "The repository moved from setup work into active feature delivery. "
                "This usually marks the point where initial scaffolding turned into "
                "real product construction.",
                "A clear transition from foundation work into forward delivery.",
                0.76,
            )
        if left == PhaseType.FEATURE and right in (PhaseType.BUGFIX, PhaseType.HOTFIX):
            return (
                "Feature Push Gave Way to Firefighting",
                "A feature-heavy phase was immediately followed by reactive fixes. "
                "That likely means the rollout introduced instability or exposed "
                "edge cases after new functionality landed.",
                "Suggests a quality gap between shipping and stabilization.",
                0.8,
            )
        if left == PhaseType.FEATURE and right in (
            PhaseType.REFACTOR,
            PhaseType.INFRASTRUCTURE,
        ):
            return (
                "Growth Shifted Into Consolidation",
                "After a build-out phase, the team pivoted into cleanup and "
                "stabilization work. That usually means rapid expansion created "
                "enough complexity to justify consolidation.",
                "Likely technical debt payoff after rapid delivery.",
                0.78,
            )
        if left in (PhaseType.BUGFIX, PhaseType.HOTFIX) and right in (
            PhaseType.REFACTOR,
            PhaseType.INFRASTRUCTURE,
        ):
            return (
                "Firefighting Settled Into Stabilization",
                "Reactive fixes were followed by structural cleanup or infrastructure "
                "work. That usually means the team moved from immediate pressure into "
                "preventing the next incident.",
                "A healthy sign that the team addressed root causes after pressure.",
                0.77,
            )
        if left == PhaseType.FEATURE and right == PhaseType.DOCUMENTATION:
            return (
                "Build-Out Shifted Into Hand-Off",
                "Feature work was followed by documentation activity. That often "
                "signals release preparation, onboarding support, or a deliberate "
                "attempt to make new functionality easier to adopt.",
                "The team likely started packaging knowledge after shipping work.",
                0.7,
            )
        return None

    def _build_signals(self, left: Phase, right: Phase) -> list[str]:
        signals = [
            (
                "Phase types changed from "
                f"{left.phase_type.value.replace('_', ' ')} to "
                f"{right.phase_type.value.replace('_', ' ')}"
            )
        ]

        left_freq = left.metrics.commit_frequency_per_day
        right_freq = right.metrics.commit_frequency_per_day
        if left_freq > 0 and right_freq > 0:
            ratio = right_freq / left_freq
            if ratio >= 1.35:
                signals.append(
                    f"Commit pace accelerated from {left_freq:.1f}/day to {right_freq:.1f}/day"
                )
            elif ratio <= 0.75:
                signals.append(
                    f"Commit pace cooled from {left_freq:.1f}/day to {right_freq:.1f}/day"
                )

        left_profile = self._churn_profile(left)
        right_profile = self._churn_profile(right)
        if left_profile != right_profile:
            signals.append(
                f"Churn profile shifted from {left_profile} to {right_profile}"
            )

        if left.metrics.unique_authors != right.metrics.unique_authors:
            signals.append(
                "Contributor count changed from "
                f"{left.metrics.unique_authors} to {right.metrics.unique_authors}"
            )

        if right.phase_type in (PhaseType.BUGFIX, PhaseType.HOTFIX):
            if (
                right.metrics.avg_message_length_words
                < left.metrics.avg_message_length_words
            ):
                signals.append(
                    "Commit messages became terser during the fix-heavy phase"
                )

        return signals

    @staticmethod
    def _churn_profile(phase: Phase) -> str:
        adds = phase.metrics.total_additions
        dels = phase.metrics.total_deletions
        if dels > adds * 1.2:
            return "deletion-heavy"
        if adds > max(dels, 1) * 1.5:
            return "growth-heavy"
        return "balanced"

    @staticmethod
    def _categorize_confidence(score: float) -> Confidence:
        if score >= 0.8:
            return Confidence.HIGH
        if score >= 0.65:
            return Confidence.MEDIUM
        return Confidence.LOW
