---
id: UC-4.24
title: Taktus proposes a cheaper method for a step
component: process
epic: E4
serves: [P2, P8, P10, P14]
state: building
version: 0.4.0
tests: [tests/components/run/test_maturation.py::test_a_steps_measures_are_read_back_from_the_run_history_it_wrote, tests/components/run/test_maturation.py::test_a_step_without_a_price_is_measured_and_its_cost_is_unpriced, tests/components/run/test_maturation.py::test_a_step_with_500_cases_and_20_in_every_class_is_a_candidate, tests/components/run/test_maturation.py::test_499_cases_or_one_class_at_19_is_no_candidate, tests/components/run/test_maturation.py::test_more_than_50_classes_another_method_or_no_numbers_is_no_candidate, tests/components/run/test_maturation.py::test_the_held_out_cases_are_a_fifth_of_every_class_drawn_the_same_every_time, tests/components/run/test_maturation.py::test_a_proposal_needs_95_percent_a_lower_cost_and_the_same_model_twice, tests/components/run/test_maturation.py::test_a_candidate_is_trained_tried_and_proposed_to_a_person, tests/components/run/test_maturation.py::test_asked_as_a_change_within_the_frame_it_is_proposed_and_nothing_is_registered, tests/components/run/test_maturation.py::test_an_agreement_of_94_percent_or_an_equal_cost_proposes_nothing, tests/integration/test_maturation_command.py::test_the_measures_are_read_back_and_a_correction_counts_without_naming_anyone, tests/composition/test_method_move.py::test_accepting_the_proposal_registers_a_version_with_the_step_on_the_trained_model, tests/composition/test_method_move.py::test_nothing_is_moved_before_a_person_accepts_or_when_the_answer_keeps_the_step, tests/composition/test_method_move.py::test_a_version_without_the_models_evaluation_is_refused, tests/composition/test_method_move.py::test_a_sure_case_is_answered_by_the_model_and_an_unsure_one_by_the_llm, tests/composition/test_method_move.py::test_over_its_first_100_cases_a_move_is_measured_beside_the_version_it_replaced, tests/composition/test_method_move.py::test_a_move_that_is_not_cheaper_is_reported_with_a_proposal_to_roll_back, tests/composition/test_method_move.py::test_rolling_back_makes_the_predecessor_current_again_as_a_new_version, tests/workers/test_maturation_on_the_bench.py::test_a_step_on_a_language_model_is_proposed_a_model_the_bench_trained, tests/workers/test_maturation_on_the_bench.py::test_the_accepted_move_runs_on_the_bench_reproducibly_and_measurably_cheaper]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0026: ccc4bd1f5423, ADR-0076: 0fce968725a4, ADR-0084: a3b606b10fa0, ADR-0114: c9fd2e73c6ba}
supersedes: null
---

# UC-4.24 — Taktus proposes a cheaper method for a step

## 1. What must be achieved

A step that runs on a language model may do a job a trained classifier could do as well, more
cheaply and reproducibly. Taktus finds such a step from what it already records, trains the
cheaper method, and shows the evidence to a person. The person decides. A move the person
accepts becomes a new version of the process, and Taktus then measures whether the move kept its
promise.

The requirements, numbered as the owner set them in DEC-0164:

1. **Measured per step, never per person.** For every step, Taktus measures from what it already
   records: cost per case, duration, how often a person corrected the result, and how much
   results spread. The measures belong to the step; none names a person (principle 14).
2. **A proposal only on evidence.** Taktus proposes to move a step from a language model to a
   trained classifier only when all of this holds: the step's results fall into a fixed set of
   at most 50 classes; there are at least 500 labelled cases and at least 20 in every class; a
   classifier trained by the ML bench on them agrees with the labels on at least 95 % of 20 %
   held-out cases; its measured cost per case is lower than the language model's measured cost
   per case; and training it twice on the same cases gives the same model, byte for byte.
3. **The proposal is a decision request.** It states the step; the number of cases and the
   classes; the agreement on held-out cases; the cost per case of both methods, measured; the
   exactness class the move would allow; the confidence threshold the new step would fall back
   at; and the model by version and digest. It is raised to whoever owns the process. Asked to
   make the move as a change within the frame, Taktus raises the proposal and makes no new
   version (UC-4.3).
