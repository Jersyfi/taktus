# DEC-0066 — The claim on a run was said to be a fence

**Category:** DEFECT
**Raised in:** [#PR](https://github.com/Jersyfi/taktus/pull/PR), while implementing #73
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

A runner holds its claim on a run's job as a lease: it renews the lease while it works, and a
lease nobody renews expires. Three places said more than that. The runner's description said
"two runners never execute one run". The control plane's architecture said the same. The queue
port said "a claim is never stolen from a live runner".

None of the three holds for a runner that is alive but cannot reach the database for longer
than the lease — a long pause, a network partition. Its lease expires, and another runner
claims the job and recovers the run. When the first runner reaches the database again, its
renewal fails and it stops the run at the next step boundary. Until then, the step it is inside
still runs, and its end is committed. For that one step, two runners write to one run, and the
later write overwrites the earlier one. Nothing checks, when a run is written, that the writer
still holds the claim: the claim is not a *fence*, a check that refuses a write from a holder
who has lost it.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- A runner that dies is not affected: it writes nothing more. That case is the one ADR-0013 A
  names, and `tests/integration/test_runner_failover.py` proves it with two runner processes
  and a SIGKILL.
- The three places now say what holds, and name the missing fence.
- Building the fence is a task of its own, #107 in `0.2.0`: every write of a run under a claim
  checks, in the same transaction, that the claim is still the writer's.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0066" in an issue.

## Outcome

**Corrected:** 2026-10-08
**What was wrong:** the runner, the control plane's architecture and the queue port said that
two runners never execute one run and that a live runner's claim is never taken.
**Why it was wrong:** the sentences described a runner that dies, and were written as if a
runner were either working or dead. A runner can be alive and cut off.
**What it now says:** a live runner cut off for longer than the lease loses its claim; the step
it is inside still commits; the claim is not a fence yet (#107).
**What changed in substance:** nothing in the software; three descriptions, and the task #107.
**Recorded in:** [#PR](https://github.com/Jersyfi/taktus/pull/PR)
