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
- Until #330 landed, readiness compared for equality. Since then it reads the range of §2, as
  the amendment below describes.

## Amendment — how the two declarations meet (2026-10-28, #330)
§2 left open how a build learns that a newer schema still serves it: the build does not hold the
newer migrations. The schema says it. Migration 0083 creates the database function
`taktus_oldest_code()`, which returns the newest revision of the oldest build the schema serves.
A migration that only expands leaves it. A migration that contracts replaces it with its own
revision and says so in its docstring.

- **The build's side** is `OLDEST_SCHEMA` in `adapters/driven/postgres/migrate.py`; unset, it is
  the build's head. A database at a revision of the build's history from there to the head is
  ready; an older one asks for `make migrate`.
- **The schema's side** is read only when the database is at a revision the build does not know.
  The build is ready when the function names a revision of its own history. A schema without the
  function is never taken for one that serves the build.
- **Migrating on start** leaves a newer schema as it is; whether the build serves it is the
  range's question.
- **The test of §1** compares the schema before and after every migration from 0083 on: a
  migration that drops, changes the type of, or tightens what existed, and does not move the
  function to itself, fails (`tests/adapters/persistence/test_migrations_expand.py`).
  `deploy/docker/upgrade.sh` runs the new migrations while the previous release still serves,
  and holds that release's readiness once a release that reads the range is the previous one.
- **The runbook of §3** is section 12 of `deploy/k8s/README.md`.

## Where this promise ends
- The promise covers one release step: the previous release beside the next. An upgrade that skips
  releases may still need downtime.
- It covers the schema. It does not cover the meaning of data that two releases interpret
  differently; that needs its own migration plan.
- A migration that declares itself breaking is outside the promise, and says so.
- The comparison sees columns, their types and nullability, and constraints. It does not see a
  function, a view or a policy an older build relies on, nor a change of what a value means.
- A build released before #330 does not read the range; it stays unready against any newer
  schema. The first release step the promise covers is from the first release that carries it.
