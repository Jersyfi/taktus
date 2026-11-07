# ADR-0244 — The value ledger folds activity per process and day, and computes its figures against a stated basis

**Status:** accepted · builds on ADR-0226, ADR-0029, ADR-0010, ADR-0105, ADR-0015 · serves
UC-9.3, UC-6.6, UC-9.1, UC-6.7, UC-9.2 · DEC-0228

## Context

The value component counts one figure, the correction rate (ADR-0226). UC-9.3 asks for a value
balance per process with a revert analysis and a recommendation per quadrant; UC-6.6 for a
proof of value whose every figure names its method and data basis; UC-9.1 for five controlling
figures with targets and simulations; UC-6.7 for the bus-factor index from recorded test
results; UC-9.2 for the maturity of departments, a backlog of potential and progress against a
plan. All of them read the same runs, and principle 7 forbids two numbers for one thing.

## Decision

### 1. Activity, folded per process and day

The projection `value.activity.v1` folds `run.created`, `run.finished`, `run.escalated`,
`step.finished`, `step.corrected` and `proposal.decided` outside a rehearsal into, per process
and UTC day: runs finished and escalated, the seconds from creation to end of those runs, step
results by a person and by any other method, step results a check refused (`check_failed`),
results corrected, and the decisions at level 1 or 2 released, corrected and rejected. It keeps
no actor. Every figure over a period sums the days of the period.

The projection `value.dependence.v1` folds `takeover.trial` and `removal.tested` with their time,
so that the bus-factor index can be computed at any past day.

### 2. The basis is the organisation's, stated and versioned

The **value basis** of a tenant is its configuration, written as a new version each time and
never changed: the currency; a personnel cost rate per role — a rate per person has no field;
per process the minutes one case takes by hand, the roles that would do it, the hours to learn
it from the takeover instructions, the minutes from request to done by hand, the business
relevance (`critical`, `important`, `nice`), a licence share per month and the investment it
took; targets per process and figure; the transformation plan per organisational unit; and
entries of potential a person entered. `value.basis_set` records each version with the person in
`refs.actor` and the version's digest. A figure resting on the basis carries the version, when
it was set and by whom, and is marked as resting on an assumption. A figure whose basis is
missing is withheld and says what is missing; it is never shown as zero.

### 3. The figures

Per process, over a period (`value/domain/service/figures.py`):

- **cockpit** (UC-9.1): `value.cycle_seconds`, the mean seconds from creation to end of the
  runs that ended; `value.quality`, the share of ended runs that finished with no result
  corrected; `value.cost_money` and `value.cost_takt`, read from accounting, never computed
  here (ADR-0010); `value.automation`, the share of step results produced by a method other
  than a person; `value.escalation_rate`, the share of ended runs that escalated;
- **balance** (UC-9.3): `value.time_saved_hours`, runs finished times the minutes by hand;
  `value.personnel_equivalent`, that time at the mean rate of the roles by hand;
  `value.error_cost`, results corrected times the minutes by hand at that rate;
  `value.licence_cost`; `value.balance`, the personnel equivalent less every cost;
  `value.errors_avoided`, the results a check that ran refused; `value.payback_months`, the
  investment over the monthly balance; the **revert analysis** — hours a month, roles, hours to
  learn, the change in response time — or, without takeover instructions, the statement that it
  cannot be made;
- **proof of value** (UC-6.6): the sums of the balance figures over the processes, and the cost
  of a case automated against by hand, each with its method and basis;
- **bus-factor index** (UC-6.7): processes whose active version has no passed takeover trial;
  per role, the processes a person of the role is needed for; per supplier, the processes its
  current removal verdict `broke`, a verdict `untested`, or one taken for an earlier version or
  without a configuration, shown as unknown; the trend per day; the graph; per value stream;
- **transformation** (UC-9.2): per organisational unit, maturity as the mean of four shares —
  autonomy level over 4, reproducible step methods, passed takeover trials, suppliers not
  broken — the backlog and the progress against the plan, linked to the change of the unit's
  time saved against the period before.

### 4. Proposals

A figure outside its target, a deterioration of the index, and each quadrant's recommendation
are **value proposals**, computed on every read and stored nowhere: each names its kind, the
process, the figure, the target or the quadrant, the period and the runs behind it. The
quadrant is set by the process's monthly cost against the median of the tenant's processes and
by its relevance. To optimise names first the steps of a variable method, for a more
reproducible one (ADR-0004), and a cheaper model second. To raise autonomy is a proposal to the
process's owner; a simulation of the next level is computed from the decisions people took at
the current one, is marked as a simulation, and changes nothing (ADR-0026). A candidate to switch
off is added to the owner's reports unasked (ADR-0242 §2).

## Alternatives

- **Store the figures.** Rejected: a stored figure is stale when the next run ends (ADR-0226).
- **A rate per person for precision.** Excluded by principle 14 and UC-9.3.

## Where this promise ends

- The time by hand is the organisation's assumption; every figure built on it is as good as it.
- An error avoided is a result a check refused; a defect caught in another way is not counted.
- The quadrant's boundary is the tenant's median cost; with one process every process is cheap.
- The index's trend holds the current set of processes against past trials and verdicts; a
  process that existed only in the past is not in it.
- A simulation assumes each decision would have run as the person decided it; it predicts
  nothing else.
- A department's processes are those of the value streams its roles are responsible for; a
  process in no stream belongs to no department.
