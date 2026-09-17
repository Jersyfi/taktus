# Docker

| File | Purpose |
|---|---|
| `compose.yml` | **self-hosting**: Taktus and PostgreSQL, two containers (ADR-0002); the reference worker as an optional third under the profile `reference-worker` |
| `Dockerfile` | the one image, every role, selected at start by `TAKTUS_ROLES` |
| `secrets.sh` | writes the two secret files `compose.yml` reads, once, under `secrets/` (ignored by git) |
| `verify.sh` | the end-to-end check: from nothing, a run, the container killed, restarted, the run resumed |
| `compose.dev.yml` | the development database: PostgreSQL alone, bound to `127.0.0.1`, trusting local connections, for `uv run taktusctl run` and the tests |

## Operating it

```bash
make up
```

That is the whole of it. `make up` writes a random database password and the database URL that
carries it under `secrets/` (never committed; existing files are kept, so a running database
keeps its password), builds the image, starts PostgreSQL, starts Taktus with every role in one
process, applies the migrations on start, and returns when readiness answers. From then on:

| Where | What |
|---|---|
| `http://127.0.0.1:8080/health` | liveness: the process is alive |
| `http://127.0.0.1:8080/ready` | readiness: the database answers and is at the schema this build needs; `503` with the reason otherwise |
| `http://127.0.0.1:8080/runs`, `/runs/{id}`, `/runs/{id}/ledger` | the read API |
| `http://127.0.0.1:8080/intake/{channel}` | webhook intake for a channel a connector serves (`TAKTUS_CONNECTORS`) |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process …` | queue a bundle for the daemon; prints the run's identifier |

`make down` stops the containers and keeps both volumes — the database and the artifact bytes.
Removing a volume is the operator's explicit act (`docker volume rm taktus_taktus-postgres`),
never a make target: nothing here deletes data without asking (CLAUDE.md §9). The
configuration is the `TAKTUS_*` variables of `.env.example`; `compose.yml` sets what a
container needs (`0.0.0.0`, the secret file, migrations on start) and passes `TAKTUS_ROLES`,
`TAKTUS_PATH_PREFIX`, `TAKTUS_WORKER`, `TAKTUS_HTTP_PORT`, `TAKTUS_SHUTDOWN_CEILING_SECONDS`
and `TAKTUS_LOG_LEVEL` through from the environment of `make up`.

**Readiness and health are different questions.** A container whose database is gone answers
`503` on `/ready` and `200` on `/health`: it must not receive traffic, and it must not be
restarted in a loop either — restarting it would not bring the database back. The compose
health check probes `/ready`, so that `--wait` returns only once Taktus can work.

**Shutdown.** `docker compose stop` sends SIGTERM and waits `stop_grace_period`, which is the
shutdown ceiling. Taktus stops accepting work, lets every running step reach its boundary, writes
the checkpoint, releases its claim, and exits; a restart resumes at that boundary with at most
one step lost (ADR-0005, ADR-0013 A). A container that is killed instead — no signal, no chance
— leaves its run claimed for at most `TAKTUS_LEASE_SECONDS` (default 60), after which the next
runner recovers it at its last persisted boundary.

**A worker.** A process needs an execution unit, and an execution unit is by design not
Taktus: workers are separate deployables behind the worker contract (ADR-0002). Two containers
are Taktus and its database; the reference worker ships in the same image as an optional
third service, `--profile reference-worker`, for trying a bundle out and for `verify.sh`.
`TAKTUS_WORKER` points the runner at whichever worker serves it.

## Verifying the promise

```bash
make verify-compose
```

`verify.sh` does, from nothing: `make up` with the reference worker; queues a bundle whose
worker step runs 24 commands; waits until that step has persisted a boundary; kills the
application container with SIGKILL; starts it again; waits for the run to finish; and checks
through the read API that the run was recovered at its last boundary (`run.recovered` in the
ledger, the step started twice), that every artifact exists exactly once, and that the ledger's
chain is intact. It exits 0 when every step held and leaves the containers running.

**Finding.** Two containers suffice for Taktus itself. The end-to-end check needs a third
process — an execution unit — because a process with a worker step needs a worker, and no
worker is part of Taktus. That is ADR-0002's shape, not a departure from it.

## Development database

`make db-up` starts PostgreSQL alone (`compose.dev.yml`, no password, `127.0.0.1` only) and
waits until it accepts connections; `make migrate` brings it to the current schema
(`TAKTUS_DATABASE_URL=postgresql://taktus@127.0.0.1:5432/taktus`); `make db-down` stops it and
keeps the volume. When port 5432 is taken on the machine, `TAKTUS_DB_PORT` picks another host
port, and the URL carries that port. Removing the volume is the operator's explicit act
(`docker volume rm taktus-dev_taktus-dev-postgres`), never a make target.
