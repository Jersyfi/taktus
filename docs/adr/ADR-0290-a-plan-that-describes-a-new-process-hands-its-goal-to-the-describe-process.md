# ADR-0290 — A plan that describes a new process hands its goal to the describe process

**Status:** accepted · extends ADR-0237, ADR-0251 · UC-12.3, UC-1.2, UC-4.1

## Context

UC-12.3 asks that a new case be worked out in dialogue (UC-1.2) and registered without code: a
test takes a description to a registered process version.

Two paths existed apart:

- **The plan dialogue** (ADR-0237) works out a plan with a person. A plan ends in a run or in a
  new process version. Nothing turned a commissioned plan of the second kind into a version.
- **A process from a description** (ADR-0251, UC-4.1) turns words into a proposal for a first
  version, through the process the operator names (`TAKTUS_DESCRIBE_PROCESS`). The proposal is
  rehearsed, and a person commissions it.

## Decision

### 1. A draft may name the process it describes

A plan draft may name `describes`: the process its goal describes. Such a draft results in a new
process version. Its steps are the describe process's, chosen as any template is chosen; its
four parts and its estimates are held as for every plan.

### 2. Commissioning it starts the describe process

Commissioning the draft is recorded as for every plan (`plan.commissioned`). Then the goal is
handed, as the description, to the describe process for the named process, acting for the person
who commissioned. Its run keeps a proposal once the model's bundle passes validation (ADR-0251).

### 3. The rest is the proposal's path

The proposal is rehearsed and commissioned by a person (ADR-0091, ADR-0251). Only then is the
process registered. The registered version is a process like any other: its runs are in the
ledger, the value balance and under its autonomy statement.

## Alternatives

- **Register the bundle when the plan is commissioned.** The model's bundle would skip its
  rehearsal and a person's commissioning.
- **Let the person paste a bundle.** That is writing code by another name.

## Consequences

- `command/domain/model/planning.py`: `PlanDraft.describes`; shown as a setting the guided mode
  does not ask.
- `composition/planning.py`: `PlanActs` takes the describe acts; `commission_and_start` returns
  the plan and the run it started.
- REST: `POST /plans` takes `describes`; the commissioning answer names the run.

## Where this promise ends

- **A proposal, not a version.** Commissioning the plan makes no version. The person
  commissions the proposal after its rehearsal.
- **Only where the operator names a describe process.** Without one, commissioning such a draft
  is refused before anything is written, naming the setting.
- **The model's bundle is held to registration's checks.** A method guessed against its
  exactness class leaves no proposal (ADR-0251 §2). The plan stays commissioned; its run says
  why no proposal was kept.
