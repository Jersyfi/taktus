---
id: UC-7.11
title: Departments share the runners fairly and hold their quotas
component: governance
epic: E7
serves: [P8, P12, P14]
state: built
version: 0.7.0
tests: [tests/components/run/test_org_units.py::test_a_unit_s_run_starts_within_two_polls_behind_another_unit_s_two_hundred, tests/components/run/test_org_units.py::test_a_run_carries_its_unit_and_its_job_does, tests/components/run/test_org_units.py::test_a_unit_s_concurrent_quota_holds_and_its_wait_is_booked_as_a_block, tests/components/run/test_org_units.py::test_a_unit_s_budget_quota_holds_and_its_refusal_is_booked_as_a_block, tests/components/run/test_org_units.py::test_a_run_without_an_amount_in_the_quota_s_currency_halts_for_a_person, tests/components/run/test_org_units.py::test_without_quotas_a_tenant_s_units_run_as_before, tests/components/run/test_org_units.py::test_a_rehearsal_commits_nothing_to_a_budget_quota, tests/adapters/queue/test_org_units.py::test_a_unit_that_holds_no_place_comes_before_one_with_much_queued, tests/adapters/queue/test_org_units.py::test_a_unit_at_its_limit_is_skipped_and_its_jobs_are_marked_held, tests/adapters/queue/test_org_units.py::test_a_limit_holds_against_runners_claiming_at_once, tests/adapters/queue/test_org_unit_spends.py::test_commits_at_once_never_cross_the_limit_together, tests/components/governance/test_org_units.py::test_a_quota_is_never_set_on_a_person, tests/components/governance/test_org_units.py::test_a_tenant_without_quotas_holds_none_and_the_run_sees_none]
adrs: {ADR-0005: 0ea928e2016b, ADR-0020: e42a9501e3b5, ADR-0043: 5bcc93809622, ADR-0166: ae0b6e9dc6ae}
supersedes: null
---

# UC-7.11 — Departments share the runners fairly and hold their quotas

## 1. What must be achieved

Several departments of one organisation run their processes on the same instance. One
department's large batch must not keep another department's single run waiting. A run carries
the organisational unit it runs for, and the runners share their places fairly between units.
A tenant may set quotas per unit: how many of its runs hold a place at once, and how much money
its runs may commit in a month. A quota limits a unit, never a person. A tenant that sets none
behaves as before.

## 2. How it is verified

- A run carries the unit its command was given in, the department below the tenant, and its job
  carries it too. The unit never comes from the identity on whose behalf the run acts.
- With unit A holding 200 queued runs, unit B's run starts within two poll intervals.
- A unit's limit of concurrent runs holds across every runner claiming at once. Another unit's
  runs are not held by it.
- A unit's monthly budget holds: the amounts its runs commit never add up to more, also when two
  runs commit at once.
- Every refusal by a quota is booked as a block with its account and its duration: `limit.quota`
  for concurrent runs, `limit.budget` for the budget (ADR-0043).
- Quotas are per unit, never per person: a quota on a name that is an identity of the tenant is
  refused (principle 14).
- Without quotas a tenant behaves as today: nothing is held, nothing is committed, and nothing
  of a quota is recorded.

## 3. Where the boundary lies

**Not visibility per unit.** Who sees what of a unit is UC-6.4. **Not cost control.** Budgets
inherited along the structure, alerts and forecasts are UC-8.5. **Not fairness between teams.**
Teams and projects share their department's places.

## 4. What it rests on

Tenants and the organisation's structure (ADR-0020, UC-1.4); admission control, which holds a
run to its budget (ADR-0005); every block booked to an account (ADR-0043); the fair claim round
between tenants (#319). ADR-0166 builds it. Measured on 2026-10-12: department A's 200 queued
runs kept department B's one run waiting 50.6 s (`docs/research/2026-10-12-devops-review.md`
§T3, DEC-0187). Issue #343; NTC-0254 records the readings it settles. Written in the branch that builds package C (DEC-0222), beside its
implementation.

## 5. What is proven so far

Every condition of §2 by the named tests, in memory and, for the queue and the store of what
was committed, in PostgreSQL: the unit on run and job, unit B's run within two polls behind A's
two hundred, the concurrent limit under runners claiming at once, the budget under commits at
once, both refusals booked as blocks, the refusal of a quota on a person, and a tenant without
quotas behaving as before.
