# ADR-0300 — A tolerance is declared before cases exist, and a drift or a broken process reaches its owner

**Status:** accepted · supersedes the bounds *A step without scorers declares nothing* of
ADR-0250 and *A drift reaches a person as an incident only where the process sends outward* of
ADR-0250 and ADR-0134 §5 · serves UC-8.4, UC-8.9

## Context

UC-8.4 §2 asks that every variable step declares its tolerance — what counts as an equivalent
result — and that a drift beyond it is a finding of deviation detection (UC-4.10). ADR-0250 put
the tolerance beside the scorers of a process's evaluation. A variable step of a process without
an evaluation therefore had nowhere to declare one. ADR-0134 §5 raised a drift as an incident
only where the process sends outward; any other drift was recorded and shown, and raised to
nobody.

UC-8.9 §2 asks that a verdict of *broke* of the removal test names every process and step that
lost its only adapter, and is raised to the owner of each of those processes. The catalog
component computes and records the verdict (`removal.tested`). Nobody was told.

The owner of a process is the role its escalation names (ADR-0252), and the tenant's `owner`
where it names none.

## Decision

### 1. A tolerance may be declared beside the steps, before any case exists

A bundle takes `tolerances`, a share from 0 to 1 per step, beside its steps:

```yaml
tolerances: { classify: 0.05 }
```

It names a variable step that produces a result. Registration refuses one that names any other
step, one wider than the ceiling of the step's class (ADR-0250 §1), and a step declared both
here and under `evaluation.tolerances`.

A step declared here holds its tolerance before its process has any case. Once a scorer scores
the step, the same declaration is the step's tolerance: the evaluation copies it, as it copies one
declared under `evaluation.tolerances`, and the rule of ADR-0250 §1 that a scored variable step
declares a tolerance is met by either place. `ProcessVersion.undeclared_tolerances` names every
variable step that produces a result and declares no tolerance in either place.

### 2. Every drift is a finding, raised to the process's owner

A verdict of `drift` raises the incident `evaluation.drift` for every process, whether it sends
outward or not. Its facts say which (`outward`: `yes` or `no`), and name the role it is addressed
to: the process's escalation role, else `owner`. The incident is the finding's tracking object
(UC-6.8); it never changes a result and never stops a run.

### 3. A process the removal test found broken is raised to its owner

When the verdict of a removal test is *broke*, every process of it whose verdict is *broke* is
raised as the incident `removal.broke`, once per process, integration and removal run. Its
facts name the integration, the steps that broke with the verdict's reason for each, the run of
the removal test, and the role it is addressed to: the process's escalation role, else `owner`.
The composition raises it after the catalog recorded the verdict, through the governance
component's `RemovalBroke`.

## Alternatives

- **A tolerance on the step itself, in `Step.json`.** ADR-0250 rejected it: it changes the shared
  kernel for something only an evaluation reads. A map beside the steps stays in the bundle.
- **A shipped tolerance per class for every step that declares none.** ADR-0250 rejected it: it
  is a declaration no one made.
- **An evaluation without scorers to hold the tolerances.** Every reader of an evaluation assumes
  it has cases and scorers; an empty one would be read as cases that do not exist.
- **Raise a drift of an inward process as a kind of its own.** Nothing reads the kinds apart; one
  kind with a fact that says outward or not is one less name for the same finding.
- **Raise a broken process to the tenant's owner always.** The process names who owns its
  failures (ADR-0252); a broken process is one.

## Consequences

- `process/domain/model/process.py`: `ProcessVersion.tolerances`, `declared_tolerances`,
  `undeclared_tolerances`, and the findings of §1. Registration reads `tolerances`; the export
  writes it (`process/domain/service/bundle.py`).
- `governance/application/service/drift.py`: `DriftSeen.outward` and `role`;
  `composition/evaluations.py` raises every drift.
- `governance/application/service/removal_broke.py`: `RemovalBroke`; the incident kind
  `removal.broke`. `composition/loopback.py` raises it for a *broke* verdict.
- `tests/components/process/test_tolerances.py`, `tests/composition/test_evaluations.py`,
  `tests/integration/test_removal_broke.py`.

## Where this promise ends

- **Registration does not yet refuse a variable step without a tolerance.** The rule is
  `undeclared_tolerances`; turning it into a refusal needs a tolerance on 59 steps of 34 bundles
  of this repository, 25 of them in `blueprints/software-operations/`, each a new bundle version.
  Until that is done, a variable step may declare none.
- **A tolerance without cases measures nothing.** A step whose process has no case declares what
  counts as equivalent; whether its results stay within it is measured only once cases exist.
- **The owner is a role.** A process whose escalation names no role is raised to `owner`. Who in
  the role reads it is the tenant's configuration.
- **Once per removal run.** A process that breaks again in next week's removal test raises a new
  incident; a second look at the same run raises nothing.
