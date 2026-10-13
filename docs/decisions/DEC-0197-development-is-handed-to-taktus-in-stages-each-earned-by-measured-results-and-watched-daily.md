# DEC-0197 — Development is handed to Taktus in stages, each earned by measured results, and watched daily

**Category:** NON-BLOCKING
**Mode entry:** M3.10 (what Taktus may take on its own, and at what cost); M4 for the direction
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-13, after a second session's report on the instance's runs of the same day; recorded in the pull request of its own that records the answers
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-13
**Written after the answer:** the owner answered in conversation on 2026-10-13; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Since 2026-10-12 the installed instance runs P-03 on every issue labelled `ready`. On 2026-10-13
it started 22 P-03 runs. One became a merged pull request (#387, for #280). Nine were refused by
P-03's own admission — blocked or not ready. Four ended on the coding agent's limit of turns,
three on the agent asking for a web page its frame forbids, two on a unit that did not start or
an assignment still held. One ended on a red pipeline, and one opened #415 for the task another
session had just done (#414). The failed runs left their claims behind (DEC-0196 removed 41),
and their work was lost.

A single run that finishes is cheap: USD 1.26 for the coding step of #373. Little progress per
dollar comes from runs that fail and tasks Taktus should not have taken.

The owner's direction: hand development to Taktus step by step, check after each step what
went right and what did not, and give it ever larger tasks — milestones, up to several
milestones towards a release — learning from every failure.

## 2. Why you are being asked

What Taktus may take on its own, and what it may spend doing so, is a limit (M3.10); the
direction of the project is the owner's (M4).

**Sources checked:** the vision — principle 10 (the whole autonomy range, with guardrails) and
principle 8 (cost control); `docs/roadmap.md`, *The handover path* (S1 to S4) and #87; ADR-0026
and ADR-0039 (autonomy levels and maturity per step); DEC-0051 (the backlog and the standing
brief). They describe levels per process and step, not how far the project hands its own
development over, nor by which measures.

## 3. What you must decide

Whether the development of Taktus is handed to the instance in stages with measured criteria,
whether P-03 pauses until the first stage is built, and how its progress is watched.

## 4. What you need to know to decide

**The stages proposed.** Each is entered when the one before it met its criteria, measured over
its window; a stage whose measures fall below them steps back one stage, and the cause becomes
an issue.

| Stage | Taktus is given | Measured before the next stage |
|---|---|---|
| 0 | single small tasks, handed over explicitly | 10 handed tasks; at least 80 % merged without rework; the money per merged pull request below an agreed figure |
| 1 | fixes and findings it met itself; P-02 makes issues ready | the same, over two weeks |
| 2 | larger tasks with a drafted ADR; every decision stays with the owner | the same rate; no decision taken past its anchor |
| 3 | a whole milestone, in the order P-01 computes | #87's two weeks, S2 of the roadmap |
| 4 | several milestones towards a release | S4; deployment stays with a person or another instance (ADR-0013 D) |

**Stage 0's mechanics** are a second session's proposal, recorded and built by it: P-03 takes
only issues handed to Taktus explicitly (a label); sessions leave those alone; Taktus comments
with a link to its run when it takes one; a failed run gives its claim back; tasks that need an
ADR or wait for a decision are not handed over, and P-03's admission refuses them.

**Watching.** A routine in Claude, independent of Taktus, reads once a day what the instance
did: runs and the causes of failures, money per run and per day, issues taken, pull requests
opened and merged, stale claims, and the measures of the current stage. It writes a page that it
updates on every run and a short message into the owner's chat channel, and warns when a day's
money passes USD 5 or several runs fail in a row. It reads only; any act stays with the owner or
a session. Taktus's own reports in the owner's channel come beside it, not instead of it: the
system that errs is not the only one that reports on itself.

## 5. Options

### Option A — stages, a pause until stage 0 is built, a daily routine (recommended)

- **Meaning:** as §4; P-03's trigger is switched off now and on again with stage 0.
- **Why recommended:** every stage is earned by numbers, and a failure becomes an issue instead
  of a loss.

### Option B — Taktus takes every ready task, watched daily

- **Meaning:** no stages; the routine alone.
- **Consequence:** the runs of 2026-10-13 go on.

## 6. What is blocked

Taktus's work on its own instance, while P-03 is paused.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-13
**Answer:** Option A. To the three questions — stage 0 by the other session and the stages and
watching by this one, P-03 paused now, the routine once a day with a warning from USD 5 a day —
the owner answered "Yes to all three, pause P-03 now." (the owner's words, translated). The
owner had asked before for a daily routine and said a chat channel with messages suits him.
**Reasoning given:** the owner's: hand development over piece by piece, so that what went right
and what did not can always be checked, and learn from every failure to reach the vision
sustainably.
**What it changes:** P-03's trigger was switched off on the instance on 2026-10-13
(`taktusctl deactivate --process p03-implementation`). It is switched on again with stage 0.
The figures of §4 hold until the owner changes them; the money per merged pull request is
proposed with the first measurements. The daily routine is set up in Claude.
**What it does not change:** merging stays a person's. P-01 and P-02 keep running.
**Recorded in:** this pull request
