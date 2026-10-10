# NTC-0141 — The `api` role serves the origin of a result

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#192](https://github.com/Jersyfi/taktus/issues/192), in the pull request that closes it

## 1. What was decided

The fourth level of UC-6.10, the origin of a result, is built as ADR-0068 decides. What the
software does differently:

- The `api` role serves `GET /levels/origins/{run_id}/{step_id}` with an account key. It answers
  with the step's result and the path back to what produced it: each step on the path, across
  runs, with its method kind, exactness class, model and adapter where recorded, and when it was
  recorded, and each external source read, with when it was read. The path is drawn from the
  provenance records and nothing else.
- A step that produced no result, one without a record, and one whose run the reader may not see
  are all answered `404`. A step on the path whose run the reader may not see is absent, and the
  path ends there.
- The visual vocabulary draws a result (a seal, marked by its exactness class), a source (a page)
  and a decision request (a flag, one form per status). None of them moves.
- The run level carries each step's decision requests with their status from the decision
  component, and links each completed step's result to its origin.
- The web app draws the origin at `#/origins/<run>/<step>`. Its graph names a node apart from its
  identifier.

The tokens of the three new forms were chosen by the session, as NTC-0127 chose the first ones,
inside the distinctions UC-6.10 requires: an outline of their own, `exact` marked as on a step, and
no motion. NTC-0127's proposed entry M1.20 covers them.

## 2. The evidence

- Issue #192, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §1 and §2;
  ADR-0021; ADR-0059; ADR-0068; DEC-0055.
- `tests/integration/test_every_level.py`: a process registered on a daemon, a run started and its
  steps completed with a result. With one key, the overview, the process graph, the run and the
  origin of the result are found.
- `tests/components/reporting/test_origin_level.py`, `test_vocabulary_origin_forms.py`, the
  decision request test in `test_run_level.py`, `tests/adapters/rest/test_origin_level.py`,
  `web/src/lib/origin.test.ts`.

## 3. What was considered

- **The origin of an artifact instead of a step's result.** Rejected: a result without an
  artifact would have none (ADR-0068).
- **A placeholder for a withheld step.** Rejected: UC-6.10 says it is absent.
- **The origin page following the stream.** Rejected: a record never changes.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #192
under UC-6.10, accepted in DEC-0055, and ADR-0068. No contract under `contracts/` changes;
`api/openapi.yaml` is regenerated. No limit or level moves.
