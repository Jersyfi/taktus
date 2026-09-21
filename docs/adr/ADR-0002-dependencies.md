# ADR-0002 — Dependencies and the execution environment

**Status:** accepted

## Context
Taktus must run on a home server with two containers and scale horizontally in a cluster. Every
additional mandatory component burdens the smallest installation.

## Decision — data
**PostgreSQL is the only mandatory dependency.** It carries state, process versions, the job queue
(`SELECT … FOR UPDATE SKIP LOCKED`), scheduling (advisory locks), the event outbox, the ledger, and
similarity search for the knowledge layer (`pgvector`).

Everything else is a port with a default adapter that needs no extra service:

| Port | Default adapter | Alternative |
|---|---|---|
| Object store (artifacts, models, reports) | local filesystem | S3-compatible |
| Secret store | encrypted in PostgreSQL | external store |
| Event bus | outbox in PostgreSQL | NATS JetStream |
| Telemetry | OpenTelemetry export outward | — |

## Decision — worker execution
A port of its own with three adapters:

| Adapter | Isolation | For | Requires |
|---|---|---|---|
| `process` | none | local development, single user | nothing |
| `container` | process, filesystem, network | self-hosting in operation | Docker or Podman |
| `kubernetes` | pod with quota and network policy | cluster, multi-tenant | Kubernetes |

**Rule: `process` is not permitted from autonomy level 3 upwards.** An unsupervised worker without
isolation is an open door.

This answers the practical question: on a development machine Taktus runs without Docker. As soon as
a worker executes foreign code, a container is mandatory.

## Decision — scaling
One image, roles via `TAKTUS_ROLES`.
- **Docker Compose:** all roles in one container. Two containers in total.
- **Kubernetes:** one deployment per role. `api` is stateless, `runner` claims work through database
  locks and scales out freely, `scheduler` is a single instance elected by advisory lock,
  `automation` partitions by event.

## Alternatives
- **SQLite for the smallest installations** — two dialects mean duplicated tests and two concurrency
  behaviours. A Postgres container is cheaper than that split.
- **A broker as a requirement** — needed above a load that is not in sight. Remains a port.
- **A home-grown sandbox instead of containers** — security work others have solved better.

## Where this promise ends

PostgreSQL as the only mandatory dependency is a promise about what an installation *needs*,
not about what it *gets*: the default adapters — filesystem object store, encrypted secrets in
the database, the outbox — are the smallest installation's fit, not a cluster's, and a cluster
adds S3, an external secret store or a broker by configuration. The rule that `process` is
refused from level 3 is enforced in code (`ports/execution.py`); the `kubernetes` adapter does
not exist yet, so the third row of the execution table is a plan until it does. The scaling
claims — `runner` scales out freely, `scheduler` is elected — are proven for two daemons on one
database (`tests/integration`), not for a cluster under load; the roadmap's 1.0.0 section names
the measurement.
