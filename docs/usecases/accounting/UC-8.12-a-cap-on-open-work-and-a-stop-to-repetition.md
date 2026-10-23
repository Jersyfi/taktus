---
id: UC-8.12
title: A cap on open work, and a stop to repetition
component: accounting
serves: [P8, P10, P12]
state: building
version: 0.5.0
tests: [tests/components/run/test_open_work.py::test_a_cap_of_two_with_two_open_pull_requests_finds_the_third_run_waiting, tests/components/run/test_open_work.py::test_a_run_in_flight_counts_until_it_ends, tests/components/run/test_open_work.py::test_a_run_that_passed_while_another_counted_is_counted_by_it, tests/governance/test_open_work_cap.py::test_a_process_that_raises_its_own_cap_is_refused_and_the_refusal_recorded, tests/governance/test_open_work_cap.py::test_a_person_changes_a_cap_and_is_named_as_its_actor, tests/components/run/test_repetition.py::test_the_same_outward_call_beyond_the_limit_is_stopped_at_its_boundary, tests/components/run/test_repetition.py::test_a_model_asked_again_without_a_tool_result_beyond_the_limit_is_stopped, tests/governance/test_open_work_cap.py::test_a_stop_raises_one_incident_that_names_the_action_the_count_and_the_limit]
adrs: {ADR-0005: 0ea928e2016b, ADR-0023: 949c6f4e13af, ADR-0043: 5bcc93809622}
supersedes: null
---

# UC-8.12 — A cap on open work, and a stop to repetition

## 1. What must be achieved

Two failures cost money without ever failing a run. A process that opens a pull request every
hour fills the review queue faster than anyone reads it. A step that repeats the same action in
a loop spends its budget on nothing.

Taktus prevents both. A process declares a **cap on its open work**: how many of its outcomes
may wait at once — open pull requests, started tasks, drafts awaiting release. While the cap is
reached, the process starts nothing new. A step that repeats the same outward action with the
same arguments beyond a limit is stopped at its boundary by rule.

## 2. How it is verified

- A process version can declare a cap per kind of open outcome. Admission counts the open
  outcomes from the connectors' records and the ledger, and admits no run that would start a new
  one while the cap is reached. The run waits and the wait is booked with its reason (ADR-0043).
  A test with a cap of two and two open pull requests finds the third run waiting, and admitted
  once one closes.
- Only a person changes a cap. A process or a worker that tries is refused, and the refusal is
  recorded.
- A step that calls the same connector action with the same arguments more often than the
  tenant's limit within one run is stopped at its next boundary. The stop names the action, the
  count and the limit, and raises an incident.
- A step whose model calls repeat without a new tool result between them beyond a limit is
  stopped in the same way.
- Both stops are rules over the ledger, never a model (ADR-0023).

## 3. Where the boundary lies

**Not a budget.** What a run may consume is UC-8.5 and ADR-0005; a cap counts outcomes, not
money. **Not concurrency.** How many runs a runner serves at once is admission and fairness
(#319). **Not a judgement of the work.** The cap does not ask whether the open outcomes are
good.

## 4. What it rests on

UC-03 B-11.03 and B-11.07; DEC-0199; NTC-0210. Admission control (ADR-0005); the rule-based
stop (ADR-0023); waiting booked to an account (ADR-0043).
