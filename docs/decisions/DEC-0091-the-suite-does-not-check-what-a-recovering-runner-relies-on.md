# DEC-0091 — The suite does not check what a recovering runner relies on

**Category:** DEFECT
**Raised in:** [#140](https://github.com/Jersyfi/taktus/pull/140), for issue #130
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Worker contract v1 says that a worker answers a new assignment whose id it already holds with
`409`, and a question about an id it does not hold with `404` (`contracts/worker/v1/openapi.yaml`).
Since ADR-0038 the run engine relies on both answers. It records an assignment's id before it
posts it. A runner that recovers a run asks the worker about that id: a `404` makes it post the
same id again, and a `409` to that post makes it adopt the assignment another runner handed over.

The conformance suite checks neither answer. A worker that takes a repeated id as a second
assignment passes the suite, and two assignments then run for one step. A gate whose coverage
has a hole that a change meets on the way is a finding, recorded as a `DEFECT` (CLAUDE.md §11,
point 11). `contracts/worker/v1/CONFORMANCE.md` §7 said what a pass covers and named the
capacity answer as checked by W-15; it did not say that these two answers are not.

## 2. Why you are being asked

You are not. The repository would leave a reader believing a pass covers what Taktus relies on,
which is entry M1.4 of `docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- `CONFORMANCE.md` §7 now names the `409` and the `404` as unchecked, and why Taktus relies on
  them.
- ADR-0038 states the same in "Where this promise ends".
- Adding the checks is a task of its own, #138. It adds checks to what v1 already requires and
  changes no requirement.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0091" in an issue.

## Outcome

**Corrected:** 2026-10-09
**What was wrong:** the engine began to rely on the `409` for a repeated assignment id and the `404`
for an unknown one, and nothing checks either; `CONFORMANCE.md` §7 did not say so.
**Why it was wrong:** both answers were lines of the OpenAPI document that nothing relied on until
a runner asked a worker about an assignment another runner handed over.
**What it now says:** the suite does not check these two answers; issue #138 adds the checks.
**What changed in substance:** nothing in the software; one description, ADR-0038's boundary, and
the task #138.
**Recorded in:** [#140](https://github.com/Jersyfi/taktus/pull/140), for issue #130
