---
id: UC-4.17
title: Deadlines and response limits are rules of the process
component: process
serves: [P8, P10, P12]
state: building
version: 0.5.0
tests: [tests/components/process/test_deadlines_declared.py::test_a_deadline_without_an_action_does_not_register, tests/components/process/test_deadlines_declared.py::test_an_action_is_a_reminder_an_escalation_or_a_start_never_a_person, tests/integration/test_deadlines.py::test_a_deadline_started_before_a_restart_escalates_once_at_its_limit, tests/composition/test_deadlines.py::test_a_deadline_survives_a_restart_and_its_action_is_taken_once_on_time, tests/composition/test_deadlines.py::test_two_schedulers_that_both_believe_they_lead_take_the_action_once, tests/composition/test_deadlines.py::test_an_answer_one_minute_before_the_limit_prevents_the_escalation, tests/composition/test_deadlines.py::test_the_lead_reminds_and_the_limit_escalates_each_to_a_role_once, tests/composition/test_deadlines.py::test_a_deadline_in_working_time_counts_only_the_tenants_working_hours, tests/components/run/test_deadline_rules.py::test_working_time_counts_only_the_tenants_hours, tests/composition/test_deadlines.py::test_every_open_deadline_is_listed_by_when_it_falls_due, tests/composition/test_deadlines.py::test_a_deadline_from_a_date_starts_the_renewal_once_at_its_lead, tests/composition/test_deadlines.py::test_a_run_carries_its_versions_deadlines_and_a_rehearsal_starts_none]
adrs: {ADR-0015: 3a42705e5561, ADR-0035: 070012ed0fb2}
supersedes: null
---

# UC-4.17 — Deadlines and response limits are rules of the process

## 1. What must be achieved

Much of an operation is about time. A support case must be answered within a day. A data
protection request has a legal deadline. A certificate expires in thirty days. A release pull
request has waited too long. If every process keeps its own timer, a timer is lost with the
process that held it, and nobody sees all the deadlines at once.

A deadline is therefore declared in the process, beside its steps, and kept by Taktus. It
names what it is measured from, its limit, its lead time, and what happens when it is reached:
a reminder, an escalation to a role, or a start of a process. Taktus keeps every deadline across
restarts and shows every open one in one place.

## 2. How it is verified

- A process version can declare a deadline: the event or date it starts from, the limit, an
  optional lead time, and the action at lead time and at the limit. A deadline without an action
  does not register.
- A deadline survives a restart of every instance. A test starts a deadline, restarts the
  instance, and finds the action carried out once, at the right time.
- A deadline reached raises its action exactly once, recorded in the ledger with the deadline
  and the case it belongs to.
- An escalation names a role, never a person (UC-1.4, principle 14). Who holds the role is the
  organisation's structure.
- A deadline ends when the event that satisfies it happens, for example an answer in the case.
  A test answers the case one minute before the limit and finds no escalation.
- A deadline counts in calendar time or in the tenant's working time, as declared. Working
  time is the tenant's configuration, never a person's.
- Every open deadline of a tenant can be listed, ordered by when it falls due, with a link to
  its case.
- No deadline is kept in a worker or an outside timer. A process that needs one declares it.

## 3. Where the boundary lies

**Not a calendar or a task tool.** Taktus keeps the deadlines its processes declare; the
business's tasks stay in its own tool (UC-5.3). **Not a measure of how fast anyone answers.**
A missed limit is the case's and the role's, aggregated by role at most (principle 14,
ADR-0015). **Not legal advice.** Which deadline the law sets is the tenant's configuration.

## 4. What it rests on

Requirement 10 of the catalogue behind UC-03; UC-03 B-1.09, B-1.13, B-3.08, B-3.12, B-5.01,
B-6.05, B-8.07, B-10.01, B-10.06; DEC-0199; NTC-0210. Time triggers through the elected
scheduler (ADR-0035); a wait that parks the run (#320).
