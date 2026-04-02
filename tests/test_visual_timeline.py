"""
Tests for visual_timeline - ASCII and SVG generation.
"""

from __future__ import annotations

from core.models import PhaseType, RiskAssessment, RiskLevel
from skills.visual_timeline import VisualTimeline


class TestAsciiTimeline:
    def test_generates_output(self, make_phase):
        phases = [make_phase()]
        result = VisualTimeline().ascii(phases)
        assert "Repository Timeline" in result
        assert "Phase 1" in result

    def test_multiple_phases(self, make_phase):
        phases = [
            make_phase(phase_number=1, phase_type=PhaseType.FEATURE),
            make_phase(phase_number=2, phase_type=PhaseType.BUGFIX),
        ]
        result = VisualTimeline().ascii(phases)
        assert "Phase 1" in result
        assert "Phase 2" in result

    def test_contains_bar_characters(self, make_phase):
        result = VisualTimeline().ascii([make_phase()])
        assert "\u2588" in result
        assert "\u2590" in result

    def test_empty_phases(self):
        result = VisualTimeline().ascii([])
        assert "no phases" in result

    def test_legend_present(self, make_phase):
        result = VisualTimeline().ascii([make_phase()])
        assert "low activity" in result

    def test_risk_markers(self, make_phase):
        phase = make_phase(phase_type=PhaseType.HOTFIX, commit_frequency_per_day=6.0)
        risk = RiskAssessment(
            risk_id="RSK-001",
            phase_number=1,
            risk_level=RiskLevel.CRITICAL,
            title="Test",
            commits_involved=5,
        )
        result = VisualTimeline().ascii([phase], risks=[risk])
        assert "\u26a0\ufe0f" in result

    def test_density_markers(self, make_phase):
        phase = make_phase(commit_frequency_per_day=9.0)
        result = VisualTimeline().ascii([phase])
        assert "\U0001f525" in result

    def test_low_activity_marker(self, make_phase):
        phase = make_phase(commit_frequency_per_day=0.5)
        result = VisualTimeline().ascii([phase])
        assert "\u00b7" in result

    def test_commit_count_shown(self, make_phase):
        phase = make_phase(commit_count=10)
        result = VisualTimeline().ascii([phase])
        assert "10 commits" in result


class TestSvgTimeline:
    def test_generates_valid_svg(self, make_phase):
        result = VisualTimeline().svg([make_phase()])
        assert result.startswith("<svg")
        assert result.strip().endswith("</svg>")

    def test_contains_phase_data(self, make_phase):
        result = VisualTimeline().svg([make_phase()])
        assert "Phase 1" in result

    def test_empty_phases(self):
        result = VisualTimeline().svg([])
        assert "<svg" in result
        assert "</svg>" in result

    def test_multiple_phases(self, make_phase):
        phases = [
            make_phase(phase_number=1),
            make_phase(phase_number=2),
        ]
        result = VisualTimeline().svg(phases)
        assert "Phase 1" in result
        assert "Phase 2" in result

    def test_contains_colors(self, make_phase):
        result = VisualTimeline().svg([make_phase(phase_type=PhaseType.FEATURE)])
        assert "#4A90D9" in result

    def test_risk_border_for_critical(self, make_phase):
        phase = make_phase(phase_type=PhaseType.HOTFIX)
        risk = RiskAssessment(
            risk_id="RSK-001",
            phase_number=1,
            risk_level=RiskLevel.CRITICAL,
            title="Test",
            commits_involved=5,
        )
        result = VisualTimeline().svg([phase], risks=[risk])
        assert "#ff4444" in result

    def test_legend_present(self, make_phase):
        result = VisualTimeline().svg([make_phase()])
        assert "feature" in result
        assert "bugfix" in result
