# Adapters

Driving adapters call into the core; driven adapters are called by it through ports
(`docs/architecture/project-structure.md` §3).

| Adapter | Kind | Status |
|---|---|---|
| `driving/cli` | `taktusctl`: `conformance run` drives the conformance suite; `run` executes a bundle in this process and `submit` queues it for the daemon, both through the services the composition root hands it (`cli/wiring.py`) | exists |
| `driving/rest` | the HTTP surface of `taktusd`: `/health` and `/ready` on every process, and with the `api` role `/intake/{channel}` (webhook intake through the connector port), `/runs`, `/runs/{id}`, `/runs/{id}/ledger`; everything under `TAKTUS_PATH_PREFIX`, every error an RFC 9457 problem; `api/openapi.yaml` is generated from it | exists; no write beyond intake, no UI |
| `driven/workers/http` | the worker port over HTTP and SSE, the client side of `contracts/worker/v1`; `workers/pool.py` maps required capabilities to a configured worker | exists |
| `driven/memory` | repositories, ledger store, object store, queue and leadership in memory with an optional file snapshot — **development and test only**; answers the same suites as the database | exists |
| `driven/postgres` | the persistence port over PostgreSQL: SQLAlchemy Core, one mapper per aggregate's document, the application role and the tenant set per transaction, the ledger store with its chain claim; the queue port over `claim_jobs` (`SELECT … FOR UPDATE SKIP LOCKED` with a lease); the leadership port over a session-level advisory lock; `migrate.py` runs the migrations and checks the revision | exists |
| `driven/configuration` | the configuration port over `TAKTUS_*` environment variables; a secret is read from the file `TAKTUS_<KEY>_FILE` names, and both at once is refused | exists |
| `driven/connectors/mcp` | the connector port as an MCP client: the `intake` tool of whichever connector serves a channel (`TAKTUS_CONNECTORS`); the operations follow with the run's binding | exists, intake only |
| `driven/clock` | system time, identifiers, randomness: the one place the control plane reads them | exists |
| `driven/telemetry` | no-op spans; an OpenTelemetry exporter later | exists |
| `driven/connectors/github` | the reference connector behind `contracts/connector/v1`: an MCP server against a repository hosting service — issues, pull requests, pipelines, comments as actions with a declared effect and a marked idempotency key; webhook intake verified and normalised into commands; fault injection for the suite. Named by capability everywhere but in its own directory | exists; reached by the daemon's webhook intake; its operations are not yet called from a process (the run's binding is `0.2.0`) |
| everything else | see the tree in the project structure | from later versions |
