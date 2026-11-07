---
id: UC-9.5
title: Bottleneck and waiting analysis
component: accounting
epic: E9
serves: [P8, P14]
state: verified
version: 0.5.0
tests: [tests/components/run/test_blocked_time.py::test_a_block_of_each_cause_is_recorded_with_its_cause_and_its_duration, tests/components/run/test_blocked_time.py::test_blocked_time_and_share_sum_per_cause_process_and_period, tests/components/run/test_blocked_time.py::test_a_wait_on_a_person_is_readable_under_their_name_by_that_person_alone, tests/components/run/test_blocked_time.py::test_no_block_and_no_sum_has_a_field_that_can_hold_a_person, tests/components/run/test_blocked_time.py::test_a_sum_of_waits_answered_by_one_person_is_withheld_count_and_all, tests/components/accounting/test_bottlenecks.py::test_admission_says_by_how_much_each_quantity_did_not_fit, tests/components/accounting/test_bottlenecks.py::test_a_refusal_s_block_carries_its_shortfall_from_the_refusal_that_began_it, tests/components/accounting/test_bottlenecks.py::test_the_marginal_value_says_what_would_have_started_when_and_how_much_higher, tests/components/accounting/test_bottlenecks.py::test_money_is_marked_an_estimate_and_a_run_s_shortfalls_add_up, tests/components/accounting/test_bottlenecks.py::test_places_are_the_most_steps_waiting_at_capacity_at_one_moment, tests/components/accounting/test_bottlenecks.py::test_a_refusal_recorded_without_its_shortfall_is_named_and_not_guessed, tests/components/accounting/test_bottlenecks.py::test_a_raise_is_recommended_only_after_every_check_found_no_change_of_method, tests/components/accounting/test_bottlenecks.py::test_every_recommendation_names_effect_cost_value_and_the_check_of_its_steps, tests/components/accounting/test_bottlenecks.py::test_waits_on_people_are_summed_by_role_and_by_department_over_two_persons, tests/components/accounting/test_bottlenecks.py::test_a_role_or_department_one_person_answered_is_withheld_count_and_all, tests/components/accounting/test_bottlenecks.py::test_no_value_of_the_analysis_can_hold_a_person_and_none_is_ranked, tests/components/accounting/test_bottlenecks.py::test_each_of_the_four_ways_to_wait_less_on_people_is_offered_where_it_applies, tests/components/accounting/test_bottlenecks.py::test_the_command_line_prints_limits_advice_waits_and_offers, tests/governance/test_rules_from_precedent.py::test_a_retired_rule_answers_nothing]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: 0ea928e2016b, ADR-0010: e381de241d4a, ADR-0015: 3a42705e5561, ADR-0029: 37c061ef032a, ADR-0039: 6cb2c2f8d271, ADR-0043: 5bcc93809622, ADR-0084: b792ae358b77, ADR-0133: 325d5c255a47, ADR-0161: 80b8a7d53d72, ADR-0283: f8745cdc605f}
supersedes: null
---

# UC-9.5 — Bottleneck and waiting analysis

## 1. What must be achieved

Taktus works inside limits — a provider's rate limit, a subscription window, a budget, local compute,
and the time people take to answer. Every limit produces waiting. Taktus measures the waiting, says
which limit caused it and what work it held up, and answers the question every decision about a limit
turns on: what would a higher limit have bought? It answers from what it measured, not from a feeling.

A bottleneck is not always a reason to buy. Before proposing to raise a limit, Taktus checks whether
another method would remove the bottleneck at no extra cost.

Waiting on people is measured too, and that measurement belongs to the person who decides. It is never
turned into a measure of them.

## 2. How it is verified

- Every block of a run is recorded with its cause, its duration and the work it held up. The causes
  are the seven of ADR-0015: a provider's limit, a quota, a budget, compute, waiting on a person,
  waiting on an external state, waiting on another piece of work.
- The analysis sums blocked time and the share of the work blocked, per cause, per process and per
  period, from those records alone.
