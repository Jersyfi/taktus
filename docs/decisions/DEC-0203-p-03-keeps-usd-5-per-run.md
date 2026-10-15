# DEC-0203 — P-03 keeps USD 5 per run

**Category:** NON-BLOCKING
**Mode entry:** M3.10 (a limit)
**Raised in:** #455, which builds DEC-0202's limit the coding worker halts at during the run
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-15
**Written after the answer:** the owner answered in conversation on 2026-10-15; left out of the acceptance rate (DEC-0042).

## 1. What this is about

#455 makes the coding worker halt at its money limit during the run (DEC-0202). It proposed to
lower P-03's limit from USD 5 to USD 4: twice the dearest finished coding step on the instance
(USD 1.78), rounded up.

## 2. Why you are being asked

A limit is the owner's (M3.10).

**Sources checked:** DEC-0202, DEC-0193, ADR-0005; none sets the figure.

## 3. What you must decide

USD 4 or USD 5 per P-03 run.

## 4. What you need to know to decide

No coding step that finished on the instance cost more than USD 1.78; the run for #277 spent
about USD 10 before the limit could hold.

## 5. Options

### Option A — USD 4 (recommended)

### Option B — USD 5, as today

## 6. What is blocked

Merging #455 and switching P-03 on again.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-15
**Answer:** Option B. "Bleib bei 5$." (the owner's words: stay at USD 5).
**Reasoning given:** none.
**What it changes:** P-03's version 10 in #455 keeps `currency: usd 5.0`; the worker now halts
at it during the run. The owner left the command to resume a halted run with a raised limit to
the session ("go on"); it becomes an issue.
**Recorded in:** this pull request
