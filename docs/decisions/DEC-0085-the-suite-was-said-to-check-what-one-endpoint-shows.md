# DEC-0085 — The suite was said to check what one endpoint shows

**Category:** DEFECT
**Raised in:** the pull request for issue #122
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

A worker declares how many assignments it holds at once. Worker contract v1 says that a worker
holding that many answers a further assignment with `503` (`contracts/worker/v1/openapi.yaml`).
Since ADR-0037 the run engine relies on that answer: a step whose worker answers `503` waits,
and no runner counts a worker's assignments itself.

The conformance suite does not check the answer. No numbered check covers it. Yet
`contracts/worker/v1/CONFORMANCE.md` §7 said that a worker passing the suite "satisfies the
contract as far as a suite talking to one endpoint can tell". The capacity answer is something
a suite talking to one endpoint can tell: it holds as many assignments as the worker declares
and posts one more. So a worker that takes more than it declares passed the suite, and the page
said it satisfied the contract.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- `CONFORMANCE.md` §7 now names the capacity answer as the one obligation the suite could check
  from one endpoint and does not.
- ADR-0037 states the same in "Where this promise ends".
- Adding the check is a task of its own, #133: a numbered check, a fault of the reference
  worker that breaks it, and the plain-words row. It adds a check to what v1 already requires
  and changes no requirement.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0085" in an issue.

## Outcome

**Corrected:** 2026-10-09
**What was wrong:** `CONFORMANCE.md` §7 said a pass meant the contract was satisfied as far as one
endpoint can tell, and one obligation that one endpoint shows — the `503` at capacity — was
checked by nothing.
**Why it was wrong:** the capacity answer was never more than a line of the OpenAPI document;
nothing relied on it until a step waited on it.
**What it now says:** the suite does not check the capacity answer; issue #133 adds the check.
**What changed in substance:** nothing in the software; one description, ADR-0037's boundary, and
the task #133.
**Recorded in:** the pull request for issue #122
