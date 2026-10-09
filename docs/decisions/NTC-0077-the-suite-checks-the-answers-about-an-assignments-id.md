# NTC-0077 — The suite checks the answers about an assignment's id

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** pull request for issue #138

## 1. What was decided

The worker conformance suite has two more checks, W-16 and W-17. Both concern an assignment's
id. The run engine records an id before it posts the assignment. A runner that recovers a run
asks the worker about that id, and acts on the answer (ADR-0038).

- **Old:** the suite checked neither answer. A worker that took a repeated id as a second
  assignment passed every check (DEC-0091).
- **New, W-16:** the suite asks for the state of an id it never posted. The worker must answer
  `404` with a problem body, a JSON object with a `title` and `status: 404`.
- **New, W-17:** the suite posts an id the worker already holds, twice. Once it is a fresh
  assignment, posted again while it runs. Once it is `main`, posted again after it finished.
  The worker must answer each repeat with `409` and a problem body. Afterwards the assignment
  of that id must still be the first one: the same `accepted_at`, a `last_seq` no lower than
  before, and a finished state unchanged. The suite then stops every assignment it posted for
  the probe and reads its stream to the end.
- **When W-17 is inconclusive:** the worker turned away the fresh assignment, or `main` did not
  finish. Each case says what to do.
- **W-15 no longer looks up the refused assignment when W-16 failed.** The lookup shows that
  nothing was recorded only where an unknown id is answered `404`. Without that, one fault
  would fail two checks.
- **The rules live with the others** (`rules.unknown_id_violations`,
  `rules.repeated_id_violations`). Their fixtures use two new fixture shapes of the worker
  contract, `UnknownIdProbe` and `RepeatedIdProbe`. Like `Transcript` they are no wire objects
  and change nothing a worker sends or receives.
- **Both reference workers have a fault for each.** `W-16` answers an id never received with
  `200` and an invented state. `W-17` accepts a held id again as a second assignment. The
  meta-tests show the suite failing on exactly that check, for both workers.

## 2. The evidence

- Issue #138 names the verification: a numbered check for the `409` and for the `404`, a fault
  of the reference worker caught by the new check alone, and `CONFORMANCE.md` no longer naming
  these answers as unchecked.
- `contracts/worker/v1/openapi.yaml` has required both answers since v1. ADR-0038 made the
  engine rely on them.
- `make gate-contracts` requires a must-fail fixture for every check. Thirteen fixtures under
  `contracts/worker/v1/examples/unknown-id-probe/` and `repeated-id-probe/` exercise the rules,
  and `tests/conformance/test_worker_v1_fixtures.py` applies the rules to them.
- `make gate-conformance`: the reference worker passes W-16 and W-17 in both profiles, and the
  coding worker in both authentication modes. The faults `W-16` and `W-17` each fail exactly
  their check, in both workers.

## 3. What was considered

- **One check for both answers.** Not taken: a worker can get one right and the other wrong,
  and the report should name which. Two numbers also keep each fault caught by one check.
- **Repeat only a running assignment.** Not taken: the engine may post an id again after the
  first assignment finished, when a runner recovers late. A worker that forgets finished ids
  would start the work again then.
- **Count `step.started` events to see a second assignment that the worker hides.** Not taken:
  a worker that answers `409`, keeps the first state and runs the work again elsewhere shows
  nothing on its endpoints. The suite cannot see it, and `CONFORMANCE.md` §7 and ADR-0038 say
  so.
- **A fault that answers `404` without a problem body.** Not taken as the fault: it would leave
  W-15's lookup passing, but it is not the failure the engine is exposed to. A worker that
  answers `200` for an unknown id makes a recovering runner wait for an assignment that does not
  exist. That fault is the one that matters. Its fixture is kept among the must-fail ones.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The suite now covers the two
answers about an assignment's id. No requirement of the contract changed: both answers were in
v1. `tests/README.md` and `tests/conformance/README.md` say the same.
