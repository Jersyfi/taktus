---
id: UC-4.4
title: Taktus proposes processes
component: process
epic: E4
serves: [P2, P9, P14]
state: built
version: 0.6.0
tests: [tests/composition/test_skills.py::test_corrections_that_recur_at_one_step_become_a_draft_that_names_no_person, tests/composition/test_skills.py::test_a_skill_that_no_using_process_can_evaluate_stays_a_draft, tests/composition/test_process_proposals.py::test_a_process_started_by_hand_every_week_is_proposed_to_that_person_only, tests/composition/test_process_proposals.py::test_an_irregular_rhythm_or_two_starts_are_not_proposed, tests/composition/test_process_proposals.py::test_a_failure_healed_again_and_again_is_an_improvement_proposal_everyone_sees, tests/composition/test_process_proposals.py::test_the_list_is_ordered_by_how_often_the_work_recurs_and_says_so, tests/composition/test_process_proposals.py::test_each_is_accepted_or_declined_on_its_own_and_accepting_builds_a_proposal, tests/composition/test_process_proposals.py::test_only_the_person_a_proposal_is_shown_to_may_decide_it_and_only_once]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0015: 3a42705e5561, ADR-0162: 543844829afb, ADR-0251: aad75bb537be, ADR-0270: 970ca723e2d7}
supersedes: null
---

# UC-4.4 — Taktus proposes processes

## 1. What must be achieved

Taktus advises. It notices where work could be automated and says so, unasked: "you do this by
hand every week — shall I take it over?" Its proposals are short, ordered by priority, and each can
be accepted on its own. A way of working that recurs in what was proposed and in what people
corrected becomes a draft skill, which enters the skill lifecycle like any other.

## 2. How it is verified

- A proposal states the work it would take over, what it would cost to run, and why it is
  proposed now, and nothing else.
- Proposals are delivered as a list ordered by priority, and the reason for the order is shown.
- Each proposal is accepted or declined on its own. Accepting one starts building a process from
  it (UC-4.1); nothing runs for real before the person commissions it.
- A procedure that recurs in accepted proposals and in corrections people made becomes a draft
  skill. A draft skill never reaches production directly: it enters the skill lifecycle, and only
  passed evaluations take it further (UC-14.2).
- A proposal drawn from a person's own work is shown to that person only. Nothing about a person's
  behaviour enters a skill: a draft skill describes a procedure of a process, never how a named
  person works (principle 14).

## 3. Where the boundary lies

**Not a change of an existing process.** Changing a process that runs is UC-4.3; proposing a
cheaper method for a step is ADR-0004's maturation. **Not process discovery from the
organisation's systems.** Finding processes in data nobody described is definition `UC-9.4`.
**Not the automation coach.** Helping a person learn to use automation is `UC-13.3`, which may draw
on these proposals. **No obligation.** A declined proposal costs nothing and changes nothing.

## 4. What it rests on

UC-4.1, which builds a process from an accepted proposal; the skill lifecycle (`UC-14.2`, migrated
in step 3, roadmap `0.6.0`); method selection (ADR-0004); the protective rule that what concerns a
person belongs to that person (ADR-0015, principle 14). The version is `0.6.0`, where the skill
lifecycle arrives; proposals without draft skills could come earlier, and the roadmap does not name
them. Definition `UC-4.4`.

## 5. What is proven so far

A step corrected in at least three distinct runs — `step.corrected`, or a proposal decided as
corrected — becomes a draft skill, once, whose origin names the runs and the step and no person
(ADR-0162 §8). A draft enters the skill lifecycle and goes no further without a passed round.
Proposals of processes are found by rule in the ledger (ADR-0270): a process a person starts
by hand at a regular cadence, and a failure healed its limit of times (UC-4.6). Each says the
work it would take over, its cost from what the runs it draws on consumed, and why now; the list
is ordered by how often the work recurs per 30 days, and each proposal says so. Each is accepted
or declined on its own; an accepted one is handed to the request path that builds a proposal of
a version (UC-4.1, ADR-0251), which only a person commissions. A proposal drawn from runs a
person started is shown to that person alone — by the named tests. The list and its acts are a
service of the composition; a page of the web app and a command in the channel for them are not
built, which is why the state is `built`.
