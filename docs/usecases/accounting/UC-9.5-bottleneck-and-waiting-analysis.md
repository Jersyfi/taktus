---
id: UC-9.5
title: Bottleneck and waiting analysis
component: accounting
epic: E9
serves: [P8, P14]
state: building
version: 0.5.0
tests: [tests/components/run/test_blocked_time.py::test_a_block_of_each_cause_is_recorded_with_its_cause_and_its_duration, tests/components/run/test_blocked_time.py::test_blocked_time_and_share_sum_per_cause_process_and_period, tests/components/run/test_blocked_time.py::test_a_wait_on_a_person_is_readable_under_their_name_by_that_person_alone, tests/components/run/test_blocked_time.py::test_no_block_and_no_sum_has_a_field_that_can_hold_a_person]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: c28377b9027e, ADR-0010: 6b161e3f6831, ADR-0015: 3a42705e5561, ADR-0029: 37c061ef032a, ADR-0043: fe6020be8643}
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

The blocked-time accounts are built, as the `run` component records them (ADR-0043). The analysis
over them is not. By the named tests:

- A block of each of the seven causes is recorded with its account, its cause, the run, the step
  and the process version it held up, and its duration; each cause once, none counted twice.
- Blocked time, the number of blocks, the runs and steps held up and the share of the runs held
  up sum per cause, per process and per period from the records alone, and equal what the test
  sums by hand from the blocks it produced.
- A wait on a person is in every block and every sum without the person's name, and readable
  under the name by that person alone; no block and no sum has a field that can hold a person.

Not yet: the marginal value of a higher limit, the recommendations and the check for a change of
method, and the four ways to wait less on people (`0.5.0`). A wait on an anchor's decision carries
the role it is addressed to; the sums are not split by role or department yet.
