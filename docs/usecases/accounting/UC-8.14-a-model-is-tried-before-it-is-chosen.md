---
id: UC-8.14
title: A model is tried on fixed cases before it is introduced, proposed or changed
component: accounting
epic: E8
serves: [P2, P3, P8, P13]
state: built
version: 0.4.0
tests: [tests/components/run/test_model_routing.py::test_a_run_that_binds_its_purpose_routes_it_to_that_model_alone, tests/components/run/test_model_routing.py::test_a_bound_model_that_does_not_fit_fails_the_step_and_moves_nowhere, tests/composition/test_trials.py::test_a_trial_runs_each_case_once_per_candidate_and_sets_them_side_by_side, tests/composition/test_trials.py::test_a_trial_binds_nothing_beyond_its_own_runs, tests/composition/test_trials.py::test_a_trial_is_offered_when_a_purpose_s_model_has_answered_nothing_yet, tests/composition/test_trials.py::test_a_trial_is_offered_when_taktus_proposes_another_model, tests/composition/test_trials.py::test_a_trial_is_offered_when_the_model_a_member_answers_as_changes_version, tests/adapters/rest/test_spend_and_trials.py::test_a_trial_is_started_for_the_key_s_identity_read_and_offered, tests/components/accounting/test_trials.py::test_each_candidate_is_reported_per_case_and_in_total]
adrs: {ADR-0030: 232318604b2d, ADR-0116: fdaf116b5e47, ADR-0134: 326ba91bbdcb, ADR-0148: 4ba172a497c9, ADR-0149: 6019b024ced9}
supersedes: null
---

# UC-8.14 — A model is tried on fixed cases before it is introduced, proposed or changed

## 1. What must be achieved

Before a model is introduced for a purpose, proposed by Taktus, or changed — another level of
one provider, another provider at the same level, a new version of the same model — Taktus
offers a trial: the same task run with each candidate, their results and their cost set side by
side, so that a person decides on evidence. Choosing the model stays the person's act.

## 2. How it is verified

- For a purpose, a trial runs a fixed set of cases with each candidate model, each case as a
  rehearsal that acts on nothing outside, with the purpose bound to the candidate for that run
  alone. Every other run, and every other purpose of the same run, routes as configured.
- The report states per candidate the cases passed, money, tokens in and out, wall time, and
  each case's results beside the other candidates'; the cases whose results differ are named.
- A trial is offered when a model is first bound to a purpose, when Taktus proposes another,
  and when the version of the model a provider reports changes. An offer is never started on
  its own.
- After a trial, no model is bound to the purpose that was not bound before it.
- The web app lists the offers and the trials, starts a trial, and shows its report.
- A trial's records name no person beside a figure (principle 14).

## 3. Where the boundary lies

- Not automatic switching: routing between models is #328 and a person's decision (M3.14).
- A trial compares what its cases exercise; a candidate that passes them may fail elsewhere.
- A difference only a live outward call would show is not seen: a rehearsal answers from
  recordings.

## 4. What it rests on

ADR-0149 and its amendment of 2026-10-28; ADR-0116 (a purpose's chain and its route);
ADR-0134 (evaluation cases); ADR-0030 (rehearsal); ADR-0148 (the figures of a run). Issue #448,
DEC-0200 answer 2.

## 5. What is proven so far

The named tests prove a purpose bound for one run, a bound model that does not fit, a trial
over the evaluation cases with its report, that a trial binds nothing beyond its runs, the three
offers, and the HTTP surface. The web app's pages are proven by `web/src/lib/spend.test.ts`.
Nothing in the instance proposes a model yet, so the `proposed` offer appears only where a
caller records the proposal; the cases a person names beside the evaluation cases are not built.
