# ADR-0005 — Step atomicity and admission control

**Status:** accepted · amended 2026-09-19 (DEC-0012): the first guarantee holds per consumption
kind, and §*Amendment* says for which · amended 2026-09-21: a budget is a budget — the design
that brings a currency limit as close to the line as a provider allows (§*Second amendment*);
the implementation follows in the next pull request

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
