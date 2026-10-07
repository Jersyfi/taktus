# DEC-0047 — DEC-0043's floor keeps its outcome and loses its reason

**Category:** NON-BLOCKING
**Raised in:** the description of [#52](https://github.com/Jersyfi/taktus/pull/52), which stated two readings of DEC-0043 as built; recorded in PRNUM
**Issue:** none; the owner answered in the brief of 2026-10-07 before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-07
**Written after the answer:** the owner answered in the brief of 2026-10-07; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

A budget reserves, for every step, its estimate plus a safety margin. DEC-0043 decided that the
margin narrows with every observation of a worker but never below 10 %, and that a worker's
history starts again when its model changes. Building that, the session read two points into the
answer and stated them in the pull request that built it, without asking.

- **The floor and an explicit setting.** An operator can configure the margin a worker without
  history starts from. The session read: observations never narrow the margin below 10 %, but an
  operator who sets the starting margin itself below 10 % keeps that lower value. It gave two
  reasons. A configured value is a limit, and a limit is the owner's or the operator's decision.
  And otherwise the engine's tests, which set the margin to zero, would have had to change.
- **What counts as a model change.** The session read: the model version is the one the step's
  estimate names, else the one the worker last reported, and an observation that names no model
  is no evidence of a change.

## 2. Why you are being asked

A safety margin is a limit, and raising or lowering a limit is the owner's (M3.10 of
`anchors.taktus.md`). DEC-0043 is the owner's answer; a reading of it is the owner's to confirm.

## 3. What you must decide

Whether the two readings hold, and whether their reasons do.

## 4. What you need to know to decide

- **The rule the second reason invoked.** A use case is never changed in the pull request that
  implements it (CLAUDE.md §9). The engine's tests are named by a use case. The session took
  editing them as touching the use case.
- **What a configured value means.** It is set once, by whoever operates the instance, and every
  later reservation depends on it.

## 5. Options

### Option A — the outcome stands, the reason is replaced, the reset confirmed (recommended)

- **Meaning:** observations never narrow the margin below 10 %. An operator who explicitly sets a
  lower value keeps it, because a limit is the operator's decision (M3.10). When such a value is
  set, Taktus says so where it is set and in every report that relies on it. The second reason is
  withdrawn. The reading of the model reset is confirmed as written.
- **Consequence:** a lower margin is possible and never silent. A test that configures its own
  margin stays ordinary work.
- **Effort:** the record's correction now; the statement where the value is set and in the reports
  is a task of `0.2.0`.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — the floor binds an explicit setting too

- **Meaning:** no configuration can go below 10 %.
- **Consequence:** an operator's limit is overruled by the product, against M3.10.
- **Effort:** the settings check and the tests that set zero.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0047: Option A." or "DEC-0047: Option B."

## Outcome

**Decided:** 2026-10-07
**Answer:** Option A, as the owner gave it. The 10 % floor governs automatic narrowing. An
operator who explicitly sets a lower value keeps it, because a limit is the operator's decision
(M3.10). When such a value is set, Taktus says so where it is set and in every report that relies
on it. The reading of the model reset is confirmed as written.
**Reasoning given:** "Otherwise the engine tests would need editing" is not a reason, and it rests
on a misreading. The rule that a use case is never changed in the pull request that implements it
protects what a use case requires — not the files that implement or test it. A test that
configures its own margin is ordinary work.
**Recorded in:** PRNUM: DEC-0043's outcome carries the corrected reason; CLAUDE.md §9 states what
the use-case rule protects; `anchors.taktus.md` M3.10 names the statement; the statement itself is
the backlog issue BACKLOG_MARGIN, milestone `0.2.0`.
