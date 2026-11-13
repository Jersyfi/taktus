---
id: UC-8.10
title: Resources and performance — strict limits that do no harm
component: accounting
epic: E8
serves: [P8, P10, P12]
state: verified
version: 0.5.0
tests: [tests/components/run/test_engine.py::test_a_step_that_does_not_fit_is_rejected_before_it_starts, tests/components/run/test_engine.py::test_a_stop_mid_step_lands_on_the_worker_s_boundary_and_resume_duplicates_nothing, tests/components/run/test_engine.py::test_a_rejected_run_resumes_with_a_raised_limit, tests/components/run/test_capacity_admission.py::test_admission_against_the_platform, tests/components/governance/test_capacity.py::test_the_owner_s_example_reads_as_a_figure_and_a_date, tests/components/run/test_unit_limits.py::test_a_step_that_does_not_fit_a_team_s_limit_is_refused_before_it_starts, tests/components/run/test_unit_limits.py::test_a_child_never_lets_a_step_through_its_parent, tests/components/run/test_unit_limits.py::test_the_company_s_limit_holds_every_unit_below_it, tests/components/run/test_unit_limits.py::test_a_limit_that_holds_too_many_runs_is_reported_with_a_recommendation, tests/components/run/test_unit_limits.py::test_a_limit_held_per_person_tells_no_role_and_names_no_one, tests/components/run/test_unit_limits.py::test_what_applies_to_a_run_names_every_limit_with_its_unit, tests/components/governance/test_unit_limits.py::test_a_limit_does_harm_where_it_held_more_runs_or_longer_than_the_watch, tests/components/governance/test_unit_limits.py::test_a_limit_held_per_person_raises_no_alert_to_a_role, tests/integration/test_units_command.py::test_an_operator_sets_a_unit_limit_watches_it_and_sees_its_consumption, tests/components/run/test_unit_limits.py::test_two_runners_admitting_against_one_limit_at_once_never_cross_it, tests/components/run/test_run_demand.py::test_a_run_that_needs_much_shows_its_demand_before_it_starts, tests/components/run/test_run_demand.py::test_a_run_no_person_commissions_is_not_asked, tests/components/run/test_run_demand.py::test_the_demand_shown_counts_only_the_person_s_own_runs_against_a_limit_per_person, tests/adapters/rest/test_limit_figures.py::test_a_limit_s_harm_report_is_in_the_views_of_administration_management_and_team, tests/adapters/rest/test_start_demand.py::test_a_web_start_that_needs_much_shows_its_demand_and_starts_once_accepted, tests/composition/test_composed_case_from_a_description.py::test_a_describe_run_that_needs_much_shows_its_demand_before_it_is_commissioned, tests/composition/test_catalogue_in_channel.py::test_a_start_that_needs_much_says_its_demand_and_the_yes_accepts_it]
adrs: {ADR-0005: 0ea928e2016b, ADR-0015: 3a42705e5561, ADR-0031: e81473d81850, ADR-0282: c98f98a54368, ADR-0298: 0e99d1d289d8, ADR-0299: e26cb101b51c}
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
by the named tests.

Limits per unit of the structure and their inheritance (ADR-0282), by the named tests: a limit
in money, compute seconds or tokens for the company, a department, a team, or each person of a
unit on their own, holds
every run on its path, and a child never admits a step its parent refuses. `taktusctl units
applies` shows, for a run or a process, what it needs — its budget, every step's reservation,
or for a process what its runs of the month cost on average and at most — what it used, and
every limit that holds it with the unit it comes from: the run's own budget, every unit limit
with its period's cost and what remains, the department's quota and the tenant's monthly budget.
A limit at which more runs, or longer, were held than the tenant's watch allows is reported to
the limit's role as `limit.harmful`, by a rule over the ledger entries `unit_limit.held` and
`unit_limit.released`: the limit, the runs, processes and seconds held, and the amount
recommended with its cost per period and its benefit. Taktus never changes the limit. What
one person's runs used against a limit held per person is shown only to that person.

Two runners admitting against one limit at once no longer both fit it: the admission is
checked again under the limit's claim before it commits (ADR-0298 §1), by the named test.

The estimated demand before a run starts (ADR-0299 §1), by the named tests in
`test_run_demand.py`: the mean of the process's runs of 28 days, or the run's budget where it
has none, against what remains of every unit limit on the run's path. A run a person
commissions that needs much — its estimate reaches half of what remains of a limit — is refused
with its demand and starts once the person accepts it; nothing is written before. `taktusctl
run` and `submit` print it and take `--accept-demand`. Against a limit held per person only the
person's own runs count. The harm report is also in the views (ADR-0299 §2), by the named test
in `test_limit_figures.py`: the figure `limit.held_seconds`, of the limit's unit for the views of
the administrator and the team affected, and of each process it held for the views grouped by
process, with the limit, the work held, the change recommended, its cost and its benefit, and
no person named; the default views `administration`, `management` and `team` show it.

Every surface where a person starts or commissions a run shows the demand first (ADR-0299 §1),
by the named tests: a start from the web app's catalogue or a person's agent is refused with
409 and the demand, and starts with the acceptance; commissioning a plan in the dialogue that
starts the describe run is refused with its demand and nothing is commissioned until it is
accepted; a start in the owner's conversation says the demand in the reading, and the person's
yes accepts it. Every condition of section 2 is met by the named tests; the state is
`verified`.
