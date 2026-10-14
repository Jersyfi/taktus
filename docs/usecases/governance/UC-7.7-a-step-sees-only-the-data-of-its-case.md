---
id: UC-7.7
title: A step sees only the data of its case, and an analysis step never speaks outward
component: governance
serves: [P11, P12, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0007: 26804369941b, ADR-0024: 64d7f9095b59}
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