4. **An accepted proposal is a new version.** The step runs on the trained model, pinned. Below
   the confidence threshold it falls back to the language model it ran on before, so that an
   unsure case is handled as it was. The new version registers only if the model's evaluation
   on the held-out cases is part of it, and it can be rolled back in one act (UC-4.3).
5. **The move is measured afterwards.** Over the first 100 cases on the new version, Taktus
   reports the cost per case and the share of cases that fell back, beside the old version's.
   A move whose cost per case did not fall is reported as such, with the proposal to roll back.

## 2. How it is verified

- **Requirement 1.** A test runs a step and reads back its cost per case, its duration, its
  correction rate and the spread of its results from the records the runs wrote. No measure
  carries an identity of a person, and a correction counts without naming who made it.
- **Requirement 2.** A step at 500 cases with 20 in every class is a candidate; a step at 499
  cases, with one class at 19 cases or with more than 50 classes is not. A candidate whose
  classifier agrees on 94 % of the held-out cases, or costs as much per case as the language
  model, or gives two different models from two trainings on the same cases, is proposed nothing.
  The held-out cases are a fifth of the cases, drawn the same way every time.
- **Requirement 3.** A proposal is a decision request to the process's owner, and it carries
  every item the requirement lists. Asked as a change within the frame, Taktus raises the
  proposal, and no version is registered.
- **Requirement 4.** Nothing moves before a person accepts. An accepted proposal registers a new
  version in which the step runs on the trained model, pinned by version and digest; the version
  it replaces stays registered and unchanged. A version without the model's evaluation on the
  held-out cases is refused. In a run of the new version, a case below the threshold is answered
  by the language model and its result says so; a case at or above it is answered by the trained
  model. Rolling back is one act, and it makes the predecessor current again as a new version.
- **Requirement 5.** Over the first 100 cases on the new version, the report gives the cost per
  case and the share that fell back, beside the replaced version's cost per case. A move that
  is not cheaper is reported as such, with a proposal to roll back.
- **Never.** Taktus never applies a move without a person, at any autonomy level.

## 3. Where the boundary lies

**Not neural models or embeddings** (#210). **Not a move from a trained model to a fixed rule**,
which comes later. **Not training on anything that describes how a person works.** **Not the
model hub** (UC-8.6). **Not a move applied without a person**, at any autonomy level.

## 4. What it rests on

Method selection and its observation (ADR-0004, `docs/architecture/methods.md` §2 and §3); a
step of method `ml` on the ML bench, pinned by digest, with its fallback (ADR-0076, issue #216);
the autonomy statement, which keeps a change of a step's method with a person (ADR-0026);
Taktus's own changes within the frame and their rollback (UC-4.3); a repeatable step and a change
of model that registers only with an evaluation (UC-8.4); the decision request (UC-7.4). ADR-0084
builds requirements 1 to 3 (issue #217); ADR-0114 builds requirements 4 and 5 (issue #218). The
roadmap's `0.4.0` is complete when a step was moved from a language model to a trained model on
Taktus's own proposal, measurably cheaper and reproducible. Put to the owner in DEC-0164, who set
these requirements with Option A on 2026-11-03.

## 5. What is proven so far

By the named tests: a step's measures are read back from the run history it wrote, a step
without a price is measured with its cost unpriced, and a correction counts without naming
anyone. The floor of requirement 2 holds at its edges — 500 cases and 20 in every class, at most
50 classes — and the held-out fifth is drawn the same way every time; a proposal needs 95 %
agreement, a lower cost and the same model from both trainings. A candidate is trained, tried and
proposed to a person as a decision request; asked as a change within the frame, it is proposed
and nothing is registered. An accepted proposal registers a version with the step on the trained
model, nothing moves before a person accepts, and a version without the model's evaluation is
refused. A sure case is answered by the model and an unsure one by the language model. Over the
first 100 cases a move is measured beside the version it replaced, a move that is not cheaper is
reported with a proposal to roll back, and a rollback makes the predecessor current again as a
new version. Against the ML bench itself, a step on a language model is proposed a model the
bench trained, and the accepted move runs reproducibly and measurably cheaper.

Not yet: a move on a step of a process Taktus runs. Every language-model step of Taktus's own
bundles reads text, and a candidate learns from numbers only until embeddings exist (#210); the
roadmap's `0.4.0` criterion waits for it (#218).
