# ADR-0250 — A variable step declares its tolerance, and its class bounds it

**Status:** accepted · extends ADR-0134 (evaluation cases, scorers and verdicts), ADR-0014
(exactness classes) and ADR-0217 (dimensions) · UC-8.4, UC-4.18 · DEC-0228

## Context

UC-8.4 asks that every variable step declare its tolerance, which is what counts as an
equivalent result. The step's exactness class bounds how wide the tolerance may be. Room for
creativity exists only where the class is `free`. A change of model, prompt or skill used by a
step registers only with an evaluation over the step's evaluation set, within the declared
tolerance.

ADR-0134 held a change to one figure, the tenant's tolerance (`evaluation_tolerance`, NTC-0228).
It compared the mean score of all cases on both sides. A step with an `exact` result and a step
that drafts free text were held to the same width. A step whose own score fell could be hidden
by another step whose score rose.

A *variable* step is a step whose method can give a different result for the same input:
`llm` or `worker` (`shared/v1/method.py`).

## Decision

### 1. The tolerance is declared beside the scorers

A bundle's `evaluation` takes `tolerances`, a share from 0 to 1 per scored step:

```yaml
evaluation:
  scorers: [...]
  tolerances: { draft: 0.2 }
```

A step's tolerance is how far its own score on the evaluation cases may fall before its result
no longer counts as an equivalent one.

Registration refuses a version in three cases:

- a variable step that a scorer scores declares no tolerance;
- a tolerance names a step that no scorer scores;
- a tolerance is wider than the ceiling of its step's class.

The ceilings are a rule (`TOLERANCE_CEILING`, `process/domain/model/evaluation.py`):

| Class | Widest tolerance | Why |
|---|---|---|
| `exact` | 0 | an exact result is the same, or it is wrong |
| `sourced` | 0.05 | it says what its source says; only its wording may differ |
| `tolerant` | 0.25 | it may differ in form, not in substance |
| `free` | 1 | room for creativity |

A step that only a rule or a statistic produces does not vary. It may declare a tolerance; where
it declares none, it is held to the tenant's tolerance, never wider than its class admits.

### 2. Each step is held to its own tolerance

An evaluation copies, when it starts, each scored step's declared tolerance and its ceiling. The
cases may change while it runs; these figures do not.

When it is scored, each step's tolerance is fixed (`step_tolerances`): the declared one, or the
tenant's within the ceiling. Each step's score on each side is the mean of its scorers' scores
over the cases (`scoring.step_score`).

- For a **change**, the verdict of ADR-0134 §4 stands. A verdict of `passed` becomes `regressed`
  where a step's score on the proposal falls below its score on the active version by more than
  the step's tolerance.
- For **drift**, a verdict of `steady` becomes `drift` where a step's score falls below its score
  in the earlier drift evaluation by more than the step's tolerance.

The evaluation names every such step (`regressed_steps`). A refused commissioning names each one
with its tolerance. A person may still commission against a `regressed` verdict, with a reason,
as ADR-0134 §4 allows.

### 3. What a change of model, prompt or skill passes through

- A **prompt** is part of a step's work. A proposal that changes it changes a step, and is
  evaluated (ADR-0134 §4).
- A **skill** version is evaluated beside the version in production (ADR-0162 §3). The verdict
  goes through the same scoring, and so through §2.
- A **model** reaches a step's real runs only after a trial passed it on the step's cases
  (ADR-0249).

## Alternatives

- **One tolerance per process.** That is what ADR-0134 had. Rejected: a step's class says how
  far its result may move, and a process mixes classes.
- **A tolerance on the step itself, in `Step.json`.** It would change the shared kernel for
  something that only an evaluation reads. Rejected: the tolerance belongs to the scorers it
  qualifies.
- **A shipped tolerance for every variable step, unless declared.** Rejected: UC-8.4 asks that
  the step declare what counts as equivalent. A shipped value would be a declaration no one made.

## Consequences

- `process/domain/model/evaluation.py`: `TOLERANCE_CEILING`, `EvaluationSpec.tolerances`, and on
  `Evaluation` the fields `declared`, `ceilings`, `step_tolerances` and `regressed_steps`.
- `process/domain/model/process.py`: the three refusals of §1.
- `process/domain/service/scoring.py`: `step_tolerances`, `step_scores`, `regressed`.
- `composition/evaluations.py`: the verdict of §2, and the refusal that names the steps.
- `B-3.02-draft-reply.yaml` declares the tolerance of its `free` draft.

## Where this promise ends

- **A step without scorers declares nothing.** The rule binds every variable step that a
  process's evaluation scores. A variable step of a process that declares no evaluation has no
  cases, and so no tolerance. Its process cannot measure equivalence until cases exist.
  Requiring cases for every variable step of every bundle is not decided here.
- The ceilings are judgement written down as a rule, not measured. A tenant may declare narrower
  tolerances, never wider ones.
- A tolerance is a fall in score. A score that rises proposes nothing (UC-4.18 §3).
- The model settings a provider applies — its sampling, its seed — are the provider's. Taktus pins
  a model version where a method needs it (ADR-0114). It does not set the provider's sampling.
- A drift reaches a person as an incident only where the process sends outward (ADR-0134 §5).
  Every other drift is recorded as `evaluation.scored` with outcome `drift`, and shown on the
  evaluation.
