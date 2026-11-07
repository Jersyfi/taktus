# ADR-0254 — Every ended run is measured against its objectives, and a recurring heal is said

**Status:** accepted · extends ADR-0107, ADR-0160 · UC-4.6 · DEC-0228

## Context

UC-4.6 requires that service-level objectives can be set per process — for its duration and for
the share of runs that complete — that every run is measured against them, and that a run that
misses one is recorded with the objective it missed. It also requires that the same failure
healed three times in one process raises an improvement proposal or a draft skill, with the
count configurable per process and never switched off.

A version could declare `slo.freshness` and `slo.latency`, and nothing measured a run against
them. Self-healing at level 4 records each heal as `step.healed`, with the failure it answered
stored by digest (ADR-0160); nothing counted them.

## Decision

### 1. Objectives

A bundle's `slo` may name `latency`, the longest a run may take, and `completion`, the least
share of ended runs that finish, a number above 0 and at most 1. The scheduler's leader looks
once a minute (`composition/objectives.py`). Each ended run — `run.finished` or
`run.escalated` — of a version that names either, not yet measured, is measured once by the
governance component's rule (`domain/service/objectives.py`): its duration from `run.created` to
its end against `latency`; the share of finished runs among the process's last 20 ended runs,
itself included, against `completion`. The ledger records `slo.measured` with the outcome `met`
or `missed_` and the objectives missed, and the run's duration. A rehearsal is not measured.

### 2. A recurring heal

A heal's failure is the reason stored under its digest: the same reason of the same step of the
same process is the same failure, on whichever attempt. When it was healed `heal_limit` times —
a bundle's top-level field, at least 1, 3 by default — the ledger records `heal.recurred` once,
and the owner-facing channel carries a report of kind `failure`: the process has a design fault,
to be changed as a new version (UC-4.3). A limit of 0 is refused at registration: the count
cannot be switched off.

## Alternatives

- **Measure in the engine when the run ends.** The engine does not hold the version's
  objectives, and a measure that fails would fail the run's last transaction.
- **A draft skill instead of a report.** A skill describes a procedure (UC-14.2); a failure that
  keeps recurring is a fault to remove, which a person decides.
- **Count by the heal's digest.** It covers the attempt number, so no two heals would match.

## Consequences

- `slo.measured` and `heal.recurred` are new ledger kinds; `heal_limit` is a new bundle field.

## Where this promise ends

- **Not a report of the run.** A heal is in the ledger and the run's record; a rendered report
  of one run is not built here.
- **Not freshness.** `slo.freshness` is the watch over expected runs' (ADR-0107).
- **Not an improvement proposal of UC-4.4.** The report says the fault; a proposal list with
  priorities is UC-4.4's, and not built here.
- **Within a minute.** A run is measured at the scheduler's next look.
