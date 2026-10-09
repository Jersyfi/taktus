---
id: UC-8.10
title: Resources and performance — strict limits that do no harm
component: accounting
epic: E8
serves: [P8, P10, P12]
state: building
version: 0.5.0
tests: [tests/components/run/test_engine.py::test_a_step_that_does_not_fit_is_rejected_before_it_starts, tests/components/run/test_engine.py::test_a_stop_mid_step_lands_on_the_worker_s_boundary_and_resume_duplicates_nothing, tests/components/run/test_engine.py::test_a_rejected_run_resumes_with_a_raised_limit, tests/components/run/test_capacity_admission.py::test_admission_against_the_platform, tests/components/governance/test_capacity.py::test_the_owner_s_example_reads_as_a_figure_and_a_date]
adrs: {ADR-0005: c28377b9027e, ADR-0015: 3a42705e5561, ADR-0031: e81473d81850}
supersedes: null
---

# UC-8.10 — Resources and performance — strict limits that do no harm

## 1. What must be achieved

Taktus keeps its own performance in view. At any time it can be seen which resources a task or a
process needs — compute, model capacity, rate limits, storage — how much of them is in use, and which
limits apply to whom: the company, a department, a project team, a team, a person or a family,
inherited along the organisation's structure as budgets are. Every step is estimated before it
starts and starts only if it fits what remains, so that no limit is broken by stopping work but by
not starting it. Every process is atomic per step: a stop — by a limit, the emergency stop or a
person — takes effect at the next step boundary, and work resumes there after approval or a changed
limit. Taktus also watches whether a limit itself does harm — work that keeps waiting at it,
progress delayed, a critical process held up — and then tells whoever owns the limit which one, what
is held, and which change it recommends with its cost and benefit. The change is a person's
decision.

## 2. How it is verified

- Every step is estimated before it is admitted, or refused. It starts only if its reservation fits
  what remains of every line it is held to: the budget (ADR-0005) and the platform's free capacity
  (ADR-0031).
- No limit is exceeded by more than the overrun of the one inner step during which a running total
  crossed it, and that overrun is recorded. Both are provable from the ledger.
- At most one step of work is lost by a stop through a limit, the emergency stop, a person or an
  anchor. Work resumes at the boundary after approval or a raised limit, and nothing is duplicated.
- Limits are set per unit of the structure and inherited as budgets are (UC-8.5). A child's limit
  never admits a step its parent's would refuse.
- For a process or a run, Taktus shows the resources it needs, the current use, and every limit that
  applies with the unit it comes from. Before a run that needs much starts, its estimated demand is
  shown to the person who commissions it.
- A limit at which work is held more often or longer than a threshold the tenant configures produces
  a report to the limit's owner and in the views of the administrator, management and the team
  affected. It names the limit, the work held and for how long, and the change recommended with its
  cost and benefit. Whether a limit is harmful is decided by a rule over the ledger, never by a
  language model. Taktus never changes the limit itself.
- What a named person's limit held is visible to that person; anyone else sees it aggregated by
  role, team or department (UC-8.5).

## 3. Where the boundary lies

**Not budgets in money.** What a unit may spend is UC-8.5; this use case is about every kind of limit
and its health. **Not the platform's capacity itself**, which Taktus observes and does not create
(ADR-0031). **Not native pause.** A worker that can pause refines the granularity; the promise holds
without it (ADR-0005). **Not deciding a limit.** Changing one is a person's (M3.10 of
`docs/decisions/anchors.taktus.md` for this repository).

## 4. What it rests on

Step atomicity and admission (ADR-0005 with its three amendments, DEC-0012, DEC-0035); the platform
watch and admission against it (ADR-0031); blocked time per cause, which shows how long work waited
at a limit (ADR-0015); budgets per unit (UC-8.5); planning that breaks long work into steps (UC-1.2).
Definition `UC-8.10`. The version is `0.5.0`, whose completion criterion is that limit
recommendations come with numbers.

**What the accepted decisions supersede in the definition's text.**

- *"Not a single limit breach."* Superseded by ADR-0005, third amendment: the promise yields by at
  most the one inner step's overrun, which is recorded; the promise that at most one step of work is
  lost is the one kept whole.
- *"The estimate comes from the worker."* Every step is estimated, a worker by its own estimate, a
  language-model step by the input its model counts and the output limit it sets, a connector call
  by the demand its operation declares. A worker's estimate is reserved as its measured error scales
  it, and twice over while nothing has measured it (ADR-0005, third amendment, points 2, 4 and 6).
- *A limit for a single person.* Kept, read as UC-8.5 reads a budget for a person (DEC-0069).

## 5. What is proven so far

A step that does not fit is rejected before it starts; a stop lands on the
worker's boundary and a resume duplicates nothing; a rejected run resumes with a raised limit; a job
the platform cannot hold is refused; the platform's capacity is reported as a figure and a date —
by the named tests. Limits per unit and their inheritance, the view of what applies, and the reports
on harmful limits are not built.
