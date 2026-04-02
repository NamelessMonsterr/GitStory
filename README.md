# GitStory - Repository Intelligence Engine

> Most developers read commits.
> GitStory reconstructs intent.

GitStory analyzes repository history to detect development phases, infer
developer intent, surface risk patterns, and turn raw commits into a
narrative you can actually read.

**Core claim:** GitStory reconstructs developer intent from raw commit data
without AI, using deterministic reasoning over commit timing, churn, file
status, keywords, and change concentration.

No LLM API needed. No cloud dependency. Just a local CLI that turns `git log`
into evidence-backed analysis.

---

## Why It Matters

Raw commit history tells you what changed.

GitStory tries to answer the harder questions:

- Was this a planned feature push or reactive firefighting?
- Did the team slow down to pay technical debt, or just stop shipping?
- Are the same files being hit repeatedly because they are fragile?
- Did a feature phase immediately collapse into hotfixes?

That is the difference between activity reporting and repository intelligence.

---

## What You Get

| Raw Input | GitStory Output |
|-----------|-----------------|
| `git log` | **Phases** - feature, bugfix, refactor, hotfix, infrastructure |
| messy commits | **Intent** - "this isn't planned work, it's damage control" |
| unreadable diffs | **Risk** - instability, fatigue, bus-factor, fragile-file signals |
| wall of hashes | **Narrative** - what happened, why, and what it likely means |
| raw history | **Timeline** - ASCII/SVG with density markers and risk alerts |
| automation pipelines | **JSON** - structured output for downstream tooling |

---

## Quick Start

```bash
cd gitstory
pip install -r requirements.txt

# Analyze a local repository
python main.py /path/to/repo

# Professional report
python main.py /path/to/repo --tone professional

# JSON output
python main.py /path/to/repo --json

# ASCII + SVG timeline in one report
python main.py /path/to/repo --timeline both --output report.md

# Sample very large histories
python main.py /path/to/repo --max-commits 500

# Analyze from piped git log instead of direct repo access
git -C /path/to/repo log --pretty=format:'%H|%an|%ae|%at|%aI|%s' --numstat \
  | python main.py --stdin
```

---

## What Makes It Credible

GitStory does not just label a phase. It tries to show:

1. **What happened**
2. **Why it thinks that**
3. **What it likely means**

Example of the style it aims for:

```text
Phase: Bugfix Spike

Why:
- 12 commits in 1.8 hours
- 71% fix-related keywords
- short commit messages
- repeated edits in auth and error-handling files

Conclusion:
Likely reactive stabilization under pressure after a broken release
or production issue.
```

That combination of evidence + interpretation is the whole point.

---

## Detection Logic

GitStory is deterministic. The engine combines signals like timing, churn,
keywords, file types, file status, and author distribution to infer likely
development intent.

| Pattern | Signal | Meaning |
|---------|--------|---------|
| High commit frequency | dense commits over short span | urgency / deadline pressure |
| Short messages | many commits with <= 3 words | reactive work / lower documentation quality |
| Fix-heavy vocabulary | `fix`, `bug`, `patch`, `hotfix` | bugfix or incident response |
| High deletions | deletion-heavy phase | refactor or cleanup |
| True new files | `git status=A` | actual build-out, not guessed growth |
| Test / CI concentration | test files, CI files, infra changes | stabilization / hardening |
| Repeated same-file edits | high touch count on few files | fragility / regression risk |
| Single-author dominance | one person owns most work | bus-factor / knowledge concentration |
| Feature phase followed by hotfix phase | adjacent phase transition | quality gap after shipping |

### Phase Boundaries

Phases are split using:

- large time gaps between commits
- vocabulary shifts between commit windows
- change-pattern shifts across adjacent clusters

---

## Why Not Just GitHub Insights?

| GitHub Insights | GitStory |
|----------------|----------|
| Shows activity graphs | Explains why activity happened |
| Counts commits per week | Detects pressure, fatigue, instability |
| Lists contributors | Identifies bus-factor risk |
| Pretty charts | Produces evidence-backed interpretation |

GitHub tells you **what happened**.
GitStory tries to tell you **what it means**.

---

## Example Outputs

- [Sample Narrative](examples/sample_output.md) - polished multi-phase story output
- [Linux Kernel Style Demo](examples/demo_linux_kernel.md) - representative high-scale demo
- [GitStory Analyzing Itself](examples/self_analysis.md) - a real report generated from this repository

These are useful when you want to understand the output before running the CLI.

---

## GitStory Analyzing Itself

GitStory has been run against its own repository history. That gives you a
real, not hypothetical, example of the pipeline working on an active project.

- See the report: [examples/self_analysis.md](examples/self_analysis.md)
- Regenerate it locally: `python main.py . --tone story --timeline ascii --output examples/self_analysis.md`

---

## Edge Cases and Limits

GitStory handles a few important edge cases explicitly:

- **stdin mode without name-status data:** new-file counts are marked unavailable instead of guessed
- **author timezone unknown:** late-night pressure signals are marked unavailable rather than fabricated
- **commit subjects containing `|` in stdin mode:** supported by format detection in the parser
- **empty input / no commits:** CLI returns a clear error instead of pretending analysis happened
- **large repositories:** `--max-commits` lets you sample history when full analysis would be noisy

Current limits:

- It is heuristic, not omniscient
- It infers likely intent, not ground truth
- Accuracy is strongest when commit messages and file history contain usable signal

---

## CLI Output Modes

- `--tone story` for readable narrative output
- `--tone professional` for structured analysis
- `--json` for machine-readable output
- `--timeline ascii|svg|both` for visual summaries

---

## Architecture

```text
Raw Git History
  -> deep_history_analysis
  -> intent_inference
  -> risk_detection
  -> narrative_engine
  -> visual_timeline
```

### Pipeline Responsibilities

- `deep_history_analysis` groups commits into phases and computes metrics
- `intent_inference` turns signals into likely explanations
- `risk_detection` flags instability, fragility, fatigue, and quality gaps
- `narrative_engine` turns analysis into readable reporting
- `visual_timeline` renders ASCII/SVG timelines with risk markers

---

## Positioning

GitStory is not a commit visualizer.

It is a repository reasoning tool:

- deterministic rather than generative
- explainable rather than opaque
- useful for maintainers, reviewers, tech leads, and hackathon judges who
  need to understand not just code change volume, but development behavior

---

## Requirements

- Python 3.9+
- Git CLI available on `PATH`
- Local repository access or piped `git log` input

---

## License

MIT
