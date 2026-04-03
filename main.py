#!/usr/bin/env python3
"""
GitStory — Repository Intelligence Engine
"""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import argparse
from pathlib import Path
from typing import TextIO

from core.models import AnalysisResult
from core.git_parser import GitParser
from skills.deep_history_analysis import DeepHistoryAnalysis
from skills.intent_inference import IntentInferenceEngine
from skills.transition_analysis import TransitionAnalysisEngine
from skills.risk_detection import RiskDetectionEngine
from skills.narrative_engine import NarrativeEngine
from skills.visual_timeline import VisualTimeline


_FALLBACK_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("⚠️", "RISK"),
    ("⚠", "RISK"),
    ("🟢", ""),
    ("🟡", ""),
    ("🔴", ""),
    ("🟠", ""),
    ("🔥", "INTENSE"),
    ("⚡", "FAST"),
    ("█", "#"),
    ("▐", "|"),
    ("▌", "|"),
    ("═", "="),
    ("—", "-"),
    ("–", "-"),
    ("·", "."),
)


_UNICODE_FALLBACK_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u26a0\ufe0f", "RISK"),
    ("\u26a0", "RISK"),
    ("\U0001f7e2", ""),
    ("\U0001f7e1", ""),
    ("\U0001f534", ""),
    ("\U0001f7e0", ""),
    ("\U0001f525", "INTENSE"),
    ("\u26a1", "FAST"),
    ("\u2588", "#"),
    ("\u2590", "|"),
    ("\u258c", "|"),
    ("\u2550", "="),
    ("\u2014", "-"),
    ("\u2013", "-"),
    ("\u00b7", "."),
)


def _ascii_fallback(text: str) -> str:
    """Best-effort transliteration for non-Unicode-friendly terminals."""
    for source, replacement in _UNICODE_FALLBACK_REPLACEMENTS:
        text = text.replace(source, replacement)
    for source, replacement in _FALLBACK_REPLACEMENTS:
        text = text.replace(source, replacement)
    return text


def _safe_for_stream(text: str, stream: TextIO) -> str:
    """Return text that can be encoded by the target stream.

    This keeps Unicode on capable terminals and degrades gracefully on
    encodings like cp1252, which would otherwise crash on emoji risk markers.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return text

    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        fallback = _ascii_fallback(text)
        return fallback.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )


def _build_debug_report(result: AnalysisResult) -> str:
    """Render a phase-by-phase explanation of the pipeline's decisions."""
    inference_map = {inf.phase_number: inf for inf in result.inferences}
    transition_map: dict[int, list] = {}
    for transition in result.transitions:
        transition_map.setdefault(transition.from_phase_number, []).append(
            transition
        )
    risk_map: dict[int, list] = {}
    for risk in result.risks:
        risk_map.setdefault(risk.phase_number, []).append(risk)

    lines: list[str] = []
    lines.append("=== DEBUG: PIPELINE INTELLIGENCE ===")
    lines.append(
        f"repo={result.repo_name} phases={len(result.phases)} "
        f"commits={result.total_commits}"
    )

    for phase in result.phases:
        metrics = phase.metrics
        inference = inference_map.get(phase.phase_number)
        lines.append("")
        lines.append(f"[phase {phase.phase_number}] {phase.phase_type.value}")
        lines.append(
            "  metrics: "
            f"commits={metrics.commit_count}, "
            f"churn=+{metrics.total_additions}/-{metrics.total_deletions}, "
            f"authors={metrics.unique_authors}, "
            f"freq={metrics.commit_frequency_per_day:.1f}/day"
        )
        lines.append(f"  boundary: {phase.boundary_reason}")

        if inference is not None:
            lines.append(
                "  intent: "
                f"{inference.confidence.value} "
                f"({inference.confidence_score:.2f}) "
                f"{inference.intent_summary}"
            )
            if inference.evidence:
                lines.append("  evidence:")
                for evidence in inference.evidence:
                    lines.append(
                        f"    - {evidence.signal}: {evidence.detail}"
                    )
            else:
                lines.append("  evidence: none")
        else:
            lines.append("  intent: none")
            lines.append("  evidence: none")

        phase_transitions = transition_map.get(phase.phase_number, [])
        if phase_transitions:
            lines.append("  transitions:")
            for transition in phase_transitions:
                lines.append(
                    "    - "
                    f"to phase {transition.to_phase_number}: {transition.title} "
                    f"[{transition.confidence.value} "
                    f"{transition.confidence_score:.2f}]"
                )
                lines.append(f"      meaning: {transition.summary}")
                for signal in transition.signals:
                    lines.append(f"      signal: {signal}")
        else:
            lines.append("  transitions: none")

        phase_risks = risk_map.get(phase.phase_number, [])
        if phase_risks:
            lines.append("  risks:")
            for risk in phase_risks:
                lines.append(
                    "    - "
                    f"{risk.risk_id} {risk.risk_level.value}: {risk.title}"
                )
                for signal in risk.signals:
                    lines.append(f"      signal: {signal}")
        else:
            lines.append("  risks: none")

    cross_phase_risks = risk_map.get(0, [])
    if cross_phase_risks:
        lines.append("")
        lines.append("[cross-phase risks]")
        for risk in cross_phase_risks:
            lines.append(
                f"  - {risk.risk_id} {risk.risk_level.value}: {risk.title}"
            )
            for signal in risk.signals:
                lines.append(f"    signal: {signal}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="GitStory — Repository Intelligence Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py /path/to/repo\n"
            "  python main.py /path/to/repo --tone professional\n"
            "  python main.py /path/to/repo --timeline both --output report.md\n"
            # FIX P2: updated to show %aI for timezone-aware parsing
            "  git -C /path/to/repo log --pretty=format:"
            "'%%H|%%an|%%ae|%%at|%%aI|%%s' --numstat | "
            "python main.py --stdin\n"
        ),
    )
    p.add_argument("repo_path", nargs="?", help="Path to a local git repository")
    p.add_argument("--stdin", action="store_true", help="Read git log from stdin")
    p.add_argument("--tone", choices=["story", "professional"], default="story")
    p.add_argument("--timeline", choices=["ascii", "svg", "both"], default="ascii")
    p.add_argument("--max-commits", type=int, default=None)
    p.add_argument("--output", type=str, default=None, help="Write to file")
    p.add_argument("--json", action="store_true", help="Structured JSON output")
    p.add_argument(
        "--debug",
        action="store_true",
        help="Print phase signals, transitions, and risks to stderr",
    )
    return p