- The marginal value of a higher limit is computed from what admission control refused and why: what
  would have started, and when, had the limit been higher. It is exact for tokens, quota and compute,
  and marked as an estimate for money reported per assignment.
- Every recommendation names the expected effect, the cost and the value. A recommendation to raise a
  limit is made only after a change of method was checked and found not to remove the bottleneck at
  no extra cost (ADR-0004); the check is named in the recommendation.
- A decider's response times are visible to that decider alone by default. Anyone else sees them
  aggregated by role or department, never by person and never ranked. The rule is in the data model:
  a test fails when a figure of waiting on a person can be read by anyone else under that person's
  name (ADR-0015, principle 14).
- Each of the four ways to wait less on people can be offered — carry on with unblocked work, a
  deadline with a deputy, batching requests that are not urgent, turning a recurring decision into a
  rule — and a rule made from recurring decisions is the decider's, and can be withdrawn by them.

## 3. Where the boundary lies

**Not a block outside Taktus.** A person who did not start a run is not a block Taktus sees.
**Not buying.** Taktus recommends; raising a limit or a budget stays with whoever owns it.
**Not the blocked-time accounts themselves**, which the `run` component records as runs execute; this
use case is the analysis over them.

## 4. What it rests on

Measuring waiting and reporting marginal value (ADR-0015), with its protective rule; admission control
before every step (ADR-0005); the blocked-time accounts as the run engine keeps them (ADR-0043); method selection (ADR-0004); consumption and money (ADR-0010). Filed in
`accounting`, which owns forecasts and marginal value; the blocked-time accounts are `run`'s
(ADR-0029). Numbered in conversation after version 2 of the definition, in no version of it
(`NUMBERING.md`). The roadmap places the blocked-time accounts in `0.2.0` and the marginal-value
recommendations in `0.5.0`.

## 5. What is proven so far

The blocked-time accounts are built, as the `run` component records them (ADR-0043), and the
analysis over them, in `accounting` (ADR-0283). By the named tests:

- A block of each of the seven causes is recorded with its account, its cause, the run, the step
  and the process version it held up, and its duration; each cause once, none counted twice.
- Blocked time, the number of blocks, the runs and steps held up and the share of the runs held
  up sum per cause, per process and per period from the records alone, and equal what the test
  sums by hand from the blocks it produced.
- A refusal by admission records by how much each quantity did not fit, with the block it
  began. Per limit account and process the analysis reads what would have started — the steps
  and runs held up — and when: each step when it was refused, so many seconds sooner in all.
  The raise is per quantity: a run's shortfalls added up, the largest run's sum; places for
  compute at capacity, the most steps waiting at one moment. Tokens, quota, compute and places
  are exact, money is marked an estimate, and a cause whose record carries no shortfall is
  named, not guessed.
- Every recommendation names its expected effect, its cost and its value, and the check for a
  change of method of every step held up: the maturation candidacy (ADR-0084). A raise is
  recommended only where no step may change method; otherwise the change of method comes first.
- A wait on a person is in every block and every sum without the person's name, and readable
  under the name by that person alone; no block, sum, group or value of the analysis has a
  field that can hold a person. The waits on people are summed by role and by department, the
  department the answerer's, ordered by key; the analysis never reads a wait on a person one by
  one.
- A sum or a group of waits on a person that fewer than two persons answered is withheld, count
  and all: summed over one person, it would be that person's response time (NTC-0168).
- The four ways to wait less on people are offered where the records give a reason: carry on
  with the steps that do not depend on the awaited one (ADR-0039), a deadline that escalates to
  a deputy (ADR-0133), batching for a role with several waits in a period, and a rule from
  recurring decisions — the deciding role's, taking effect on a person's acceptance, retired by
  them, after which it answers nothing (ADR-0161). `taktusctl bottlenecks` prints all of it.

Not measured: a raise for a provider's rate limit, a unit's quota or budget, or the tenant's
monthly budget, whose records carry no shortfall. Batching is offered, not done: Taktus does not
hold a request back on its own.
