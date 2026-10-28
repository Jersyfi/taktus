---
id: UC-7.7
title: A step sees only the data of its case, and an analysis step never speaks outward
component: governance
serves: [P11, P12, P14]
state: verified
version: 0.5.0
tests: [tests/components/run/test_case_scope.py::test_every_call_of_a_scoped_step_carries_its_subject_and_the_record_names_it, tests/components/run/test_case_scope.py::test_a_scoped_step_asking_for_a_second_customer_is_refused_and_it_is_recorded, tests/components/run/test_case_scope.py::test_a_subject_taken_from_a_step_s_output_is_refused_before_the_run_starts, tests/components/process/test_frame.py::test_an_analytic_step_given_a_mail_capability_is_refused_at_registration, tests/components/run/test_case_scope.py::test_an_analytic_step_never_speaks_outward_even_through_its_source, tests/components/run/test_case_scope.py::test_an_analytic_step_on_a_source_not_declared_free_is_refused, tests/components/process/test_frame.py::test_an_analytic_step_on_a_source_the_tenant_does_not_declare_free_is_refused, tests/components/run/test_case_scope.py::test_reading_personal_data_outside_a_case_halts_a_level_4_process, tests/conformance/test_connector_v1_business.py::test_the_payment_connector_answers_a_case_only_its_own_customer]
adrs: {ADR-0007: 26804369941b, ADR-0024: 52ba89e4adec, ADR-0130: e38152a550b0}
supersedes: null
---

# UC-7.7 — A step sees only the data of its case, and an analysis step never speaks outward

## 1. What must be achieved

A step that answers a customer needs that customer's account and nothing else. A step that
analyses retention needs many records and must never write to anyone. If both are possible in
one frame, a confused or manipulated model can send one customer's data to another, or
publish what it analysed.

Taktus therefore scopes data to the case. A step that serves a case — a support request, a
data protection request — reaches only the data of the case's subject. A step that analyses
works on a copy without personal fields and has no outward capability at all. Both are enforced
in the frame the step runs in, not asked of the model.

## 2. How it is verified

- A step can declare a **case scope**: the subject the case is about, taken from the case's
  intake, never from the model's output. Every connector call of that step carries the scope,
  and a connector serving a scoped capability returns only the subject's data. A test asks,
  from inside a scoped step, for a second customer's account and is refused, and the refusal is
  recorded.
- A step can declare itself **analytic**. Its frame holds no connector action whose effect
  reaches outside (ADR-0024), and no host outside its data source. A test gives an analytic
  step a mail capability and finds the process refused at registration.
- An analytic step reads a source the tenant declares free of personal fields. A source not so
  declared is refused for it.
- An export of personal data outside a specific case is an anchor: never executed without a
  person, at any level (UC-03 §6).
- The scope is named in the step's provenance record, so that every result shows whose data it
  was built from.

## 3. Where the boundary lies

**Not the removal of personal fields.** Producing a copy without them is the business's data
pipeline, or a process of its own. **Not the source system's permissions.** A connector also
passes the caller's permissions through (UC-5.5). **Not a guarantee against a wrong subject in
the intake.** If the case names the wrong customer, the scope is wrong too; that is a result
defect (UC-4.10).

## 4. What it rests on

Requirement 9 of the catalogue behind UC-03; UC-03 §6 (user data), B-3.02, B-3.08, B-9.02;
DEC-0199; NTC-0210. Least privilege down to the worker (UC-7.3); the frame's allowed tools and
hosts (ADR-0007); connector effects (ADR-0024).

## 5. What is proven so far

ADR-0130 builds it. The named tests prove every condition of §2 in the run and at
registration: the subject taken from the run's inputs and refused from a step's result; the
scope on every connector call; a second customer's account refused by a connector that honours
the scope, and the refusal recorded as `frame.refused`; an analytic step given a mail
capability refused at registration, and refused at the call when an operation leaves the
system; a source the tenant does not declare free refused; a level-4 process halted before it
reads personal data outside a case; the scope in the provenance record.

The connector's half is proven by conformance check C-11 against a real connector: the
payment connector's scoped capability `payments.customers` answers a case's own customer and
refuses another customer as `out_of_scope`. A connector that ignores the scope fails C-11 and
nothing else.
