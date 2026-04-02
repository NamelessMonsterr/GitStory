
# Skill: deep-history-analysis

## Purpose

Parse raw git history and produce structured, classified development phases.
This is the foundation layer — every other skill depends on its output.

## What It Does

1. **Parses** git log into `Commit` objects with file-change metadata.
2. **Classifies** each commit (feature, bugfix, refactor, infrastructure,
   documentation) using keyword + file-path heuristics.
3. **Detects phase boundaries** using:
   - Time gaps (>3× median commit interval, minimum 24h)
   - Vocabulary shift between sliding commit windows
   - File-pattern change detection
4. **Assigns a phase type** based on the dominant commit classification
   within each phase (>40% dominance required, else "mixed").
5. **Computes per-phase metrics:**
   - commit count, additions, deletions, total churn
   - average commit interval (hours)
   - average message length (words)
   - most-changed files (top 5)
   - dominant file extensions (top 3)
   - unique author count
   - commits per day
6. **Post-processes** to detect hotfix sprints (high fix-density + high frequency)
   and initial setup phases (≤5 commits at start).

## Inputs

| Input       | Type              | Required |
|-------------|-------------------|----------|
| `repo_path` | `str`             | One of   |
| `commits`   | `list[Commit]`    | these    |

## Outputs

| Output  | Type          | Description                        |
|---------|---------------|------------------------------------|
| phases  | `list[Phase]` | Chronological development phases   |

Each `Phase` contains its raw commits for downstream skill consumption.

## Phase Boundary Rules

Boundaries are placed where:
1. A time gap exceeds 3× the median inter-commit interval (floor: 24h)
2. If fewer than 2 boundaries found AND >20 commits exist, vocabulary
   shift analysis runs on sliding 10-commit windows (threshold: >0.6)

Each boundary includes a human-readable justification string.