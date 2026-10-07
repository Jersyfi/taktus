# DEC-0046 — The coding worker's suite promised a live test it does not have

**Category:** DEFECT
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52), while raising the coding agent key for CI (NEED-0012)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The description at the top of the coding worker's conformance suite,
`tests/conformance/test_worker_v1_coding.py`, said since 2026-09-18: "The real agent is
exercised by the live test at the end, which runs only when `TAKTUS_CODING_AGENT_LIVE` names the
credential file to use." There is no such test, at the end or anywhere, and the variable is read
by nothing. A reader who trusted the sentence would believe the real agent is checked whenever
someone sets a variable. It is checked only by a live run with `tools/first_run.sh`.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The description now says that the suite runs against the stand-in only, and that the live
  test is written when CI has a key of its own for the agent (NEED-0012).
- The status file and the roadmap already said that a live run of the coding worker in CI does
  not exist; they were right, and the suite's description was the one place that said otherwise.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0046" in an issue.

## Outcome

**Corrected:** 2026-10-01
**What was wrong:** the suite's description named a live test against the real agent and a
variable that switches it on; neither exists.
**Why it was wrong:** the test was planned with the execution layer and not written; the
description was written for the plan.
**What it now says:** the suite runs the worker against the stand-in only; a live test is written
when CI has the agent's key (NEED-0012).
**What changed in substance:** nothing; the description of a test file.
**Recorded in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
