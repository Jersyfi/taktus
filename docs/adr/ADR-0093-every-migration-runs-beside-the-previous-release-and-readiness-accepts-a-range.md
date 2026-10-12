# ADR-0093 — Every migration runs beside the previous release, and readiness accepts a range

**Status:** accepted · from DEC-0187 (finding K3); the rule binds every migration from this ADR on, and the range check is #330 (`0.5.0`)

## Context
An upgrade runs the schema migration as a pre-upgrade hook, before any new pod starts. Readiness
passes only when the database's schema revision equals the build's head
(`adapters/driven/postgres/migrate.py`, `check_schema`).

The review of 2026-10-12 (`docs/research/2026-10-12-devops-review.md`, K3) showed what follows:

- after the migration, the old process's `/ready` turned from 200 to 503 within 0.1 s, before
  the new one was ready;
- an old pod restarted in that window does not start (exit code 3).

The migration in that experiment, 0049, only adds a nullable column, and the old code would have
run against it. The outage came from the equality check alone. It is also why `helm rollback`
cannot bring an old build back without a downgrade nobody had written down.

Taktus is business-critical at level 4 (ADR-0013). An operator upgrading an instance that serves
many customers cannot accept a gap on every upgrade.

## Decision

### 1. Expand, then contract
Every migration keeps the previous release's code working against the migrated schema:

- **It may add:** tables, nullable columns or columns with a default, indexes, functions.
- **It may not, in the same release:** rename or drop what the previous release reads or writes,
  or narrow a type or a constraint the previous release relies on.
- **The contracting half** — dropping or tightening what no supported release reads any more — comes in a later release than the expanding one.

A migration that cannot follow this rule says so in its docstring, names the release it breaks,
and is announced in the release notes as an upgrade with downtime.

### 2. Readiness accepts a range
Each build declares the oldest schema revision it runs against, beside its head. Readiness passes
while the database's revision lies between the two. A database newer than the build's head is
accepted when the build is the previous release of that head. A test runs each new migration
against the previous release's code (#330).

### 3. The way back is written down
`deploy/k8s/README.md` carries a rollback runbook that a person can follow without Taktus
(ADR-0013 C). It states:

- what `helm rollback` restores;
- when a downgrade is needed, and with which image it runs;
- that a downgrade which drops data counts as a delete and is done only on a person's word.

## Alternatives
- **Keep the equality check, and accept a gap per upgrade.** Rejected: it is the outage measured.
- **Run migrations at startup of every replica.** Rejected: replicas race, and the old ones still
  refuse.

## Consequences
- From this ADR on, a migration that renames or drops a column the previous release uses is
  refused in review until the range check exists, and by the test after it.
- Until #330 lands, readiness still compares for equality. The rule of §1 makes the range check
  safe to switch on when it arrives.

## Where this promise ends
- The promise covers one release step: the previous release beside the next. An upgrade that skips
  releases may still need downtime.
- It covers the schema. It does not cover the meaning of data that two releases interpret
  differently; that needs its own migration plan.
- A migration that declares itself breaking is outside the promise, and says so.
