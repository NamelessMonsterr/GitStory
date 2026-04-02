
# RULES — GitStory Operating Constraints

These rules are non-negotiable. Every skill, every output, every inference
must comply.

---

## Rule 1: No Hallucinated Intent

**NEVER claim developer intent without commit evidence.**

- Every inference MUST cite specific commits, date ranges, or file patterns.
- If the data is ambiguous, say so explicitly.
- Speculation is allowed ONLY when clearly labeled as speculation and
  supported by at least two corroborating signals.

**Violation example:**
> "The team was clearly frustrated during this period."

**Correct form:**
> "Commit messages shortened from avg 12 words to 3 words between March 5-9,
> and commit frequency tripled. This pattern is consistent with urgent
> pressure — though it could also indicate a hackathon or sprint push."

---

## Rule 2: Reasoning Before Conclusions

**ALWAYS show the reasoning chain before stating a conclusion.**

Structure:
1. **Observation** — what the data shows
2. **Pattern** — what recurring signal exists
3. **Inference** — what this likely means
4. **Confidence** — how certain you are (high/medium/low)

Never skip straight to inference.

---

## Rule 3: Patterns Over Anecdotes

**Prefer patterns over individual commits.**

- A single commit that says "urgent fix" means little.
- Twelve commits in 4 hours all touching the same error handler means a lot.
- Always aggregate before interpreting.

---

## Rule 4: Dual Output Format

**Every analysis MUST produce BOTH:**

1. **Structured data** — JSON-compatible phases, metrics, classifications
2. **Narrative** — human-readable explanation

Neither is optional. The structured data proves rigor. The narrative proves
understanding.

---

## Rule 5: Phase Boundaries Must Be Justified

**When grouping commits into phases, state WHY the boundary exists.**

Valid boundary reasons:
- Significant gap in commit timestamps (>3x average interval)
- Abrupt change in file-change patterns
- Shift in commit message vocabulary
- Introduction or removal of key files (CI configs, test suites, new modules)

Invalid: arbitrary date splits, equal-sized chunks.

---

## Rule 6: Confidence Labeling

Every intent inference must carry a confidence level:

| Level  | Meaning                                      |
|--------|----------------------------------------------|
| HIGH   | 3+ corroborating signals, clear pattern      |
| MEDIUM | 2 signals, plausible but not certain          |
| LOW    | 1 signal, speculative, clearly marked as such |

---

## Rule 7: No Filler

- No "In conclusion..."
- No "It's worth noting that..."
- No padding. Every sentence must carry information.

---

## Rule 8: Respect the Repository

- Never mock code quality without evidence.
- Never assume team size, skill level, or organizational context
  unless inferable from the data.
- Treat every repository as someone's real work.