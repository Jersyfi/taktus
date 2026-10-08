# NTC-0025 — A margin below the floor is said

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-08
**Raised in:** the pull request that closes [#72](https://github.com/Jersyfi/taktus/issues/72)

## 1. What was decided

The uncalibrated margin is what a worker without calibration history reserves beyond its
estimate. An operator sets it with `TAKTUS_BUDGET_UNCALIBRATED_MARGIN`. Observations never narrow
it below a floor of 0.1. An operator's own value below the floor holds (DEC-0047).

- **Old:** a value below the floor held silently. Only the startup log's list of settings showed
  it, among fifty others.
- **New:** a value below the floor is said in three places.
  - The startup log carries a warning naming the value and the floor.
  - Every run records the uncalibrated margin, the floor and, where the margin is below it, a
    sentence saying so, in its budget statement. The ledger's `budget.set` entry names that
    statement by its digest.
  - `taktusctl cost <run>` prints that sentence beside the run's money, and `--json` carries it.
- At or above the floor nothing is said. The floor, the default of 1.0 and the narrowing are
  unchanged.

## 2. The evidence

- DEC-0047, the owner's answer of 2026-10-07: "When such a value is set, Taktus says so where it
  is set and in every report that relies on it."
- `anchors.taktus.md` M3.10 states the same.
- The tests, each with a margin of 0, of 0.05 and of 0.1:
  `tests/composition/test_settings.py` (the warning),
  `tests/components/run/test_estimates.py` (the budget statement),
  `tests/components/accounting/test_cost.py` (the cost, rendered and as JSON).

## 3. What was considered

- **Saying it only at startup.** Rejected: a run's report outlives the process that started it,
  and DEC-0047 names every report that relies on the value.
- **Recording the margin only when it is below the floor.** Rejected: a statement that always
  names the margin and the floor lets a reader check the claim, not only trust it.
- **A ledger entry of its own.** Rejected: the budget statement is already the one document that
  says what a run was held to, and `taktusctl cost` already reads it.

## 4. Which entry permits it

M2.4, "a change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public". The scope is DEC-0047's answer. The
budget statement is not a contract, and no limit moves: the value an operator set still holds.
Moving it would be M3.10.
