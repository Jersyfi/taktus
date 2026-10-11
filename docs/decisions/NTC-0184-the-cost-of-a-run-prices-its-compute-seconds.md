# NTC-0184 — The cost of a run prices its compute seconds

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #230

## 1. What was decided

Until now `taktusctl cost <run>` priced a run's tokens and left its compute seconds out. A
price table can price a second of compute per resource class since #217 (ADR-0084). The same
table therefore gave two answers to "what did this cost": maturation's, with compute, and the
cost command's, without.

The cost of a run now prices both at the one table its budget statement names:

1. **Tokens and compute seconds together.** The amount is the tokens per model and kind plus the
   compute seconds per resource class, each at the table. The report shows the two parts beside
   the total, and `--json` carries them as `tokens_amount` and `compute_amount`.
2. **A resource class the table does not price is named**, as `no price for compute <class>`.
   It is never counted as free.
3. **A table without `compute` gives the amount it gave before.** Where the run used compute
   seconds, the report says that they were not priced and names the table and the classes.
4. **A run held without a price table names that fact** when it used compute seconds, as it did
   when it used tokens.

What changes for an operator: a run with worker steps, priced at a table that prices no compute
or not its class, now exits with code 1, "part of what the run used has no price". It exited 0
before, because compute was not looked at. The amount itself does not change for such a table.

## 2. The evidence

- `tests/components/accounting/test_cost.py`: a run with an `llm` step and a worker step, held
  to a table that prices `cpu.small`, costs its tokens plus its compute seconds as the test
  computes them by hand; a class the table does not price is named and adds nothing; a table
  without `compute` gives the token amount and says compute was not priced; a table given to
  compare prices compute without changing the run's own figure; a run of compute alone held
  without a table names that.
- `tests/integration/test_first_slice.py`: a run of the first slice, held without a table, now
  names that its compute could not be priced.

## 3. What was considered

- **Keep the exit code 0 when only compute is unpriced.** Rejected: ADR-0010's amendment says
  nothing unpriced counts as free. An exit code of 0 says the whole amount is priced, which would
  then be false.
- **Two figures instead of one total.** Rejected: one breakdown at one table gives one amount
  (ADR-0010). The parts are shown beside it, so that nothing is hidden in the sum.
- **Count money a worker reported itself as the compute part.** Rejected: the issue's boundary
  excludes it, and it is the worker's figure, not the table's. It stays printed beside the
  amount, as before.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.4.0` item and issue #230. No contract changes: the price table's
`compute` field exists since #217, and the cost report is no published schema. No limit moves:
admission and the budget statement are untouched, and what a currency budget holds is unchanged
(ADR-0010, second amendment, states the boundary). No level moves.
