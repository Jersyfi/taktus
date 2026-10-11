# NTC-0188 — A currency budget holds the money of compute

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #232

## 1. What was decided

Until now a currency budget held what workers estimate and report in that currency, and the
priced estimate of an `llm` step. A worker that reports compute seconds and no money was
admitted as if its compute cost nothing. The run's price table can price a second of compute
per resource class (ADR-0084), and the cost of a run counts that money (#230). A run with worker
steps could therefore cost more at its table than its currency budget held it to, while its
budget statement said the currency was held.

A currency budget now holds the money of compute (ADR-0005, fourth amendment):

1. **Held at the table.** Where the table prices compute in a currency the budget limits,
   admission prices a step's reserved compute seconds, and what the run used and reserved, at
   the table. A step whose money does not fit what remains is rejected, and the run halts with
   cause `limit`. The money is derived each time and never stored on the step.
2. **The worker halts on its seconds.** Where compute money is held, the worker's `limits` carry
   a compute ceiling even where the budget sets none: its reservation, and never more than the
   seconds the money left would buy.
3. **Unpriced compute is refused.** Under a currency budget, a step that estimates compute
   seconds is refused with `no_estimate` when no table is configured, when the table prices no
   compute, when it prices in a currency the budget does not limit, or when it does not price the
   step's class. So is a step that needs money while compute the run already used has no price.
4. **The statement says it.** `budget.set` of a run with a currency budget and a worker step
   carries a promise of kind `compute_money`: `held`, with the table and its classes, or
   `unpriced`, with the reason and that such a step is refused.

What changes for an operator: a run with a currency budget and a worker that reports compute —
the script worker, the ML bench — now needs a price table that prices that worker's resource
class. Without one, the worker step is refused before it starts. A run whose currency budget did
not cover its compute at the table now halts with cause `limit` where it ran on before. The coding
workers report no compute seconds and are not affected.

## 2. The evidence

- `tests/components/run/test_estimates.py`: of 1.50 usd, two worker steps of 4 s at 0.25 usd a
  second each reserve 1.00 usd; the first runs with a ceiling of 4 s, and the second is rejected,
  "1.0 usd needed, 0.5 left". At 2.00 usd both run. A table that prices only another class, a
  table without `compute` and no table each refuse the step with `no_estimate`, and the worker is
  never handed it. The statement says `held` or `unpriced`, with the reason, for each.
- `tests/components/run/test_budget.py`: the promise for every table, the money added per class
  and an unpriced class named, and the ceiling bought with the money left.
- `tests/components/accounting/test_cost.py`: three tests of #230 that need a run which used
  unpriced compute now hold it to a budget in compute seconds alone, because a currency budget
  would refuse that compute.

## 3. What was considered

- **State that compute money is not held, and admit the step.** Rejected: ADR-0005's second
  amendment says a limit is a limit, and ADR-0010 says nothing unpriced counts as free. The issue
  asks the same: unpriced compute is never admitted as free under a currency budget.
- **Store the compute money on the step's estimate and reservation**, as an `llm` step's
  estimate carries its money. Rejected: a running step counts the larger of its reservation and
  its actual per quantity. Money stored beside the seconds would then be counted twice, and the
  calibration of a worker's own money estimate would be diluted by money it never estimated.
- **Hold compute money only where the worker reports no money.** Rejected: the cost of a run
  prices compute at the table whatever the worker reports (ADR-0010, second amendment), and a
  worker that reports money for its tokens has not paid for its hardware. A worker whose money
  already includes its compute is held for it twice, which errs towards the limit. ADR-0005 says
  so where its promise ends.
- **Convert between currencies.** Rejected: there is no rate in the record. A budget in another
  currency than the table's refuses compute instead.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #232 in `0.4.0`. No contract changes: the price table's `compute` field exists
since #217, a worker's `limits` already carry a compute ceiling, and the budget statement is no
published schema. No limit moves: no budget, margin or quota is raised or lowered (M3.10); an
existing currency limit is held where it was not. No level moves. The promise changed, so the ADR
was amended under M1.9, in the same pull request.

Found on the way and not built here: a currency budget does not yet hold an `llm` step's money
after the step finished. That is #235, in the shape of the form `Task`.
