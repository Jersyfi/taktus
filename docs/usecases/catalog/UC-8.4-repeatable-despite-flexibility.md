---
id: UC-8.4
title: Repeatable despite flexibility
component: catalog
epic: E8
serves: [P8]
state: building
version: 0.4.0
tests: [tests/components/run/test_llm_steps.py::test_an_answer_that_fails_the_check_does_not_leave_the_step, tests/composition/test_method_move.py::test_a_version_without_the_models_evaluation_is_refused, tests/composition/test_method_move.py::test_the_same_case_on_the_moved_step_gives_the_same_result, tests/composition/test_evaluations.py::test_a_variable_step_declares_its_tolerance_within_what_its_class_admits, tests/composition/test_evaluations.py::test_a_step_is_held_to_its_own_tolerance_where_the_tenant_s_is_wider, tests/composition/test_evaluations.py::test_a_regression_is_not_commissioned_unless_a_person_overrides_it_with_a_reason, tests/composition/test_evaluations.py::test_drift_is_measured_on_the_schedule_and_raises_an_incident_where_it_speaks_out, tests/composition/test_skills.py::test_a_regressing_skill_is_not_evaluated_and_a_worse_one_falls_back_by_rule, tests/composition/test_model_validation.py::test_a_replacement_reaches_real_runs_only_after_its_validation_run_held, tests/components/process/test_tolerances.py::test_a_variable_step_without_cases_declares_its_tolerance_beside_the_steps, tests/components/process/test_tolerances.py::test_a_tolerance_beside_the_steps_is_held_within_its_class_and_to_a_variable_step, tests/components/process/test_tolerances.py::test_the_declaration_is_held_once_a_scorer_scores_the_step, tests/composition/test_evaluations.py::test_a_drift_of_a_process_that_sends_nothing_outward_is_raised_as_a_finding]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: 0ea928e2016b, ADR-0011: f25413d512b9, ADR-0014: 6611f7833deb, ADR-0018: 17c99e0eaa3c, ADR-0114: 75a031083f19, ADR-0134: 49496fd840aa, ADR-0162: 543844829afb, ADR-0249: 96644d826d42, ADR-0250: 31261db30459, ADR-0300: eb9fcb2fa1f6}
supersedes: null
---

# UC-8.4 — Repeatable despite flexibility

## 1. What must be achieved

Models give varying answers by nature. Taktus uses them efficiently and repeatably all the same:
prompts and configurations are versioned, outputs have a structure that is checked, a change of
prompt, model or skill is evaluated automatically against earlier results, settings are
deterministic where that makes sense, and room for creativity is defined where a task needs it.
The same task under the same configuration gives an equivalent result within a stated tolerance,
and the flexibility of the dialogue with a person is kept whole.

## 2. How it is verified

- Every prompt and every model setting is part of the process version (ADR-0011). Every run names
  the version it ran.
- A variable step declares the structure of its output, and an answer that does not pass the step's
  check does not leave the step.
- Every variable step declares its tolerance — what counts as an equivalent result. Its exactness
  class bounds how wide the tolerance may be (ADR-0014), and room for creativity exists only where
  the step's class is `free`.
- A change of model, prompt or skill used by a step registers only with an evaluation over the
  step's evaluation set, within the declared tolerance. A change that fails stays out of production.
- Evaluations run inside Taktus. A connected evaluation platform may keep a copy (UC-5.8); removing
  it changes nothing in what is evaluated.
- Running a step's evaluation set again under an unchanged configuration stays within its
  tolerance. A drift beyond it is a finding of deviation detection (UC-4.10).

## 3. Where the boundary lies

**Not identical answers.** A variable method repeats within its tolerance; replaying a run repeats
the sequence of steps, not the answers (ADR-0005). **Not choosing a cheaper method**, which is
method selection (ADR-0004). **Not the dialogue.** Planning with a person (UC-1.2) is not held to a
tolerance.

## 4. What it rests on

Process versions as bundles (ADR-0011); exactness classes (ADR-0014, ADR-0018); method selection
(ADR-0004); step atomicity and replay (ADR-0005); deviation detection (UC-4.10). Definition `UC-8.4`.
The version is `0.4.0`, where a step moves to a trained model on Taktus's own proposal and the move
must be evaluated.

## 5. What is proven so far

An answer that fails its step's check does not leave the step, by the named test. A change of
model registers only with an evaluation: a step on a trained model is refused without its
model's evaluation on held-out cases, with one of another file, or with one below the agreement
a proposal is raised on (ADR-0114). The same case on a pinned model gives the same result.

Every variable step a process's evaluation scores declares its tolerance, and registration
refuses one wider than the step's class admits: 0 for `exact`, 0.05 for `sourced`, 0.25 for
`tolerant`, any for `free` (ADR-0250). A change of prompt is a proposal that changes a step and
is held to the process's evaluation set; a change of skill is evaluated beside the version in
production (ADR-0162); a change of model reaches real runs only after a trial held it on the
process's cases (ADR-0249). Each step is held to its own tolerance, so that a step that fell is
seen where the whole score did not. A run of the set again under the same version that falls
beyond a tolerance is a verdict of `drift`, recorded as `evaluation.scored`, and an incident
where the process sends outward (ADR-0134 §5). All by the named tests.

A variable step of a process without cases declares its tolerance beside its steps, under
`tolerances`, held to its class's ceiling, and the same declaration is held once a scorer
scores the step (ADR-0300 §1); `ProcessVersion.undeclared_tolerances` names every variable step
that declares none. A drift of a process that sends nothing outward is raised as the incident
`evaluation.drift` as well, a finding of deviation detection, addressed to the process's
escalation role or `owner` (ADR-0300 §2). By the named tests.

Not met: registration does not yet refuse a variable step without a tolerance. Refusing it
needs a declared tolerance on 59 steps of 34 bundles of this repository, 25 of them in
`blueprints/software-operations/`, each a new bundle version (ADR-0300, where the promise
ends). The state stays `building`.
