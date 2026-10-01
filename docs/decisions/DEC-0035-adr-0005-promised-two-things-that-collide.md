# DEC-0035 — ADR-0005 promised two things that collide when one step overruns

**Category:** DEFECT
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51), which builds the budget of ADR-0005 against the numbers of the first live run
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

ADR-0005 makes two promises about every run: no limit is ever breached, and at most one step of
work is lost. The first live run (`docs/runs/first-run.md` §2) showed three places where the
repository said something that was not true:

- **The two promises cannot both hold when a single step overruns.** Attempt 4 of the coding
  step spent 7.8 % more money than its estimate. Stopping such a step at once loses its work;
  letting it finish crosses the line. The ADR named neither which promise yields nor where.
- **"Before a step starts, the worker estimates its demand"** was true for worker steps only.
  An `llm` step passed admission with no estimate at all, and so did every connector call. Where
  the code and an ADR disagree the ADR wins, and the code is the finding.
- **"Recomputable from the ledger"** (ADR-0010, cited by ADR-0005) did not hold for money: the
  ledger recorded tokens without the model and without the price kind, and attempt 1 spent half
  the money of attempt 3 for more tokens.

## 2. Why you are being asked

You are not. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes correcting a documentation
defect the session's, recorded as a `DEFECT`, with an ADR amendment where an ADR is involved;
entry M1.9 makes a change to an accepted ADR's substance the session's while the vision holds.
The correction keeps both guiding principles it touches — principle 8 asks for exactly this —
and moves no limit: the one value that would, the default margin, is asked as DEC-0034.

## 3. What you must decide

Nothing. The ADR is amended and the code follows it, with tests.

## 4. What you need to know to decide

- **Which promise yields.** "At most one step of work is lost" holds without exception. "No limit
  is ever breached" yields by the overrun of the one inner step during which a running total
  crossed the line. The reservation, grown by the run's safety margin, is the worker's hard
  ceiling; a worker halts at its next boundary before crossing it (check W-14 of the worker
  contract), and the run halts with cause `limit`.
- **Every step is estimated.** A worker by its own estimate, a model step by its counted input
  and its output limit, a connector call by its operation's declared demand, a rule by nothing.
  A step that cannot be estimated is refused, not admitted.
- **Money from the record.** Tokens are recorded per model and per price kind, and a versioned
  price table prices them; `taktusctl cost <run>` recomputes a run's money from the ledger.
- **Tests that hold it:** `tests/components/run/test_estimates.py`, `test_budget.py`,
  `tests/components/accounting/test_cost.py`, and W-14 in `tests/conformance`.

## 5. Options

None for the owner. What the session did: the third amendment of ADR-0005, the amendment of
ADR-0010, the code and the tests named above.

## 6. What is blocked

Nothing. The budget of `0.2.0` was waiting for exactly this.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0035" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-30
**What was wrong:** ADR-0005 promised "no limit is ever breached" and "at most one step of work is
lost" without saying which yields when one step overruns; it said every step is estimated while
only worker steps were; and money was not computable from what the ledger recorded.
**Why it was wrong:** both promises cannot hold when a step's demand is not knowable before it
starts, and the first run produced such a step; the estimate had been asked of the one kind of
step that had an endpoint for it, not of every step.
**What it now says:** the third amendment: the work promise holds, the limit promise yields by at
most one inner step's overrun, absorbed by the margin; every step is estimated or refused; money
follows from tokens per model and price kind at a versioned price table; a budget says what it
can promise when it is set.
**What changed in substance:** admission estimates every step and refuses one without an
estimate; the worker's `limits` are its reservation grown by the margin, and a worker halts at a
boundary before crossing them; consumption carries tokens by model and price kind; the run
records its budget statement as `budget.set`.
**Recorded in:** [#51](https://github.com/Jersyfi/taktus/pull/51)
