---
id: UC-9.1
title: The process controlling cockpit
component: value
epic: E9
serves: [P7, P8]
state: built
version: 0.5.0
tests: [tests/components/value/test_figures.py::test_the_cockpit_is_computed_from_the_ledger_and_recomputed_from_it_alone, tests/components/value/test_figures.py::test_a_rehearsal_is_no_work_and_a_result_corrected_twice_counts_once, tests/components/value/test_figures.py::test_a_simulation_is_marked_and_computed_from_the_decisions_people_took, tests/components/value/test_figures.py::test_a_figure_outside_its_target_is_a_proposal_naming_figure_target_and_runs, tests/adapters/rest/test_figures.py::test_once_a_role_holds_the_right_to_steer_only_its_holders_set_targets]
adrs: {ADR-0006: a5960785aee4, ADR-0010: e381de241d4a, ADR-0026: ccc4bd1f5423, ADR-0029: 37c061ef032a, ADR-0244: 0e3d5ef324fa, ADR-0293: fc2a083e6206}
supersedes: null
---

# UC-9.1 — The process controlling cockpit

## 1. What must be achieved

Running processes gets a controlling layer. Every process has its figures — cycle time, quality,
cost, degree of automation, rate of escalation — with targets against actuals, trends, and
simulations such as "what happens if we allow autonomy level 3?". With them the business can be
steered precisely, not by feel.

The figures agree with the activity log: there are never two truths. Targets can be set per process,
and a deviation from a target produces a proposal of what to do.

## 2. How it is verified

- Each of the five figures is computed from the ledger and the records it references (ADR-0006), and
  has one definition wherever it is shown (ADR-0029). A test recomputes them from the ledger alone and
  finds the same values.
- Cost is shown in Takt and in money as accounting records them (ADR-0010), never in a third unit.
- A target can be set for each figure of each process, by a person with the right to steer the
  process. A figure outside its target produces a proposal (UC-4.4) that names the figure, the target,
  the period and the runs behind it.
- A simulation names the records it starts from and every assumption it makes, and is marked as a
  simulation wherever it is shown. A simulation of a higher autonomy level is computed from the
  decisions people actually took at the current level — how many were approved unchanged, how many
  changed, how many refused. A simulation changes nothing: raising autonomy stays the act of the
  process's owner (UC-15.5, ADR-0026).
- No figure of the cockpit is broken down by named person (principle 14).
- Every figure of the cockpit is in the export (UC-5.7).

## 3. Where the boundary lies

**Not the value balance**, which weighs cost against benefit and is UC-9.3. **Not the bottleneck
analysis**, which is UC-9.5. **Not a forecast tool.** A simulation answers a question from recorded
behaviour; it does not predict the market or the organisation. **Not the view.** Who sees the cockpit
is UC-6.4.

## 4. What it rests on

The ledger as the single source of every metric (ADR-0006); consumption in Takt and money (ADR-0010);
the autonomy statement and how a raise is proposed (ADR-0026); proposals (UC-4.4); the responsibility
anchor (UC-15.5); views and export (UC-6.4, UC-5.7). Filed in `value` with E9 (ADR-0029 files figures
with their owner). Definition `UC-9.1`. The roadmap's `0.5.0`.

## 5. What is proven so far

Built (ADR-0244). By the named tests: the five figures are computed from the ledger and found
again when recomputed from it alone; cost is read from accounting in money and Takt; a figure
outside its target is a proposal naming figure, target, period and runs; a simulation of the
next level is marked and computed from the decisions people took. Targets are set by a role
holding the right `process.steer` (ADR-0293): a role without it is refused with the right named,
one with it sets them; while no role of the tenant holds it, `owner` sets them, as NTC-0270
recorded.