def run_pipeline(
    repo_path: str | None,
    stdin_mode: bool,
    tone: str,
    timeline_fmt: str,
    max_commits: int | None,
    output_path: str | None,
    json_mode: bool,
    debug_mode: bool,
) -> int:

    # ── Step 0: Parse ────────────────────────────────────────────
    if stdin_mode:
        raw = sys.stdin.read()
        if not raw.strip():
            print("Error: empty stdin.", file=sys.stderr)
            return 1
        commits = GitParser.from_log_text(raw)
        repo_name = "stdin-repo"
    elif repo_path:
        try:
            git_parser = GitParser(repo_path)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        commits = git_parser.parse(max_commits=max_commits)
        repo_name = git_parser.repo_name
    else:
        print("Error: provide repo_path or --stdin", file=sys.stderr)
        return 1

    if not commits:
        print("Error: no commits found.", file=sys.stderr)
        return 1

    print(f"[gitstory] Parsed {len(commits)} commits from '{repo_name}'", file=sys.stderr)

    # ── Step 1: Deep History Analysis ────────────────────────────
    analysis = DeepHistoryAnalysis(commits=commits)
    analysis.repo_name = repo_name
    phases = analysis.run()

    if not phases:
        print("Error: no phases detected.", file=sys.stderr)
        return 1

    print(f"[gitstory] Detected {len(phases)} development phases", file=sys.stderr)

    # ── Step 2: Intent Inference ─────────────────────────────────
    inference_engine = IntentInferenceEngine()
    inferences = inference_engine.run(phases)

    print(f"[gitstory] Generated {len(inferences)} intent inferences", file=sys.stderr)

    # ── Step 3: Transition Analysis ──────────────────────────────
    transition_engine = TransitionAnalysisEngine()
    transitions = transition_engine.run(phases)

    if transitions:
        print(
            f"[gitstory] Interpreted {len(transitions)} phase transitions",
            file=sys.stderr,
        )

    # ── Step 4: Risk Detection ───────────────────────────────────
    risk_engine = RiskDetectionEngine()
    risks = risk_engine.run(phases, inferences)

    if risks:
        crit = sum(1 for r in risks if r.risk_level.value in ("critical", "high"))
        print(
            f"[gitstory] Identified {len(risks)} risk findings ({crit} critical/high)",
            file=sys.stderr,
        )

    # ── Step 5: Narrative Engine ─────────────────────────────────
    narrative_engine = NarrativeEngine()
    narrative = narrative_engine.run(
        phases,
        inferences,
        repo_name,
        tone,
        risks=risks,
        transitions=transitions,
    )

    # ── Step 6: Visual Timeline ──────────────────────────────────
    tl = VisualTimeline()
    ascii_tl = (
        tl.ascii(phases, risks=risks) if timeline_fmt in ("ascii", "both") else ""
    )
    svg_tl = (
        tl.svg(phases, risks=risks) if timeline_fmt in ("svg", "both") else ""
    )

    # ── Assemble Result ──────────────────────────────────────────
    all_authors = sorted({c.author for p in phases for c in p.commits})

    result = AnalysisResult(
        repo_name=repo_name,
        total_commits=sum(p.metrics.commit_count for p in phases),
        date_range_start=phases[0].start_date,
        date_range_end=phases[-1].end_date,
        unique_authors=all_authors,
        phases=phases,
        inferences=inferences,
        transitions=transitions,
        risks=risks,
        narrative=narrative,
        timeline_ascii=ascii_tl,
        timeline_svg=svg_tl,
    )

    if debug_mode:
        print(
            _safe_for_stream(_build_debug_report(result), sys.stderr),
            file=sys.stderr,
        )

    # ── Output ───────────────────────────────────────────────────
    if json_mode:
        output_text = result.to_json()
    else:
        sections = [narrative]
        if ascii_tl:
            sections.append("\n## Timeline\n\n```\n" + ascii_tl + "\n```\n")
        if svg_tl:
            sections.append("\n## Timeline (SVG)\n\n" + svg_tl + "\n")
        output_text = "\n".join(sections)

    if output_path:
        Path(output_path).write_text(output_text, encoding="utf-8")
        print(f"[gitstory] Output written to {output_path}", file=sys.stderr)
    else:
        print(_safe_for_stream(output_text, sys.stdout))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.repo_path and not args.stdin:
        parser.print_help()
        return 1
    return run_pipeline(
        repo_path=args.repo_path,
        stdin_mode=args.stdin,
        tone=args.tone,
        timeline_fmt=args.timeline,
        max_commits=args.max_commits,
        output_path=args.output,
        json_mode=args.json,
        debug_mode=args.debug,
    )


if __name__ == "__main__":
    raise SystemExit(main())
