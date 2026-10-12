# ADR-0005 — Step atomicity and admission control

**Status:** accepted · amended 2026-09-19 (DEC-0012): the first guarantee holds per consumption
kind, and §*Amendment* says for which · amended 2026-09-21: a budget is a budget — the design
that brings a currency limit as close to the line as a provider allows (§*Second amendment*) ·
amended 2026-09-30 (DEC-0035): which promise yields when one step overruns, every step
estimated, money from the record, and a budget only as strong as the provider allows
(§*Third amendment*); implemented in the same pull request · amended 2026-10-01 (DEC-0043): the
worker's margin has a floor of 10 % and its history resets with its model version (point 6) ·
amended 2026-10-08 (DEC-0047, NTC-0025): an operator's margin below the floor is said where it is
set and in every report that relies on it (point 6) · amended 2026-10-11 (NTC-0188): a currency
budget holds the money of compute seconds at the run's price table, and refuses compute the table
does not price (§*Fourth amendment*)

## Context
A limit enforced by aborting destroys work and money at the same time: the tokens are spent and the
result is gone. With a subscription window it is worse, because the window cannot be topped up.

## Decision
Every step persists its result — checkpoint, artifacts, consumption. Before a step starts, the
worker estimates its demand and the step runs only if it fits the remaining limit. A stop takes
effect at the next step boundary.

## Alternatives
- **Hard abort on limit** — simpler, loses work.
- **Requiring native pause support from workers** — few can do it, and the guarantee would no longer
  be worker-agnostic. Workers that can pause refine the granularity; they are not a precondition.

## Consequences
- Two hard guarantees, both provable from the ledger: no limit is ever breached — for the
  consumption kinds a worker reports per step, which the amendment below names; at most one step
  of work is lost.
- Long-running tasks must be decomposed into persistable steps during planning. That is a
  requirement on the planner, not a side effect.
- Replaying a run comes for free.

## Amendment — for which consumption kinds the first guarantee holds

The original text said "no limit is ever breached" without qualification. The first real coding
worker showed that the sentence is true for some consumption kinds and not for others, and an
ADR that promises more than the workers can deliver is a documentation defect (DEC-0012). What
follows replaces the unqualified sentence.

**The guarantee comes from admission, and admission needs a running total.** Before a step
starts, its estimate is checked against what remains of the limit. What remains is the limit
minus what every earlier step *reported*. A kind that a worker reports per step therefore has an
exact running total at every boundary, and admission holds the line: a step that would cross it
does not start.

| Consumption kind | Reported | The guarantee |
|---|---|---|
| **tokens** (`tokens_in`, `tokens_out`) | per step, by every worker that uses a language model (`consumption.reported`, W-04) | holds: the running total is exact at every boundary |
| **quota** (`quota_units`) | per step by workers, per call by connectors | holds |
| **compute** (`compute_seconds` in a resource class) | per step | holds |
| **currency** | at the end of an assignment, by a worker that learns its cost only then — the coding worker reports `total_cost_usd` once, with its final result (`workers/claudecode/README.md`, *Consumption*) | **degrades to an estimate:** the running total is exact only at assignment boundaries, not at step boundaries within one |

For currency, then: a step starts only if its *estimated* cost fits what remains. A step that
costs more than its estimate is discovered when its assignment finishes and reports. The next
step is admitted against the corrected total; the overshoot has already been spent.

**What a person setting a currency budget can expect.** No assignment starts whose estimate does
not fit what remains. When an assignment finishes and reports its cost, the total is corrected
and the next assignment is admitted against it. The budget can therefore be exceeded by at most
the difference between one assignment's estimate and its actual cost, and the ledger shows the
overshoot at the boundary where it was reported. **What they cannot expect:** that a running
assignment is stopped by its cost, or that the spend never exceeds the budget. A worker that
reports money per step raises the currency guarantee to the same level as tokens; the coding
worker cannot, and its README says so.

**The consequence worth having.** The Takt (ADR-0010) derives from tokens and compute seconds —
quantities reported per step — and not from money. It is therefore the quantity admission
control can actually hold a run against, and a budget stated in Takte has the guarantee that a
budget stated in a currency does not. That is an argument for the Takt that was not in ADR-0010
and belongs there once the Takt is measured (`0.2.0`).

`docs/architecture/control-plane.md` §5.1 and §7 state the same table in the reader's words.

## Second amendment — a budget is a budget

The first amendment stated where the currency guarantee ends. The owner's position on that
boundary: a limit is a limit. Where a provider makes it impossible to hold exactly, the answer
is to get as close as possible and to say so everywhere — not to accept the gap. What follows is
the design. It is recorded here so that the implementation, in the next pull request, is held
to it; nothing of it is implemented yet.

