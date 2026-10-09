---
id: UC-8.5
title: Cost control for every unit — budgets, alerts, forecasts
component: accounting
epic: E8
serves: [P7, P8, P14]
state: building
version: 0.2.0
tests: [tests/components/accounting/test_cost.py::test_a_run_costs_what_its_tokens_cost_at_the_table_it_was_held_to, tests/components/run/test_engine.py::test_admission_counts_what_earlier_steps_used, tests/components/run/test_budget.py::test_the_margin_absorbs_an_overrun_and_nothing_beyond_it, tests/components/run/test_budget.py::test_money_reported_per_assignment_is_held_as_an_estimate, tests/components/run/test_estimates.py::test_the_budget_says_what_it_can_promise_when_it_is_set]
adrs: {ADR-0005: c28377b9027e, ADR-0010: 6b161e3f6831, ADR-0015: 420aac4db0cc}
supersedes: null
---

# UC-8.5 — Cost control for every unit — budgets, alerts, forecasts

## 1. What must be achieved

Every model call, and every other step that consumes something, is recorded with what it consumed
and what that cost, and attributed to the unit it ran for. A unit is whatever the organisation
configures: a person, a team, a project team, a department, the company, a private group or a
family. Each unit can have budgets — per month, per project, per process. Before a budget is
reached, an alert warns; at the budget, the configured policy applies. Taktus forecasts, from the
consumption so far and the runs planned, what each unit will have spent and when its budget will
run out, and warns early, not only at the limit.

## 2. How it is verified

- Every completed step records its consumption — tokens per model and per price kind, compute
  seconds per resource class, quota units — and the unit it is attributed to. The money a run cost
  is recomputable from the ledger at the price table it was held to (ADR-0010).
- Budgets can be set per unit and per period, project or process. They inherit along the
  organisation's structure — company, department, team, person — and the rules for booking over and
  under a parent's budget are configuration. A child's budget never lets a step through that its
  parent's budget would refuse.
- An alert fires when a unit's consumption, or its forecast, reaches a configurable share of its
  budget, and reaches the unit's addressees in their view.
- A step whose estimate, as reserved, does not fit what remains is not admitted. No budget is
  exceeded by more than the overrun of the one inner step during which a running total crossed it,
  and that overrun is recorded (ADR-0005, third amendment).
- At the budget, the configured policy applies, chosen from: halt at the step boundary and bring in
  a person (the default); wait for the budget's next period; continue on a cheaper model the process
  allows for the same purpose. No policy admits a step beyond the line.
- When a budget is set, Taktus states what it can promise for it: per consumption kind, whether it is
  held exactly per step, as an estimate, only as a share of a provider's time window, or not at all.
- A forecast names a band, not a single date or amount, and states what it was computed from.
- An anomaly in a unit's cost — a rise that the unit's own history does not explain — raises an
  alert. Whether something is an anomaly is decided by a rule or a statistic over the ledger, never
  by a language model.
- Consumption and cost per unit are shown as they are recorded; money a worker reports only when an
  assignment ends is shown as an estimate until it is reported.
- What a named person consumed is visible to that person. Anyone else sees consumption aggregated
  by role, team or department; no view ranks people by what they consumed (principle 14).

**Proven so far:** money recomputed from the ledger, admission against what earlier steps used,
the margin that absorbs an overrun, money per assignment held as an estimate, and the statement of
what a budget can promise, by the named tests — for a run's budget. Units, inheritance along the
organisation, alerts, policies other than halting, forecasts and anomalies are not built.

## 3. Where the boundary lies

**Not charging.** What the organisation pays for Taktus is the Takt's, and nothing is charged yet
(ADR-0010, the owner's question M4.3). **Not the provider's bill.** Taktus holds its own record and
names where it may differ from a provider's invoice; it does not reconcile the invoice. **Not limits
on resources other than consumption.** Compute capacity, rate limits and their health are
definition `UC-8.10`. **Not an assessment of anyone.** A budget for a person limits what is run for
them; it is not a measure of their work.

## 4. What it rests on

Admission control and the budget (ADR-0005, with its three amendments, DEC-0012, DEC-0035); the one
breakdown and its two tables, money and Takt (ADR-0010); the `accounting` component, which meters
a run from its ledger entries; the organisation's structure from the identity component (`0.2.0`);
the views of UC-6.4; the protective rule of ADR-0015. Definition `UC-8.5`. Filed here although the
rest of E8 is migrated in step 3, because the migration's step 2 reconciles it with the decisions
that moved past it.

**What the accepted decisions supersede in the definition's text.** The requirement above is the
definition's; four parts of how the definition said it no longer hold, and each is kept here so
that what was once wanted stays readable:

- *"When a budget is exceeded, the configured policy applies."* Superseded by ADR-0005: a budget is
  held by admission before a step starts, not by a reaction after it was crossed. The policy applies
  at the line, and the only crossing left is the one inner step's overrun of the third amendment.
  The definition's policy "stop" is the halt at the boundary; its "throttle" is waiting for the next
  period; its "cheaper model" stands, within what the process allows; its "escalate" is the default.
- *"Consumption and cost in real time."* Holds for every kind reported per step. For money that a
  worker reports only when its assignment ends, the running figure is an estimate until then
  (ADR-0005, first amendment; DEC-0012).
- *A forecast as a point* — "92 % of the budget by the 24th". Superseded by ADR-0005, second
  amendment, point 5: a forecast names a band.
- *Cost as the one measure.* ADR-0010 makes money one of two tables over one breakdown, beside the
  Takt, and a budget in Takte is enforced only once the Takt is measured. A budget in a currency is
  converted into tokens when the run starts and held there; where a provider bills per time window,
  only a share of the window can be held, and the budget says so when it is set (ADR-0005, third
  amendment, point 5).

**Where the definition and the vision pull apart.** The definition lists a single person as a unit
for budgets. Principle 14 forbids any metric that appraises a named person. The condition above —
a person's consumption visible to that person, aggregated for everyone else — is the stricter
reading, and the owner is asked about it in DEC-0069.
