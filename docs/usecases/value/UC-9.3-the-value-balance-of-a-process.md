---
id: UC-9.3
title: The value balance of a process
component: value
epic: E9
serves: [P8, P10, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0004: ffdb1f1537f5, ADR-0010: 6b161e3f6831, ADR-0015: 420aac4db0cc, ADR-0026: ccc4bd1f5423, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-9.3 — The value balance of a process

## 1. What must be achieved

Not only what a process costs, but what it is worth — by criteria the organisation sets itself. For
every process Taktus keeps a **value balance**, updated as the process runs:

- **the cost side:** the cost of models and workers, infrastructure, a share of licences, and the cost
  of errors and rework;
- **the benefit side:** working time saved, valued at the personnel cost rate the organisation set for
  each role; time gained in throughput; quality and errors avoided; and a business relevance the
  process's owner assigns — critical, important, or nice to have;
- **the revert analysis:** what it would cost and mean to have people do the process again — hours a
  month, the roles needed, the time to learn it from the takeover instructions (UC-6.3), and how much
  slower the response would be. The consequences of turning automation back are as visible as its
  advantages.

All processes appear in a matrix of cost against business relevance, and each quadrant carries a
recommendation: cheap and relevant — raise autonomy; expensive and relevant — optimise; expensive and
not relevant — a candidate to switch off or rebuild, reported actively; cheap and not relevant —
observe.

The balance serves the steering of processes. It never serves the assessment of people.

## 2. How it is verified

- The criteria, their weights and the personnel cost rates are configuration of each organisation. A
  personnel cost rate is set per role; a rate per person cannot be configured.
- Every figure on the cost side is read from accounting — consumption in Takt and money (ADR-0010) —
  or from a cost the organisation configured; none is computed a second time in `value` (ADR-0029).
- Time saved is computed from the runs that completed and the time the same work takes by hand, as the
  revert analysis states it; the time by hand is an assumption shown with who set it.
- The revert analysis of a process states hours a month, roles, the time to learn the process from its
  takeover instructions, and the change in response time, each with its basis. A process without
  takeover instructions shows that the revert analysis cannot be made, rather than a figure.
- Management sees, per process: the balance, the cost of the process against the equivalent personnel
  cost, the payback period, and the cost of reverting.
- Every recommendation names its quadrant and the data it was derived from. A recommendation to
  optimise first names whether a cheaper or more reproducible method would do the step (ADR-0004,
  ADR-0015 §3). A recommendation to raise autonomy is a proposal to the process's owner, never a change
  (ADR-0026, UC-15.5). A candidate to switch off is reported to the owner without being asked.
- No figure of the balance, and no input to it, is attributed to a named person (principle 14). A test
  fails when one is added to the data model.
- The balance can be aggregated per domain (UC-15.1) and per chain across domains (UC-15.4).

## 3. Where the boundary lies

**Not bookkeeping.** The balance is a steering figure, not an entry in the organisation's accounts.
**Not an automatic decision.** Switching a process off, rebuilding it or raising its autonomy stays
with its owner. **Not the proof of value**, which sums the balances for management and investors
(UC-6.6).

## 4. What it rests on

The `value` component, which owns the value ledger and the revert analysis
(`docs/architecture/project-structure.md` §1); figures with one owner (ADR-0029); consumption in Takt
and money (ADR-0010); method selection (ADR-0004) and the rule that a method change is checked before
a limit is raised (ADR-0015); the autonomy statement (ADR-0026); the takeover instructions (UC-6.3);
the responsibility anchor (UC-15.5). Definition `UC-9.3`. The roadmap's `0.5.0`, *value ledger with
revert analysis*.

**What an accepted decision supersedes in the definition's text.** The definition counts the cost of
artificial intelligence as tokens and model cost (definition `UC-8.5`). Accounting now records all
work — of models, workers and compute — in one normalised unit, the Takt, and in money from the record
(ADR-0010); the cost side reads both. The definition's way to optimise an expensive process is a
cheaper model or a tuned prompt; method selection makes a more reproducible method the first
candidate, and a cheaper model the second (ADR-0004).
