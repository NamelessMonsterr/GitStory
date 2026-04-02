# Skill: intent-inference

## Purpose

Core differentiator. Structured reasoning over phase data to infer
WHY changes happened — not just WHAT changed.

## Reasoning Framework

Every inference follows this strict chain:

1. **Observation** — raw metrics
2. **Pattern** — what the metrics imply in context
3. **Inference** — the "why" conclusion
4. **Confidence** — HIGH / MEDIUM / LOW

## Signal Catalogue

| Signal            | Detection Method                                   |
|-------------------|----------------------------------------------------|
| urgency_pressure  | Short msgs + high freq + local-time late-night + fix keywords |
| feature_push      | Feature keywords + truly new files (status=A) + net growth |
| tech_debt_payoff  | Refactor keywords + deletions > additions          |
| stabilization     | Test file additions + CI config changes            |
| documentation_push| Doc keyword density + markdown file dominance      |
| team_change       | New unique authors + documentation overlap         |

## Key Fixes (v1.1)

- **INITIAL phases are checked FIRST** in synthesis — they can no longer
  be overridden by feature/urgency heuristics.
- **"New files introduced"** now uses git name-status (`A` flag) instead
  of counting any addition-only diff as a new file.
- **Late-night detection** uses the author's local timezone offset. When
  timezone is unknown, `late_night_ratio` is 0 (no fabrication).

## Confidence Rules

| Level  | Rule                                     |
|--------|------------------------------------------|
| HIGH   | 3+ active signals with clear evidence    |
| MEDIUM | 2 active signals                         |
| LOW    | 0–1 signals — explicitly labeled speculative |