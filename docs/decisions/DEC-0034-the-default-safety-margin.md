# DEC-0034 — The default safety margin of a budget

**Category:** NON-BLOCKING
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51), which builds the budget of ADR-0005
**Issue:** [#48](https://github.com/Jersyfi/taktus/issues/48)
**Needed by:** 2026-10-28

## 1. What this is about

Every run has a budget: how much money, how many tokens, how much machine time it may use.
Before a step starts, Taktus estimates what the step will use and admits it only if that fits
what is left. Estimates are wrong. In the first live run the coding step's estimate of its input
was too low by up to four times, and one attempt spent 7.8 % more money than was set aside for
it.

Two things now absorb that error. The first is **calibration**: Taktus remembers how wrong each
worker's estimates were and sets aside more for a worker that underestimates. The second is a
**safety margin**: a share of every budget that Taktus holds back from the first step on. On a
budget of five dollars with a margin of ten per cent, Taktus admits steps against four dollars
fifty. The fifty cents are what a step that overruns its estimate may use before its worker
must stop at its next resting point. Beyond the margin, the worker stops and the run waits for
a person.

The margin has a default, and every budget without its own uses it. The default is yours to set.

## 2. Why you are being asked

Entry M3.10 of `docs/decisions/anchors.taktus.md`: "Raising or lowering a limit: a budget, a
quota, a compute bound, a safety margin (ADR-0005)." The default margin decides how much of
every budget is held back, which is exactly that entry.

## 3. What you must decide

What share of every budget Taktus holds back by default: ten per cent, nothing, or twenty per
cent.

## 4. What you need to know to decide

- **What the margin does.** It lowers the line admission holds a run to, by its share, and it is
  what a step may use beyond its estimate before its worker must stop. A larger margin means
  fewer runs stopped by an overrun and less of each budget available for planned work.
- **What calibration already does.** For the coding worker, calibration starts from the eight
  attempts of the first run: it sets aside 4.3 times the worker's input estimate and 1.08 times
  its money estimate. With that, the worst attempt of the first run would have fitted without a
  margin. For a worker nothing has measured yet, the estimate is taken as given, and only the
  margin absorbs its error.
- **Where each run says it.** Every run records its budget, its margin and the line it was held
  to when it starts, and the command line prints what a budget can promise.
- **What an operator can change.** `TAKTUS_BUDGET_MARGIN` sets the default for an instance,
  between nothing and nine tenths. What you decide here is the default the product ships with.
- **What becomes hard to change.** Little. The value is one setting; changing it changes
  future runs only, and every past run recorded the margin it was held with.

## 5. Options

### Option A — ten per cent (recommended)

- **Meaning:** a run is admitted against nine tenths of its budget, and a worker may use its
  share of the last tenth before it must stop.
- **Consequence:** a step that overruns its estimate by up to about eleven per cent finishes
  instead of stopping the run; a budget buys ten per cent less planned work.
- **Effort:** none; it is the provisional answer.
- **Reversibility:** cheap; one setting.
- **Why recommended:** it covers the error seen on money in the first run (7.8 %) for a worker
  calibration has not measured yet, and it is small enough that a tight budget still does its
  work.

### Option B — nothing

- **Meaning:** a run is admitted against its whole budget; calibration alone absorbs estimate
  error.
- **Consequence:** the first run of a worker that underestimates stops at its first overrun and
  waits for a person; every run can use its whole budget for planned work.
- **Effort:** one line.
- **Reversibility:** cheap.

### Option C — twenty per cent

- **Meaning:** a run is admitted against four fifths of its budget.
- **Consequence:** almost no run stops on an overrun; every budget buys a fifth less planned work.
- **Effort:** one line.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. Ten per cent is in force meanwhile. If no answer arrives by 2026-10-28, it stays, and
changing it later changes one setting and no recorded run.

## 7. How to answer

"DEC-0034: Option A.", "DEC-0034: Option B." or "DEC-0034: Option C." in the issue. Another
share is a fine answer too; a free-text answer is read back as an interpretation and confirmed
before it is acted on.

## Outcome

**Decided:** 2026-10-01
**Answer:** None of the three options as written. The owner: the default safety margin for a
worker **without** calibration history is 100 %, not 10 %; a worker with history uses its
calibration, which narrows the margin with every run. Read as: (1) the margin belongs to a
worker step's estimate, not to the budget as a whole — a worker nothing has measured yet, and no
seed covers, reserves its estimate plus 100 %, twice its estimate; (2) a worker with history
reserves its estimate scaled by its measured error; (3) model and connector steps, whose
estimates are a counted prompt and a declared demand, are bounds and take no margin; (4) the
budget-wide holdback the question asked about stays a named setting and holds back nothing by
default. This reading is the record; the pull request that carries it is where the owner
confirms it.
**Reasoning given:** the only worker measured so far underestimated by a factor of two to four.
Caution towards the unknown, loosening through data.
**Recorded in:** [#51](https://github.com/Jersyfi/taktus/pull/51).
`TAKTUS_BUDGET_UNCALIBRATED_MARGIN` (1.0) and `TAKTUS_BUDGET_MARGIN` (0) in
`src/taktus/composition/settings.py`; `UNCALIBRATED_MARGIN` in
`src/taktus/components/run/domain/service/budget.py`; ADR-0005, third amendment, point 6;
`tests/components/run/test_budget.py::test_an_uncalibrated_worker_reserves_twice_its_estimate_and_history_narrows_it`.
