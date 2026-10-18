# ADR-0114 — An accepted proposal moves the step to a trained model as a new version, and the move is measured

**Status:** accepted · builds the third part of method maturation (issue #218, roadmap `0.4.0`)
on ADR-0076, ADR-0084 and ADR-0091, with the conditions of DEC-0164's provisional answer,
Option A

## Context
ADR-0084 measures every step and proposes moving a step from a language model to a trained
classifier when the evidence holds. The proposal is a decision request to whoever owns the
process. ADR-0084 left the proposal unapplied: nothing registered a version when a person
accepted it. ADR-0076 lets a step of method `ml` run, but an unsure model could only hand its
case to a person. A step moved from a language model should hand an unsure case back to the
language model, so that it is handled as it was before.

DEC-0164's provisional answer, items 4 and 5, says what follows an accepted proposal. The step
runs on the trained model, pinned. Below the confidence threshold it falls back to the language
model it ran on before. The new version registers only with the model's evaluation on the
held-out cases. It can be rolled back in one act. Over the first 100 cases on the new version,
Taktus reports the cost per case and the share of cases that fell back, beside the old version's
cost per case. A move whose cost per case did not fall is reported with a proposal to roll back.
UC-4.3 §2 says a change is a new version and the replaced version stays unchanged. UC-8.4 §2
says a change of model registers only with an evaluation.

ADR-0110 also speaks of proposals. There a proposal is a step that waits at level 1 or 2, and a
person releases, corrects or rejects it. A proposal to move a step is not such a step. It is a
decision request, answered under ADR-0008, so it needs its own account of what an answer does.

Six questions were open. What counts as acceptance. What the new version contains. How a run of
it decides between the two methods. What registration requires of it. How the move is measured.
How it is undone.

## Decision

### 1. Acceptance is the person's answer taking effect, with the option that moves
A proposal is accepted when the decider's answer to its request took effect (ADR-0008): the
reading was confirmed, and the option is `A`, the move. A person answers on the HTTP surface or
in the owner's channel, as for every request. Every decision that takes effect there is handed to
the composition root's `MethodMoves` (`composition/moves.py`). One that answers a proposal to
move is applied at once. Any other decision changes nothing.

The answer maps onto the vocabulary of ADR-0110 without being counted by it:

| Answer | Outcome |
|---|---|
| option `A` as proposed | applied: the new version is registered |
| option `A` with modifications | not applied: a rule cannot read a modification; the person changes the process instead (ADR-0091) |
| option `B` | nothing registered; the step stays on the language model |

A decision request is never counted in a correction rate. ADR-0110 §1 already keeps an anchored
step's request out of the count, and a proposal to move is a request of the same kind. The
person whose answer took effect is the actor of the move and the author of the new version.

`taktusctl maturation apply <request>` applies an accepted proposal by hand. It serves where the
decision took effect but its application did not, for example when registration refused the
version. Applied twice, a proposal gives the same version.

### 2. The new version is the active version, with the one step moved
The active version is written back as a bundle (ADR-0091 §5) under the next version name. Only
the proposed step changes, by a rule (`run/domain/service/maturation.moved_step`):

| Field | Becomes |
|---|---|
| `method` | `ml` |
| `model` | the proposal's `<step>-clf@<twelve digits of the digest>` |
| `fallback` | `when: confidence < <the proposal's threshold>`, `to: llm` |
| `requires` | `data.read`, `ml.predict` |
| `reason` | the evidence, and the request that accepted it |
| `rejected` | the earlier entries without `ml`, and `llm` with its measured cost |
| `work.model` | the model file as base64, with its digest |
| `work.dataset` | `{values, features}`: the values the prompt was rendered from, and the numbers the model was trained on |
| `work.fallback` | the step's whole former work: the prompt, the system text, the purpose, the check |
| `work.evaluation` | the evaluation of §4 |

The exactness class, the dependencies and the conditions of the step stay as they were. A step
on a language model carries at most `sourced`, which is what a trained model may carry
(ADR-0084 §6). The new version passes the one registration every version takes, with every
check it applies. The replaced version stays registered and unchanged, and becomes current again
only through §6. A proposal made on a version that is no longer the active one is not applied;
its step is proposed again on the cases of the version that is.

The model file travels in the version. Until a model hub exists (UC-8.6), nothing else keeps
the file with the version that pins it. The training run's artifact is in the object store, and
a version that only named it would depend on a store the takeover instructions cannot assume.

### 3. A run predicts its one case, and falls back to the language model below the threshold
An `ml` step's work may give its rows as one case: `{"values": ..., "features": [...]}`. The
engine resolves the values as the language model's prompt resolved them, and writes the one row
of numbers the features name. A case that lacks a feature, or gives one that is not a finite
number, fails the step before anything starts. A step that falls back to `llm` must give its
rows this way, and must carry the language model's work under `work.fallback`.

Such a step is admitted for both methods: the prediction the worker estimates, and the
completion the model port counts (ADR-0005). After the prediction:

- **At or above the threshold**, the class is the step's answer. The result says
  `answered_by: ml` and `fell_back: false`.
- **Below the threshold**, the case goes to the language model, with the same prompt, the same
  purpose and the same check. Its answer is the step's answer. The result says `answered_by:
  llm`, `fell_back: true`, and names the model that answered. The step's consumption is both
  methods' together.

Either way the result names the model and its digest, the confidence, the threshold and every
row, and carries the answer as `text`, as a step on a language model did. A dependant that read
`$from: <step>, $select: text` reads the same field. A language model that does not answer fails
the step, retryable, with both reasons.

### 4. A step on a trained model registers only with its model's evaluation
Registration holds every step of method `ml` to carrying `work.evaluation`
(`process/domain/service/evaluation.py`, UC-8.4 §2). It names the model by the digest of the
file evaluated, which must be the digest the step pins. It names how many held-out cases the
evaluation used, the agreement on them, the share below the threshold, and the trial run that
made it. An agreement below 95 % is refused: a change that fails its evaluation stays out of
production. The floor is the one a proposal is raised on (ADR-0084 §4).

A version without the evaluation is refused with the finding. So is one whose evaluation is of
another file. This applies to every `ml` step, not only to a moved one: a model a person pins by
hand is a change of model too.

### 5. The move is measured over its first 100 cases, and recorded once
A move is the ledger entry `method.moved`, with the new version, the step, the request and the
move by digest. `ReviewMovesHandler` (`run/application/service/moves.py`) measures every move by
a rule (`maturation.review`):

- the first 100 cases of the step on the new version, in the order they started: their cost per
  case at the instance's price table, and the share that fell back;
- every case of the step on the replaced version: their cost per case at the same table.

Until 100 cases ran, the move is `measuring`, and nothing is recorded. Then the verdict is
`cheaper` when the new cost per case is lower, `not_cheaper` otherwise, and `unpriced` when
either cost cannot be priced. It is recorded once, as `method.measured`, with the measures by
digest. A measure names no person (principle 14).

A move that is `not_cheaper` is reported with a proposal to roll back: a decision request to the
role `owner`, whose option `A` rolls back and whose option `B` keeps the move. A rule never rolls
back on its own, because a change of a step's method kind is a person's (UC-4.3 §2, ADR-0026).

The handler runs from `taktusctl maturation moves`, and in S-06's weekly run, whose operation
`propose` returns the moves measured beside its proposals (ADR-0086).

### 6. Rolling back is one act
A rollback registers the version the move replaced again, as a new version, through the same
registration (ADR-0091 §5). It is one command, `taktusctl maturation rollback <process>`, or an
accepted proposal to roll back. Only a move whose version is current can be rolled back; a later
change is undone as any version is. The ledger records `process.rolled_back`, as every rollback
does, and `method.rolled_back` with the move. Nothing is deleted: the moved version stays
registered and readable by name.

### 7. What depends on DEC-0164's answer
Four numbers and one rule are Option A's: the 100 cases a move is measured over (item 5), the
95 % agreement registration holds an evaluation to (item 2), the fallback to the language model
the step ran on (item 4), the proposal to roll back a move that is not cheaper (item 5), and the
rollback in one act (item 4). An answer that changes a number changes the constant
(`maturation.MOVE_CASES`, `evaluation.MIN_AGREEMENT`). An answer of Option B or C changes the
source these rest on, not the mechanism.

## Alternatives
- **Applying the answer as soon as it is given.** An answer is read, reflected back and
  confirmed before it takes effect (ADR-0008). Registering on the unconfirmed reading would act
  on a free-text answer silently.
- **Counting the acceptance as a decision on a proposal (ADR-0110).** The correction rate
  measures how often a person changes what Taktus proposes to do in a run. A decision to change a
  process is another thing; counting it would let one accepted move lower or raise a level.
- **Naming the model file by its digest only, read from the object store.** The version would
  be small. It would depend on a store that a person taking over the process cannot assume, and
  on an artifact that a retention policy may remove. The hub (UC-8.6) is where a reference
  belongs.
- **Applying a modified answer as far as it reads.** A threshold written in words is language;
  no rule reads it. The person changes the process through a proposal of their own (ADR-0091).
- **Rolling back by rule when the move is not cheaper.** It would change a step's method kind
  without a person, which is always outside the frame (UC-4.3 §2).
- **A step of S-06 of its own for the review.** S-06's bundle and its recording would change for
  an operation that reads what is already recorded. The weekly `propose` operation is where
  maturation already reads every step.
- **A fallback per row.** ADR-0076 rejected it. A moved step predicts one case, so its one row
  is the case.

## Consequences
- `run`: `MlWork.fallback`, `MlWork.evaluation` and the dataset `{values, features}`; an `ml`
  step may fall back to `llm`; the engine's `_moved`; the case's `started_at` and `fell_back` in
  `StepMeasures`; `maturation.moved_step`, `Move`, `MoveReview`, `review`; the handler
  `ReviewMovesHandler` and the error `MoveError`; the port `Verdict` gains `modified`.
- `process`: the rule `domain/service/evaluation.py`, applied by `parse_bundle`.
- `composition`: `MethodMoves` in `composition/moves.py`, wired in `local.py` and `daemon.py`;
  the callback a decision that took effect is handed to names the request; `InstanceMaturation`
  measures the moves.
- `taktusctl maturation apply | moves | rollback`.
- Ledger kinds `method.moved`, `method.measured` and `method.rolled_back`. None changes a state,
  so none is a change of `contracts/changes/v1` (ADR-0055).
- No migration and no contract change: a version is a document already, and `Step.fallback.to`
  already admits `llm`.

## Where this promise ends
The move is measured over its first 100 cases only. A model that drifts afterwards is not
watched here; that is deviation detection (UC-4.10). The cost per case is what the steps
consumed, at the price table the instance is configured with. The trainings and the trials that
made the evidence are not part of it; their runs are in the ledger with their own cost. The
replaced version's cost per case is read over all its cases, not over the 100 before the move.

The fallback holds back an answer the model says it is unsure of. A model that is sure and wrong
is not caught, as ADR-0076 says. The language model a case falls back to is the one the purpose
resolves to now, which may not be the one that answered before the move.

A version carries its model file, so a version with a large model is a large document. Only an
answer that took the option to move, without modifications, is applied; any other change of the
step is the person's, as a change of the process. An answer confirmed on a surface that does not
hand decisions to `MethodMoves` — the command line of a development store has none — is applied
by `taktusctl maturation apply`.

The roadmap's `0.4.0` criterion is shown here against scripted workers and against the ML bench
itself, not on an instance. On an instance it needs a step whose cases reach the floor of
ADR-0084: 500 labelled cases whose values give numbers. No step of a process Taktus runs for
itself reads numbers yet; each reads text, which needs embeddings (#210). Until one does, or a
step of the second tenant reaches the floor, the criterion is not met on an instance.
