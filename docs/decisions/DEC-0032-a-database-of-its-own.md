# DEC-0032 — The Taktus instance's database: its own, or shared

**Category:** NON-BLOCKING
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), whose deployment plan lists "the database decision" among what is needed from the owner (`deploy/k8s/README.md` §8); answered in conversation and recorded in [#51](https://github.com/Jersyfi/taktus/pull/51)
**Issue:** none; the owner answered before a request was written, and this record is the request with its answer
**Needed by:** 2026-10-20

## 1. What this is about

Taktus keeps everything it knows in one database: what it is running, what it has run, and the
chained record of every step. The deployment plan for the owner's integration server left one
question open: does the Taktus instance bring a database of its own, or does it use a database
server that already runs there for other systems?

## 2. Why you are being asked

Entry M3.8 of `docs/decisions/anchors.taktus.md`: "A new dependency at integration-code tier 1
— what Taktus itself needs in order to run: database, queue, secret store, telemetry". The
database an instance runs on is that dependency.

## 3. What you must decide

Whether the Taktus instance runs on a database of its own or on an existing, shared server.

## 4. What you need to know to decide

- **One database per instance either way.** An instance never shares its database with another
  instance (ADR-0020); the question is only whether the server under it is shared with systems
  that are not Taktus.
- **What depends on it.** At autonomy level 4 Taktus runs work a business depends on and reports
  when something fails. A report about a failure is written through the same database.
- **What the chart can do.** It can deploy a database in the instance's namespace, with its own
  volume, or point at an existing server by a connection URL.

## 5. Options

### Option A — a database of its own (recommended)

- **Meaning:** the chart deploys a PostgreSQL for the instance, in its own namespace, on its own
  volume.
- **Consequence:** a failure of another system's database does not take Taktus with it; one more
  database to back up and upgrade.
- **Effort:** part of the chart.
- **Reversibility:** costly once data exists: moving it is a migration.
- **Why recommended:** the owner's reason, below.

### Option B — an existing, shared server

- **Meaning:** the instance's database lives on a server that also serves other systems.
- **Consequence:** one server less to run; a failure or a maintenance window of that server stops
  Taktus too, including its report of the failure.
- **Effort:** a connection URL.
- **Reversibility:** costly once data exists.

## 6. What is blocked

The chart's database section, which the deployment pull request writes.

## 7. How to answer

"DEC-0032: Option A." or "DEC-0032: Option B."

## Outcome

**Decided:** 2026-09-30
**Answer:** Option A. The owner, in conversation: a PostgreSQL of its own for the Taktus instance,
in its own namespace — confirmed on 2026-10-01 as the same namespace as the instance, not a
namespace for the database alone; the ambiguity came from the brief's wording. The chart deploys
the database with the instance (`database.deploy: true`), in the control plane's namespace, and
no other system uses that server.
**Reasoning given:** a shared database means the system meant to report a failure fails with it.
**Recorded in:** [#51](https://github.com/Jersyfi/taktus/pull/51); `deploy/k8s/README.md` §2 and §8 say the same.
