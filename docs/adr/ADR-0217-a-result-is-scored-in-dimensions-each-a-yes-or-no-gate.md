# ADR-0217 — A result is scored in dimensions, each a yes-or-no gate

**Status:** accepted · extends ADR-0134 (evaluation cases and scorers) and ADR-0142 (the frame
of an outward message) · UC-4.18, UC-7.6, UC-03 B-4.05, DEC-0228

## Context

UC-03 B-4.05 asks that every draft is scored on fixed dimensions with yes-or-no gates, and that
whether it is sent is decided by a rule, not by a model. A tenant sets the thresholds.

Two places score a draft. The frame of an outward message (ADR-0142) holds every reply to its
checks before it is sent; a check is already a rule over a value, `matches` or `not_matches`.
The evaluation cases (ADR-0134) score a step's result against a target and compare a change with
the active version by the mean of every scorer. A mean hides a dimension: a change that writes
better replies on the whole and forgets to apologise in one case of five passes.

## Decision

### 1. A draft is gated per dimension by the frame's rules

A process scores its draft in a step of its own, one line per dimension, `name: yes` or
`name: no`. The frame of the outward message carries one check per dimension that `matches` its
`yes` line. A reply with any dimension answered `no`, or not answered, is held by that check,
whose name is the reason. The model scores; the rule decides. No product change is needed for
this: it is what the frame already does with a check.

### 2. An evaluation scorer may score one dimension with a gate

A scorer of `evaluation.scorers` may name `dimension` and `gate`, a score from 0 to 1; each
needs the other. A case passes the dimension where the scorer's score reaches the gate. Each
`Score` records its dimension and whether it `passed`.

A side's result carries `dimensions`: per dimension, the share of its cases scored on it that
passed. A case whose scorer gave no score is not counted in that share.

### 3. A change that passes a gate less often regressed

A change whose share in any dimension falls below the active version's by more than the tenant's
tolerance is `regressed`, even where its mean holds. It is held as every regression is: it is
commissioned only with a person's reason (ADR-0134 §4).

### 4. The blueprint's dimensions

B-3.02 of `software-operations` scores every draft in the step `dimensions` on four: `answers`,
`language`, `tone` and `complete`. Each is a check of its message frame. The gates are the
blueprint's; a tenant's version changes or adds them.

## Alternatives

- **One number from a judge, and a threshold.** A model's number is not a yes or no a person can
  read back, and a threshold on it is a gate on the model's judgement, not on the reply.
- **Let the model decide whether to send.** B-4.05 forbids it, and so does ADR-0023 for every
  decision a rule can take.
- **A dimension as a scorer's own verdict, apart from the mean.** The mean is what ADR-0134
  compares and drift reads; a dimension is a further reason for a regression, not another score.

## Consequences

- `process`: `Scorer.dimension` and `.gate`; `Score.dimension` and `.passed`;
  `SideResult.dimensions`; `scoring.dimensions`, `scoring.gated`; `scoring.change` regresses on
  a dimension.
- `composition/evaluations.py` records each score's dimension and gate.
- `blueprints/software-operations`: B-3.02's step `dimensions` and its four checks.

## Where this promise ends

- The frame's gate is as good as the scoring step's reading. A model that answers `yes` wrongly
  passes the gate; the independent check and the other checks of the frame still hold the reply.
- Drift is measured on the mean score alone (ADR-0134 §5); a dimension that falls without a
  change is seen in the evaluation's figures, and raises no incident of its own.
- A dimension is compared only where both sides scored cases on it.
