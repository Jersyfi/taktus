# ADR-0076 — A step of method `ml` is a prediction on a worker, and an unsure one goes to its fallback

**Status:** accepted · builds the first part of method maturation (issue #216, roadmap `0.4.0`)
on ADR-0004 and ADR-0007

## Context
ADR-0004 names `ml` as one of eight methods a step can run on: a trained model, reproducible
exactly at a pinned version. `docs/architecture/methods.md` §2 adds that a model that is unsure
does not guess, it asks, and gives the form of that rule: `fallback: when: confidence < 0.9, to:
human`. Until now no step of method `ml` could run: the run engine refused it before the run
started, for want of an executor.

The ML bench (`workers/mlbench/`, #89) trains, evaluates and predicts behind the worker contract.
A prediction names its model file by the digest of its bytes, and returns every row's class with
its confidence, the probability the model gives its own answer (NTC-0156).

Four questions were open. Where an `ml` step runs. How it names its model. What *the step's
confidence* is when the step predicts more than one row. And what "goes to its fallback" means in
a run.

## Decision

### 1. An `ml` step is an assignment to a worker that offers `ml.predict`
An `ml` step runs on the worker port, like a `worker` step. It requires the capability
`ml.predict`, and the engine resolves a worker that offers every capability the step requires.
Training is never part of a run's `ml` step: training runs as a worker of its own (ADR-0004), and
the step only predicts. No method is executed inside the control plane, so no library for machine
learning enters it.

The step's `work` names the rows to predict as `dataset` and the model file as `model`, with the
digest of its bytes. The engine turns them into the task of a prediction — `operation: predict` —
and hands it over through the same estimate, admission, hand-over and stream as every worker step
(ADR-0005, ADR-0038). A model without a digest is refused before the run starts. A model whose
bytes do not match is used for nothing by the worker, the step fails and the run escalates.

The step pins its model as `name@version` (`contracts/shared/v1/Step.json`). Until a model hub
exists (UC-8.6), nothing ties that name to a file but the step itself: the work names the file
and its digest, and the step's result names both.

### 2. The step's confidence is the lowest confidence of its rows
A step that predicts several rows hands its result on as one. If one row is unsure, the step is
unsure. Its confidence is therefore the lowest confidence of any row, and a step that predicted no
row has none and fails.

### 3. The fallback condition is a threshold a rule evaluates
For an `ml` step, `fallback.when` must read `confidence < t` or `confidence <= t`, with `t`
between 0 and 1. The engine compares; no model judges whether the model was sure enough. A step
whose condition has another form, or that names no fallback, is refused before the run starts.
The contract requires a fallback for variable methods only; an `ml` step is not variable, but it
can be unsure, and `methods.md` §2 says what follows.

### 4. Below the threshold, the step goes to its fallback, and its answer stays in the step
A step whose confidence meets its condition does not finish with the model's answer. In this
version a fallback can go to a person, and nowhere else. The step waits for a person
(`step.awaiting`, outcome `fell_back`), with a block on the account `wait.human`. The document the
entry names by digest carries the step, the model and its digest, the confidence and the
threshold, and the digest of the predictions. The steps that depend on it are held back. The
person performs the step and reports it performed, at any autonomy level: the step ends without a
result from Taktus, and a dependant that reads it receives nothing. The predictions stay recorded
as the step's artifact; they are never its result.

A fallback to another method — to the language model a step moved away from — is refused before
the run starts. Switching methods inside a step belongs to the move itself (#218).

### 5. The result names what produced it
A step that is sure enough finishes with a result document: the model as pinned and by digest,
every row's class and confidence, the step's confidence and the threshold. Its provenance record
names the model and the rows it read. The same model, rows and worker version give a result with
the same digest.

## Alternatives
- **Predicting inside the control plane.** Fast, and it puts a machine-learning library into the
  core, against the adapter obligation (ADR-0003) and ADR-0004's "training runs as a worker".
- **The mean of the row confidences.** It lets one unsure row hide behind many sure ones; the
  step would pass on an answer the model did not stand behind.
- **A fallback per row**: the sure rows pass, the unsure ones go to a person. It needs a result
  that a person completes row by row. That is a larger change of the run and of the answer a
  person gives, and nothing asks for it yet.
- **A new ledger kind for a fallback.** The changes contract would gain a kind every reader must
  learn. `step.awaiting` already means "the step waits for a person"; the outcome says why.

## Consequences
- `parse_work` reads an `ml` step's work as `MlWork`, a worker step's work with a prediction as
  its task. Every rule that applies to a worker step applies to it: it acts, so at level 1 it is
  proposed and performed by a person, and at level 2 it waits for a confirmation (ADR-0039).
- `taktusctl run` names `--performed` for a step that fell back.
- No migration: the block a fallback opens is held in the step run's existing block.

## Where this promise ends
The fallback holds the model's answer back when the model says it is unsure. It does not catch a
model that is sure and wrong: confidence is the model's own estimate, and agreement with the truth
is measured when the model is evaluated, not when it predicts. The pin by digest makes the file
the step runs on knowable; it does not say the file is the model `name@version` claims to be,
which needs the model hub (UC-8.6). A fallback goes to a person only: until #218, a step cannot
fall back to another method. A step's confidence is the lowest of its rows, so a step that
predicts many rows goes to a person more often than one that predicts a few; a fallback per row
is not built.
