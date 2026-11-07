# ADR-0237 — A plan is worked out in versions, and only a commissioned version runs

**Status:** accepted · extends ADR-0005, ADR-0026 · UC-1.2, DEC-0228

## Context

UC-1.2 asks that a person and Taktus work out a plan back and forth, and that commissioning it
is an explicit act of its own. A plan must name what is done, with what, by when and at which
autonomy level with its reason; every estimate must name its basis; a plan changed after it was
commissioned runs only once it is commissioned again; and a plan with a step that cannot be
estimated is refused before anything runs.

Until now a plan was commissioned in the same step that created it (`CommissionPlan`), from a
process version's steps. There was no record a dialogue could change, and the engine started a
run from any plan it was handed.

## Decision

### 1. A plan draft is the record the dialogue changes

A **plan draft** names the command it answers, its goal, its steps — each with its method,
reason and capabilities —, the process version it runs or that it results in a new one, the
date it is due, the autonomy level and its reason, and an estimate per step. Every change is a
new version and records `plan.revised`. A draft is kept in `plan_draft` at its current version.

### 2. An estimate names its basis, or is a guess

An estimate is a figure in a unit — seconds, tokens, minor units, Takte, turns — and the basis
it was computed from. One without a basis is shown as a guess, never as a figure. A step
without a figure cannot be estimated.

### 3. Commissioning takes one version, refused when incomplete or unestimable

Commissioning takes the draft's current version into a `Plan` of the shared kernel whose
identifier is `<draft>@v<version>`, commissioned by the identity that commissions, and records
`plan.commissioned` naming that plan and identity, in one transaction. It is refused, writing
nothing, when the draft lacks one of the four parts — the refusal names each — or when a step
cannot be estimated, naming the step (ADR-0005). A version revised after it was commissioned is
not commissioned: the plan of the version that was stays as it was, until the new version is
commissioned.

### 4. The engine runs only a commissioned plan

`RunEngine.start` and `submit` refuse a plan whose status is not `commissioned`. Confirming a
step at level 2 records `step.confirmed`, which is not commissioning: no plan changes by it.

## Alternatives

- **Versions in the shared kernel's plan.** A field on `Plan.json` would change a published
  contract for what only the dialogue needs. The draft is the `command` component's own record;
  the plan stays what the run reads.
- **Commissioning per step.** It is what UC-1.2 forbids: a plan must not slide into execution
  because steps were approved.

## Consequences

- `components/command/domain/model/planning.py`, `application/service/plan_dialogue.py`.
- `components/run/application/service/execute_run.py`: the refusal of a plan not commissioned.
- `migrations/versions/0101_run_steering_and_plan_drafts.py`: `plan_draft`.
- `tests/components/command/test_plan_dialogue.py`, `tests/components/run/test_pause_and_cancel.py`.

## Where this promise ends

- What Taktus proposes in the dialogue — alternatives, the steps of a long piece of work — is
  the caller's to put into the draft. The record holds what was agreed; it does not propose.
- An estimate's basis is a sentence the caller states. Whether the figure follows from it is
  not checked; the budget holds the run all the same (ADR-0005).
- The one-step `CommissionPlan` of a trigger, a deadline or a reaction stays: those plans are
  commissioned by whoever configured the process, and are never drafts.
