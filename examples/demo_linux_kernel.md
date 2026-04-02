# Demo: Linux-Kernel-Style History

> This is a representative demo, not a claim that GitStory was run on the
> Linux kernel itself. The commit patterns below are modeled after the kind of
> long-lived, high-churn, multi-maintainer history you see in large systems
> codebases.

---

## Repository Snapshot

**Repository:** `kernel-network-stack`
**Style:** systems code, long maintenance tail, frequent stabilization bursts
**Period:** January 2023 to March 2024
**Shape:** feature work, bug-fix clusters, cleanup passes, and subsystem handoffs

GitStory is strongest when history is messy but meaningful. This demo is built
to show that it can still extract signal from the kind of repo where changes
arrive in bursts, authors overlap, and maintenance work is as important as new
features.

---

## Phase 1: Foundation
*Jan 2023 - Mar 2023*

**Snapshot:** 18 commits, 2 contributors, 1,240 lines of churn, 9 new files

This phase reads like subsystem scaffolding. The commit stream is small but
deliberate, with high file creation and broad setup activity. GitStory would
classify this as early infrastructure work rather than feature delivery.

**Why it matters**
- The repo is being assembled around stable interfaces.
- New files dominate, so the history looks like bootstrapping, not churn.
- Confidence is high because the message vocabulary and file changes align.

**Interpretation**
This is the kind of phase that says, "the project is becoming real."

---

## Phase 2: Feature Ramp
*Apr 2023 - Aug 2023*

**Snapshot:** 73 commits, 4 contributors, 8,960 lines of churn, 21 new files

The signal here is classic growth: higher commit volume, positive net addition,
and a wider spread of touched source files. GitStory would frame this as a
feature-heavy expansion cycle with a clear subsystem focus.

**Evidence**
- Commit frequency rises sharply.
- Net additions stay strongly positive.
- Several commits reuse the same core paths, which suggests an active feature
  branch rather than random maintenance.

**Interpretation**
The codebase is extending capability, not just polishing existing behavior.

---

## Phase 3: Stabilization and Firefighting
*Sep 2023 - Nov 2023*

**Snapshot:** 41 commits, 5 contributors, 2,110 lines of churn, 0 new files

This is the most telling phase in the demo. Short messages, fix-heavy wording,
and concentrated edits on a small set of files would push GitStory toward a
hotfix or bug-fix reading. The lack of new files is important: the work is not
expansion, it is stabilization.

**Evidence**
- High density of fix-oriented commits.
- Repeated edits on the same paths.
- Message tone shifts from implementation to repair.

**Interpretation**
This looks like production pressure, the kind of maintenance burst that large
systems projects eventually hit.

---

## Phase 4: Cleanup and Hardening
*Dec 2023 - Mar 2024*

**Snapshot:** 26 commits, 3 contributors, 5,310 lines of churn, 14 files heavily revised

The last phase reads like deliberate consolidation. Deletions rise, refactors
become more visible, and the tone changes from "ship it" to "make it last."
GitStory would likely call this a refactor or debt-paydown phase with a strong
stabilization undertone.

**Evidence**
- Repeated churn on a small group of core files.
- Refactor language appears in the commit history.
- Net change is smaller than the total churn, which points to cleanup rather
  than growth.

**Interpretation**
This is the maintenance phase that keeps the project viable over time.

---

## Risk Findings

### Quality Gap
- A feature-heavy phase is followed by a repair-heavy phase.
- That pattern suggests a release that shipped faster than the surrounding
  tests or review process could support.
- In a real systems repo, this is the kind of thing that deserves attention.

### Concentrated Churn
- A handful of paths absorb repeated edits across multiple phases.
- That raises the chance of fragile code and makes future changes more costly.

### Bus Factor Pressure
- Several key phases are dominated by only a few contributors.
- That is normal in subsystem history, but it still creates knowledge risk.

---

## Why This Demo Matters

This example shows the point of GitStory: it does not just label commits, it
turns long, noisy history into a readable story about intent, pressure, and
stability. That matters most in repositories like kernel-style systems code,
where the important signal is rarely in one commit. It is in the pattern.

If a reviewer can read this demo and immediately see how the tool distinguishes
foundation, growth, firefighting, and cleanup, the project is doing its job.
