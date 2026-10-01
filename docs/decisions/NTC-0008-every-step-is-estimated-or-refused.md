# NTC-0008 — Every step is estimated or refused

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-30
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51)

## 1. What was decided

What a run does around every step changed, inside the scope ADR-0005's second amendment agreed:

- **Old:** only a worker step was estimated; a rule, a connector call, a wait and an `llm` step
  were admitted with nothing. **New:** every step has an estimate before it is admitted — a
  model step its counted input and output limit, a connector call its operation's declared
  demand, a rule nothing — and a step that cannot be estimated is refused; the run halts with the
  new cause `no_estimate`.
- **Old:** a worker's `limits` were everything left of the budget. **New:** they are its
  reservation — the estimate as calibration scales it — grown by the run's margin and never more
  than is left; a worker that halts before crossing them halts the run with cause `limit`.
- **Old:** admission held a run to its budget. **New:** to its budget less its margin, and also to
  what the platform has free (ADR-0031).
- **New ledger entries:** `budget.set` with the budget statement, `step.reserved` where the
  reservation differs from the estimate, `step.rejected` with outcome `no_estimate` or
  `rejected_by_capacity`.
- **New:** every operation of the reference connector declares its demand.

## 2. The evidence

The first live run (`docs/runs/first-run.md` §2): an `llm` step admitted with no estimate, a
worker estimate wrong by 4.3 times on input, one step 7.8 % over its money. The tests that hold
the new behaviour: `tests/components/run/test_estimates.py` and `test_budget.py`.

## 3. What was considered

- Admitting a step without an estimate when the budget does not limit what it uses: rejected,
  principle 8 forbids "a step admitted without an estimate" without exception.
- Giving the worker everything that is left as its ceiling: rejected, a worker that overruns its
  reservation would then spend the steps after it.

## 4. Which entry permits it

M2.4: a change of what the software does inside an agreed scope — ADR-0005's design, accepted —
that breaks no contract (the contract additions are optional fields), moves no autonomy level and
says nothing public. The one value that moves a limit, the default margin, is DEC-0034.
