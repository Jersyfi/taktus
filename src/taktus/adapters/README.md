# Adapters

Driving adapters call into the core; driven adapters are called by it through ports
(`docs/architecture/project-structure.md` §3).

| Adapter | Kind | Status |
|---|---|---|
| `driving/cli` | `taktusctl`: `conformance run` drives the conformance suite; `run` drives the control plane through the services the composition root hands it (`cli/wiring.py`) | exists |
| `driven/workers/http` | the worker port over HTTP and SSE, the client side of `contracts/worker/v1`; `workers/pool.py` maps required capabilities to a configured worker | exists |
| `driven/memory` | repositories, ledger store, object store in memory with an optional file snapshot — **development and test only**; answers the same repository suite as the database | exists |
| `driven/postgres` | the persistence port over PostgreSQL: SQLAlchemy Core, one mapper per aggregate's document, the application role and the tenant set per transaction, the ledger store with its chain claim; `migrate.py` runs the migrations and checks the revision | exists |
| `driven/configuration` | the configuration port over `TAKTUS_*` environment variables | exists |
| `driven/clock` | system time, identifiers, randomness: the one place the control plane reads them | exists |
| `driven/telemetry` | no-op spans; an OpenTelemetry exporter later | exists |
| `driven/connectors/github` | the reference connector behind `contracts/connector/v1`: an MCP server against a repository hosting service — issues, pull requests, pipelines, comments as actions with a declared effect and a marked idempotency key; webhook intake verified and normalised into commands; fault injection for the suite. Named by capability everywhere but in its own directory | exists; not yet called from a process (the connector port and the run's binding are `0.2.0`) |
| everything else | see the tree in the project structure | from later versions |
