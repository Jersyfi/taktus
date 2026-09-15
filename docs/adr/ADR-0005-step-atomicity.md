# ADR-0005 — Step atomicity and admission control

**Status:** accepted

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
- Two hard guarantees, both provable from the ledger: no limit is ever breached; at most one step of
  work is lost.
- Long-running tasks must be decomposed into persistable steps during planning. That is a
  requirement on the planner, not a side effect.
- Replaying a run comes for free.
