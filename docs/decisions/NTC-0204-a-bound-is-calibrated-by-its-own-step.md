# NTC-0204 — A bound is calibrated by its own step

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-13
**Raised in:** the pull request for issue #370

## 1. What was decided

ADR-0005, amended a fifth time on 2026-10-13, is the decision; this notice records the change
of behaviour.

1. **A step that is not a worker step is scaled only by its own history.** Each observation
   carries `<process>/<step>`, taken from the ledger entry's process version and step. When
   such a step is admitted, the factors come from the observations of the same step through
   the same adapter; without any, the estimate is taken as given.
2. **A worker step is unchanged.**

## 2. The evidence

- 2026-10-13, the installed instance, `run_fd221e54dff23b6ad891`, P-03 for #278: the coding
  step succeeded; `create-branch` estimated 64 quota units and was reserved 192, three times
  the estimate, and refused: "192.0 quota units needed, 191.0 left". Its only earlier
  observation, `run_0fe0ff759342c538f0fd`, had used 14 of 64. The factor of three came from
  another operation of the same connector.
- `tests/components/run/test_budget.py`
  `test_a_bound_is_calibrated_by_its_own_step_not_by_its_adapter`, and the run component's
  tests (435 passed).

## 3. What was considered

- **Per adapter and operation.** The ledger names the step, not the operation; the operation
  would have to be looked up in the process version of every observation. Per step is what
  the ledger already says, and a step calls one operation. Not taken.
- **Raising P-03's quota.** A limit is the owner's (M3.10), and it would have hidden a wrong
  reservation instead of correcting it. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #370. No contract changes; no limit or margin moves: a worker is
calibrated as before, and a bound is still scaled by its own measured error. The amendment of
ADR-0005 is M1.9.
