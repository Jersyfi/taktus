# ADR-0005 — Step atomicity and admission control

**Status:** accepted · amended 2026-09-19 (DEC-0012): the first guarantee holds per consumption
kind, and §*Amendment* says for which

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
