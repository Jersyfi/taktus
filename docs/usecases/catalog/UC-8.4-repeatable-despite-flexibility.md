---
id: UC-8.4
title: Repeatable despite flexibility
component: catalog
epic: E8
serves: [P8]
state: building
version: 0.4.0
tests: [tests/components/run/test_llm_steps.py::test_an_answer_that_fails_the_check_does_not_leave_the_step]
adrs: {ADR-0004: ffdb1f1537f5, ADR-0005: c28377b9027e, ADR-0011: f25413d512b9, ADR-0014: 6611f7833deb, ADR-0018: 17c99e0eaa3c}
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

An answer that fails its step's check does not leave the step, by the named test.
Tolerances, evaluation sets and evaluation before a change are not built.
