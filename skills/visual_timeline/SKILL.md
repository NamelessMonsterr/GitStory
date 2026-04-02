
# Skill: visual-timeline

## Purpose

Generate visual timelines of repository evolution. Two output formats:

1. **ASCII** — terminal-friendly, zero dependencies, works everywhere
2. **SVG** — clean vector graphic for reports, READMEs, and presentations

## Inputs

| Input  | Type          | Description            |
|--------|---------------|------------------------|
| phases | `list[Phase]` | From deep-history-analysis |

## Outputs

| Method   | Returns | Description                          |
|----------|---------|--------------------------------------|
| `.ascii()`| `str`  | ASCII timeline with proportional bars|
| `.svg()`  | `str`  | SVG markup with colored bars + legend|

## ASCII Format