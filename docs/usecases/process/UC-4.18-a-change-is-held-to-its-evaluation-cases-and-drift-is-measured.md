---
id: UC-4.18
title: A change is held to its evaluation cases, and drift is measured without a change
component: process
serves: [P8, P10, P12]
state: verified
version: 0.5.0
tests: [tests/composition/test_evaluations.py::test_a_change_runs_on_the_cases_beside_the_active_version_as_rehearsals, tests/composition/test_evaluations.py::test_a_scorer_has_a_method_of_its_own_and_a_rule_comes_first, tests/composition/test_evaluations.py::test_a_judge_scores_inside_a_run_and_falls_back_to_its_rule, tests/composition/test_evaluations.py::test_a_regression_is_not_commissioned_unless_a_person_overrides_it_with_a_reason, tests/composition/test_evaluations.py::test_drift_is_measured_on_the_schedule_and_raises_an_incident_where_it_speaks_out, tests/composition/test_evaluations.py::test_a_corrected_draft_is_proposed_as_a_case_and_enters_the_set_once_confirmed, tests/composition/test_evaluations.py::test_a_case_keeps_no_personal_input_the_tenant_does_not_allow, tests/composition/test_change_in_channel.py::test_a_commissioning_is_read_back_with_the_verdict_on_the_cases, tests/composition/test_method_move.py::test_a_cheaper_move_that_scores_lower_on_the_cases_is_proposed_for_rolling_back, tests/composition/test_software_operations.py::test_b_4_04_a_corrected_draft_becomes_a_case_and_b_4_02_runs_it_every_week, tests/composition/test_evaluation_dimensions.py::test_a_change_that_passes_a_gate_less_often_regressed_though_its_mean_holds, tests/composition/test_evaluation_dimensions.py::test_an_evaluation_records_each_dimension_beside_the_score]
adrs: {ADR-0084: b792ae358b77, ADR-0091: ca83e9f5bb5f, ADR-0134: 49496fd840aa, ADR-0217: 0d2ddc42c4e9}
supersedes: null
---

# UC-4.18 — A change is held to its evaluation cases, and drift is measured without a change

## 1. What must be achieved

A step that writes to customers with a language model can get worse in two ways. Someone
changes its prompt, its tools or its model. Or nobody changes anything, and the model or the
knowledge behind the same name changes anyway.

Taktus guards against both. Every change of a step's prompt, tools or model is run on the
process's evaluation cases before it is commissioned, and a regression blocks it. The same
cases are run on a schedule without any change, and drift is reported. When a person corrects
a draft, the case is proposed as a new evaluation case, and a person confirms its target answer.

## 2. How it is verified

- A proposed version that changes a step's prompt, tool set or model is run on the process's
  evaluation cases beside the active version before it can be commissioned (ADR-0091).
- A scorer is a check with a method of its own. A rule comes first; a language model as judge
  only where no rule can score, and then with a fallback (#408).
- A version whose score falls below the active version's by more than the tenant's tolerance is
  not commissioned. A person may override it, and the override is recorded with its reason.
- The evaluation runs on a schedule the process declares, with no change. A score that falls
  beyond the tolerance against the last run is reported as drift and raises an incident when the
  process sends anything outward.
- Every evaluation run is recorded with the model's identifier and version as the provider
  reported them, so that a drift can be tied to a change of the provider's.
- A draft a person corrected is proposed as an evaluation case, with the corrected answer as its
  target. It enters the set only once a person confirmed the target.
- An evaluation case holds no personal data beyond what the tenant allows; a case taken from a
  real conversation is reduced to what scoring needs.

## 3. Where the boundary lies

**Not deviation detection.** Whether a result is correct is UC-4.10; this use case asks whether
a step is still as good as it was. **Not the choice of model.** Which model serves a purpose is
the tenant's (UC-8.2). **Not automatic adoption.** A better score proposes; it never commissions
a version by itself.

## 4. What it rests on

UC-03 B-2.04, B-2.05, B-4.01, B-4.02, B-4.04; DEC-0199; NTC-0210. Evaluation cases per
process and versions compared on them are #408 (DEC-0195 W7); commissioning through a proposal
and a rehearsal is ADR-0091; a measured step and a proposal on evidence is ADR-0084.

## 5. What is proven so far

Built (ADR-0134, ADR-0217). A proposal that changes a step is run on the process's cases beside
the active version, as rehearsals, and a score below the active version's by more than the
tenant's tolerance blocks its commissioning unless a person overrides it with a reason. A scorer
is a rule, or a judge that says why no rule can and falls back to a rule or a person. The same
cases run on the process's schedule with no change, and a drift raises an incident where the
process sends outward. Every case names the model the provider reported for each step, so that a
drift is tied to the provider's change. A corrected draft is proposed as a case, reduced to the
inputs the steps read, and enters the set once a person confirmed its target.

A scorer may score one dimension with a yes-or-no gate; a change that passes a gate less often
than the active version, beyond the tolerance, regressed even where its mean holds (ADR-0217).

The software business's B-3.02 declares its evaluation: a corrected draft becomes a case, the
cases run every week, and a model that answers otherwise under the same name is a drift with an
incident (UC-03 B-4.01, B-4.02, B-4.04). Comparing two models on the same cases, with quality,
cost and latency side by side, is the model trial of UC-8.14 (B-2.05).
