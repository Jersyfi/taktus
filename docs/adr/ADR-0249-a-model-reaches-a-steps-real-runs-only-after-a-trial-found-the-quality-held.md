# ADR-0249 — A model reaches a step's real runs only after a trial found the quality held

**Status:** accepted · extends ADR-0116 (purpose chains and the route), ADR-0149 (model trials)
and ADR-0250 (step tolerances) · UC-8.2, UC-8.9, UC-8.4 · DEC-0228

## Context

UC-8.2 asks that a model be eligible for a step only after it passed the step's evaluation.
UC-8.9 asks that replacing the provider behind a purpose be a configuration change followed by a
validation run of every process that uses the purpose. The replacement may reach runs for real
only after the validation run has reported, per process, whether the quality held.

Two pieces exist. A **trial** (ADR-0149) runs the evaluation cases of every process that asks a
purpose, once per candidate model, as rehearsals with the purpose bound to that candidate. Its
report says per candidate how many cases finished. The **route** (ADR-0116) takes the first
member of the purpose's chain that fits the step.

Nothing joined the two. The report decided nothing (ADR-0149 §4). A model configured in a chain
served real runs at once. A finished case run counted as passed, whatever it answered.

## Decision

### 1. A validation says, per process and model, whether the quality held

For every model a trial ran and every process whose cases it ran, a **validation** compares two
figures for each scored step that asks the trial's purpose:

- the model's **score**: the step's score on the trial's case runs;
- the **baseline**: the step's score on the case runs of the process's newest scored evaluation,
  on its active side.

Both are scored by the same rules. A rule scorer scores by its rule; a judge scores by its
fallback rule; a judge without a fallback rule scores nothing here. A trial runs no judge,
because a judge's own model would then be part of what is compared. A process that has no scored
evaluation yet has a baseline of 1, its targets.

The verdict is a rule:

- `pending` while a case run of the trial for that model has not settled (ADR-0134 §3);
- `fell` where a step's score is below its baseline by more than the step's tolerance
  (ADR-0250 §2);
- `held` otherwise.

The trial's report carries every validation (`TrialRead.validations`, `GET /trials/{id}`). A
named case (ADR-0149, amended) has no target and is not part of a validation.

### 2. The route passes over a model that holds no validation

A step is **evaluated** where its process's version declares a scorer for it and the process's
evaluation set holds a case with a target for it.

In a real run, an evaluated step may reach only a model whose newest settled validation for the
step's process is `held`. Every other member of the chain is passed over with the reason
`not_evaluated`. The reason is recorded in the route of the provenance record, beside
`residency`, `exactness`, `cooling_down` and `not_shared` (`Provenance.json`). A newer
validation that is still pending does not replace a settled one.

Three runs are not held to it:

- a **rehearsal**, because it acts on nothing (ADR-0030) — the evaluation of a change is one;
- a trial's own **case run**, whose purpose is bound to its candidate;
- a step its process does not evaluate, because it has no evaluation to pass.

Where no member fits, the step fails on its method, and its fallback takes over (ADR-0116 §4).

The run asks through a port of its own (`run/ports/evaluated.py`). The composition root answers
it from the trials in the ledger, the versions, the runs and the evaluations
(`composition/validation.py`).

### 3. The validation run is offered, and a person starts it

A trial is offered as `introduced` wherever the first member of a purpose's chain has been
included in no trial of that purpose. Before this decision, the offer stood only while the model
had answered no step. Replacing the model behind a purpose therefore offers the validation run
at once, and so does a model that served before this decision.

A trial is still started by a person, never on its own (ADR-0149 §3). Its runs spend money, and
spending beyond an allowance is a person's decision (M3.10). The validation run follows the
configuration change through that act. Until it has run and reported, the evaluated steps of
the purpose do not reach the replacement.

## Alternatives

- **Start the validation run on its own when a chain changes.** It would spend without a person's
  act, against ADR-0149 §3. Rejected. The route's refusal and the offer make the gap visible, and
  starting is one act.
- **Count a finished case run as a pass**, as the report did. A model that answers beside the
  point still finishes. Rejected: the quality is what UC-8.9 asks to be held.
- **Hold every step, evaluated or not.** A step without cases could never be validated, and would
  never reach a model again. Rejected; see *Where this promise ends*.

## Consequences

- `run/domain/service/routing.py`: `unevaluated`, and the reason `not_evaluated`.
- `run/application/service/execute_run.py`: the engine asks `Evaluated` for a real run.
- `composition/validation.py`: `Validations`; `composition/evaluations.py`: `rule_scored` and
  `latest_scored`.
- `accounting/application/service/trials.py`: `Validation` and `TrialRead.validations`.
- `composition/trials.py`: the broadened `introduced` offer, and the validations in a trial read.
- `composition/daemon.py` wires the validations into the engine. The local wiring has no trials,
  and holds no route to them.

## Where this promise ends

- **A step that its process does not evaluate is not held.** Most variable steps of the shipped
  bundles have no evaluation cases yet. For them a new model serves real runs at once, as before.
  The promise grows with the cases.
- A validation is per process, not per step of another process. A trial runs every process that
  asks the purpose, so one trial validates them all.
- A trial compares by rules. A step scored only by a judge without a fallback rule has no score in
  a trial. Its validation then stays `pending`, and the step does not reach the model.
- The baseline is the newest scored evaluation, re-scored by the same rules. A process whose
  evaluation ran long ago is held to that.
- A provider that changes the model behind one name is seen by the `changed` offer (ADR-0149
  §3). The earlier validation stands until a new trial settles.
- The local wiring (`taktusctl` without a daemon) runs no trials and holds no route.
- Reading the validations reads the trials of the purpose from the ledger for each evaluated
  step. An instance with many trials pays for that on every such step. A cache is not built.