**1. Reserve, do not reconcile.** Admission control debits the *estimate* from the budget at
the moment the step is admitted, not the actual at the moment the step completes. While the
step runs, the budget already shows the estimate as spent. When the actual arrives, the
reservation is replaced by it: released downward when the step cost less, corrected upward
when it cost more. An overrun can then come from one source only — the estimate was wrong —
never from the budget being blind between admission and report. Today the run holds only
what was *reported* against the budget (`run.consumed()`): the estimate of a running step is
not held while the step runs, which is harmless while steps run one after another and becomes
a hole the moment two steps run at once or a worker reports money only at the end.

**2. Enforce in tokens, not in money.** A budget stated in a currency is converted at the start
of the run into a budget in tokens, per model, using the known price of the model configured
for each purpose. The token budget is enforced where measurement happens: per step, exactly
(the first amendment's table). The residual error of a currency budget then shrinks to
*price-list drift* — the price changed after the run started — and to workers that report
tokens but not money; both are named in the run's report. A budget in Takte needs no
conversion, which is the argument for the Takt the first amendment already made.

**3. A named safety margin.** A margin, configurable per tenant and per process, is subtracted
from the budget before the first step is admitted. On a tight budget Taktus works more
conservatively: it admits less than the budget says, by the margin. The margin is a
configuration value with a name and a default, never a hidden constant, and the report of every
run shows the budget, the margin and the line the run was actually held to.

**4. Estimate quality is measured per worker.** For every worker step the ledger holds the
estimate and the actual. Per worker — never per person — Taktus keeps the ratio over time. A
worker that consistently underestimates earns a larger margin automatically: its estimates are
scaled by its measured error before they are admitted. The system becomes more accurate instead
of repeating a promise it cannot keep. The scaling is a statistic over the ledger, reproducible
from it; a change to how it is computed is a change to this ADR.

**5. Transparency, everywhere it belongs.**
- Setting a budget shows the possible overrun range, not just a number: the largest single
  step estimate the worker may exceed, the price-list drift since the run started, and the
  workers whose money is reported per assignment.
- A forecast names a band, not a point.
- Every step whose actual exceeded its estimate appears in the run's report as a *calibration
  signal* — a fact about the estimate, not a failure of the step.
- Every place that shows a budget in a currency shows the token budget it was converted into
  and the price it was converted at.

**What this changes in the first amendment's table.** Nothing in the rows for tokens, quota and
compute. The currency row gains a second line: with the reservation and the conversion in
place, the running total in tokens is exact at every boundary, and the currency figure is that
total at the conversion price plus the drift since. The sentence "the spend can exceed the
budget by the difference between one assignment's estimate and its actual cost" stays true and
becomes the whole of the residual, stated with its size in the report.

The limits of this design are in *Where this promise ends* below.

## Third amendment — the first run's findings, and which promise yields

The first live run (2026-09-23, `docs/runs/first-run.md` §2) measured the design against real
numbers and found three faults. This amendment corrects them and records what was built. The
decision record is DEC-0035.

**1. The two guarantees collide when one step overruns, and "no limit is breached" yields by at
most one inner step.** "At most one step of work is lost" and "no limit is ever breached" cannot
both hold when a single step uses more than was reserved for it: stopping it at once loses
work, and letting it finish crosses the line. Attempt 4 of the first run spent 7.8 % more money
than its step was estimated at. The resolution goes through the worker contract's `limits`:

- the reservation — the estimate as calibration scales it (point 4 of the second amendment) —
  is passed to the worker as its `limits`, grown by the run's margin and never more than what
  is left of the whole budget;
- the worker halts at its next step boundary when its running total plus its next inner step's
  demand would cross a limit, and ends `stopped`, naming the `limit`, with its checkpoint
  (check W-14 of `contracts/worker/v1`, beside W-10, which refuses *before* the start);
- the run halts with cause `limit`, and a person raises the limit or lets it be (M3.10).

**Which promise yields, and why.** "At most one step of work is lost" holds without exception:
the worker stops only at a boundary, with a checkpoint, and a resume continues from it.
"No limit is ever breached" yields by at most the overrun of the one inner step during which
the running total crossed the line: a step whose demand was not knowable before it started
cannot be stopped inside itself without losing it. The reservation exists to absorb exactly
that overrun — twice the estimate for a worker nothing has measured yet, its measured error for
one with history (point 6). Work lost is lost for good; a
bounded overrun is recorded, calibrated against and reported. The first promise is therefore
the one kept whole.

**2. Every step is estimated, and a step that cannot be is refused, not admitted.** An `llm`
step passed admission with no estimate at all. Now every step has one before it is admitted:

| Step | Its estimate |
|---|---|
| `worker` | the worker's answer to `POST /v1/estimate`, as before |
| `llm` | input tokens counted before the call by the model adapter (exactly, or as an upper bound, as it declares); output tokens bounded by the limit the step sets; money at the price table, with every input token priced as the dearest input kind, because whether it will be read from a cache is not knowable before the call |
| a connector call | what the operation declares one call consumes (`contracts/connector/v1`, `Demand`) |
| a wait on a connector | that demand for as many calls as the wait can make |
| a rule, a wait on the clock | nothing, and exactly so |

A model that cannot count, an operation that declares no demand, or a budget in a currency
over a model the price table does not price leaves the step without an estimate: it is refused
(`step.rejected`, outcome `no_estimate`) and the run halts with cause `no_estimate`.

**3. Money follows from the record.** Consumption carries tokens per model and per price kind —
uncached input, output, input read from a cache, input written to one (`contracts/shared/v1`,
`tokens_by_model`) — and a versioned price table prices them (`contracts/model/v1`,
`PriceTable`). The run's budget statement names the table by the digest of its document, so
that money is recomputable from the ledger at the prices it was held to. This is what ADR-0010
asks of the Takt: the same breakdown feeds both.

**4. Estimate quality is measured and acted on.** Calibration (point 4 of the second amendment)
is built: per adapter and method, the largest ratio of actual to estimate over the last twenty
observations of the ledger, never below one. For an adapter nothing has measured yet, a seed
stands in: the eight attempts of the first run for a worker that serves the coding
capabilities, which reserves 4.3 times its input estimate and 1.08 times its money estimate.

**5. The budget says what it can promise when it is set.** A model adapter declares its
`Calculability` (`contracts/model/v1`): how it counts input, whether its output limit is hard,
which price kinds its provider reports, and how the provider bills. From the declarations the
run derives, per limited kind, how it is held — exactly per step, as an estimate, only as a
share of a subscription's time window, or not at all — and records that statement as
`budget.set` before the first step. Where a provider bills per time window, the statement says
that a currency budget cannot be enforced, only a share of the window. The evidence for what
providers permit is `docs/research/2026-09-30-what-providers-allow.md`.

**6. The safety margin belongs to a worker's estimate** (DEC-0034, the owner's answer). A worker
with no calibration history reserves its estimate plus 100 % — twice its estimate
(`TAKTUS_BUDGET_UNCALIBRATED_MARGIN`, 1.0) — because the only worker measured so far underestimated
by a factor of two to four. A worker with history reserves its estimate scaled by its measured
error, and at least its estimate plus a margin that narrows with every observation — 1/(n+1)
of the 100 % after n — so that one run does not take the whole margin away: caution towards the
unknown, loosening through data. Observations never narrow the margin below 10 % — an
operator who configures the uncalibrated margin itself lower has set that limit, and it holds
(DEC-0047). Such a value is never silent: the startup log carries a warning naming the value and
the floor, every run started under it records in its `budget.set` statement that the margin was
set below the floor, and `taktusctl cost` prints that beside the run's money (NTC-0025). A
worker's history
resets when its model version changes — the one its estimate names, else the one it last
reported — because a calibration for one model says nothing about the next (DEC-0043, the
owner's answer, 2026-10-01). The
budget-wide holdback of point 3 of the second amendment stays a named setting
(`TAKTUS_BUDGET_MARGIN`) and holds back nothing by default; where an operator sets it, a worker
may use its share of it before it must halt.

## Fourth amendment — a currency budget holds the money of compute (2026-10-11)

Since ADR-0084 a price table may price a second of compute per resource class, and since #230
the cost of a run counts that money (ADR-0010, second amendment). Admission did not. A currency
budget was held against what workers estimate and report in that currency and against the
priced estimate of an `llm` step. A worker that reports compute seconds and no money was
therefore admitted as if its compute were free, while the budget statement said the currency
was held. That is a limit that does not hold, and the second amendment's position is that a
limit is a limit. What follows is built (#232, NTC-0188).

**1. Compute money is held at the run's table.** Where a run has a currency budget and its
price table prices compute in a currency the budget limits, admission prices a step's reserved
compute seconds at the table. It prices what the run used and reserved the same way, per
resource class. The step is admitted only where its money fits what remains of the line. The
money is derived from the seconds each time; it is never stored on the step, so that money
still follows from the record (third amendment, point 3).

**2. A worker halts on the compute its money buys.** A worker reports compute seconds, not
money, so a ceiling in money would not stop it. Where compute money is held, the worker's
`limits` carry a compute ceiling even where the budget sets none. The ceiling is its reservation,
grown by the run's margin, and never more than the seconds the money left would buy (W-14).

**3. Unpriced compute is refused, never admitted as free.** Under a currency budget, a step whose
estimate names compute seconds is refused (`no_estimate`) when no price table is configured,
when the table prices no compute, when it prices in a currency the budget does not limit, or
when it does not price the step's resource class. The same holds when compute the run already
used has no price, because what is left of the budget cannot then be computed. This is the rule
the third amendment, point 2, set for a model the table does not price.

**4. The statement says it when the budget is set.** A run with a currency budget and a worker
step records, in `budget.set`, a promise of kind `compute_money`. It says `held`, with the table
and the classes it prices, or `unpriced`, with the reason and the consequence that a step that
needs compute is refused.

**What this changes in the first amendment's table.** Nothing in its rows. The currency row now
covers compute seconds where the table prices them, held per step like compute itself.

## Fifth amendment — every cached token is booked by its kind (2026-10-13)

Money follows from the record (third amendment, point 3), so a token booked at the wrong kind
is money recorded wrong. The adapter for the chat-completions dialect read cached input only
nested in `prompt_tokens_details`. An endpoint that reports it at the top of the usage, as
`cache_creation_input_tokens` and `cache_read_input_tokens`, had its writes booked as uncached
input: 8 000 writes in a call of 10 000 input tokens were booked as 10 000 input and no write
(issue #312, `docs/research/2026-10-12-devops-review.md` §G1). Where a write costs more than
uncached input, the money recorded was too low. What follows is built.

**1. Both shapes are read.** The adapter books input read from a cache and written to one
wherever the endpoint reports it, nested or at the top of the usage. Where both shapes report a
kind, they count the same tokens, and the larger count is booked once. Cached tokens that exceed
`prompt_tokens` cannot be part of it; the total is then taken as the uncached input alone, and
the input tokens as the sum. `contracts/model/v1` §5 states the rule, and the conformance suite
reads the same rule.

**2. The operator declares what the endpoint reports.** `TAKTUS_MODEL_USAGE_KINDS` names the
price kinds the endpoint reports per call; unset, `input,output`. The adapter's declaration
(`usage_kinds`, point 5 of the third amendment) is that list. Conformance check M-04 fails an
endpoint that does not report a declared kind, so a declaration is held to what the endpoint
does.

## Where this promise ends

The first amendment states where the currency guarantee ends: a worker that reports money
only when an assignment ends leaves the running total blind within the assignment, and the
budget can be exceeded by one assignment's estimate error. The second amendment shrinks that
residual and does not remove it: price-list drift after the run started, a worker that reports
tokens but no money, and a wrong estimate remain, each stated in the report. "At most one step
of work is lost" holds for what the worker persisted at its last boundary; a worker that
reports no inner boundaries loses the whole step. Replaying a run reproduces the sequence of
steps, not the answers of a variable method.

The third amendment moves the boundary, and does not remove it. The overrun of the inner step
during which a running total crossed the line is spent; a worker that reports a quantity only
when its assignment ends — the coding worker's money — cannot halt on it, and is held by the
quantities it does report per step, tokens. An upper-bound count over-reserves by design; an
estimate a provider calls exact may differ from its bill by a small amount (the research names
one that does). A connector call that needs more than its operation declares reports more
after it, and is recorded as a calibration signal. Calibration learns only from the ledger it
reads: the first run of an adapter no seed matches is held at its estimate as given. The
refusal for want of an estimate holds for the four ways a step is estimated today; a method
added later brings its own.

The fourth amendment holds compute money only at the run's own table, in the table's currency.
There is no conversion between currencies: a budget in another currency refuses compute instead
of guessing a rate. A worker that reports money which already includes its compute is held for
that compute twice — once as it reports it, once at the table; it errs towards the limit. Compute
a worker uses without estimating it is priced once it is reported, at the next boundary, not
before. A step's compute money is not part of its recorded estimate, so calibration learns the
seconds and not the money. Quota units and storage have no price, and a currency budget does not
hold them. The money of an `llm` step is held at its priced estimate while the step runs; once
it finished, the running total does not count it yet. That is a finding against this ADR, not a
boundary of it (#235).

The fifth amendment reads the two shapes known on 2026-10-13. A provider that reports cached
input under another name has it booked as uncached input, and M-04 shows that only for a kind
the operator declared. Where `prompt_tokens` excludes the cached tokens and is still larger than
them, the rule cannot tell, and the cached tokens are taken out of it: the input is then booked
too low. Which convention each endpoint in use follows is verified against it, not assumed. M-04
checks the declaration when the suite runs, on a short call; a provider that stops reporting a
kind later is not seen until the suite runs again.
