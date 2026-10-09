# NTC-0075 — The suite checks the capacity answer

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#139](https://github.com/Jersyfi/taktus/pull/139), for issue #133

## 1. What was decided

The worker conformance suite has a fifteenth check, W-15. A worker declares how many
assignments it holds at once (`max_concurrent_assignments`). W-15 checks what it answers when
it holds that many.

- **Old:** the suite never ran two assignments at once. A worker that accepted more assignments
  than it declared passed every check (DEC-0085).
- **New:** after the seven assignments it runs one after the other, the suite posts as many
  assignments as the worker declares and then one more. The worker must answer the one more
  with `503` and a problem body, a JSON object with a `title` and `status: 503`. It must record
  nothing of it: looking the assignment up answers `404`. Afterwards the suite stops every
  assignment it posted for the probe and reads its stream to the end.
- **When it fails:** the worker accepts the one more while every held assignment is still
  unfinished. A finished state never changes back, so those assignments were all held when the
  worker accepted. Any answer but `503` fails too, and so do a `503` without a problem body and
  a `503` after which the assignment can be looked up.
- **When it is inconclusive:** a held assignment finished before the places were filled or
  before the answer, so the worker may have had a free place; the worker turned away or
  finished an assignment of the probe before its places were full; or it declares more than
  sixteen places, the most the suite fills. Each case says what to do.
- **The rule lives with the stream rules** (`rules.capacity_violations`). Its fixtures use a
  new fixture shape of the worker contract, `CapacityProbe`. Like `Transcript` it is no wire
  object and changes nothing a worker sends or receives.
- **Both reference workers have a fault `W-15`** that accepts beyond their capacity. The
  meta-tests show the suite failing on W-15 and on no other check, for both.

## 2. The evidence

- Issue #133 names the verification: a numbered check, a fault of the reference worker caught
  by it alone, the plain-words row in `CONFORMANCE.md`, and an inconclusive report with what to
  do for a capacity too large to fill.
- `contracts/worker/v1/openapi.yaml` has required the `503` since v1, and ADR-0037 makes the
  run engine rely on it.
- `make gate-contracts` requires a must-fail fixture for every check. Seven fixtures under
  `contracts/worker/v1/examples/capacity-probe/` exercise the rule.
  `tests/conformance/test_worker_v1_fixtures.py` applies the rule to them.
- `make gate-conformance`: the reference worker passes W-15 in both profiles, holding its four
  places; the coding worker passes it in both authentication modes, holding its two; the fault
  `W-15` fails exactly W-15 in both workers; a suite that fills fewer places than the worker
  declares reports W-15 inconclusive.

## 3. What was considered

- **Post the probe's assignments at the same moment.** Not taken: it would test how a worker
  handles a race between two requests, which the contract does not specify. Posting one after
  the other fills the places just as well.
- **Fail a worker that answers `503` before its declared places are full.** Not taken: an
  assignment the suite did not post, from another client, takes a place too. The suite cannot
  tell that apart from a worker that declares too much, so it reports inconclusive.
- **No upper bound on the places the suite fills.** Not taken: a worker that declares a
  thousand places would have the suite start a thousand assignments. Sixteen fills both
  reference workers four times over. A worker with more places is started with fewer for the
  run, which the report says.
- **Leave the fixture out and exempt W-15 from the fixture gate.** Not taken: every other check
  has a must-fail fixture, and a rule without one is pinned by nothing but the live suite.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The suite now covers the
capacity answer. No requirement of the contract changed: the `503` was already in v1.
`tests/README.md` and `tests/conformance/README.md` say the same.
