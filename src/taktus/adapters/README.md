# Adapters

Driving adapters call into the core; driven adapters are called by it through ports
(`docs/architecture/project-structure.md` §3).

| Adapter | Kind | Status |
|---|---|---|
| `driving/cli` | `taktusctl`: `conformance run` drives the conformance suite; `guides check` and `guides publish` render the guides from the repository and put them into a directory (ADR-0065); `run` executes a bundle in this process and `submit` queues it for the daemon, both through the services the composition root hands it (`cli/wiring.py`) | exists |
| `driving/rest` | the HTTP surface of `taktusd`: `/health` and `/ready` on every process, and with the `api` role `/intake/{channel}` (webhook intake through the connector port), `/runs`, `/runs/{id}`, `/runs/{id}/ledger` for a reader whose account key proves an identity, `/findings/intake` for another instance's signed findings where the operator opened it (ADR-0118); everything under `TAKTUS_PATH_PREFIX`, every error an RFC 9457 problem; `api/openapi.yaml` is generated from it | exists; no write beyond intake, no UI |
| `driven/workers/http` | the worker port over HTTP and SSE, the client side of `contracts/worker/v1`; `workers/pool.py` maps required capabilities to a configured worker | exists |
| `driven/memory` | repositories, ledger store, object store, queue and leadership in memory with an optional file snapshot — **development and test only**; answers the same suites as the database | exists |
| `driven/postgres` | the persistence port over PostgreSQL: SQLAlchemy Core, one mapper per aggregate's document, the application role and the tenant set per transaction, `lock_timeout` and `idle_in_transaction_session_timeout` on every connection (`TAKTUS_DATABASE_LOCK_TIMEOUT_SECONDS`, `TAKTUS_DATABASE_IDLE_IN_TRANSACTION_SECONDS`), the ledger store with its chain claim — the only lock on a tenant's chain, in one process as across instances; the queue port over `claim_jobs` (`SELECT … FOR UPDATE SKIP LOCKED` with a lease), and its fence, a `FOR SHARE` read of the claim inside every write under it; the leadership port over a session-level advisory lock; `migrate.py` runs the migrations and checks the revision | exists |
| `driven/configuration` | the configuration port over `TAKTUS_*` environment variables; a secret is read from the file `TAKTUS_<KEY>_FILE` names, and both at once is refused | exists |
| `driven/connectors/mcp` | the connector port as an MCP client: the `intake` tool of whichever connector serves a channel (`TAKTUS_CONNECTORS`); the operations follow with the run's binding | exists, intake only |
| `driven/connectors/directory` | `knowledge.pages` over a directory of Markdown files, one per page, the mark kept in a comment on the file's last line: the knowledge system of an organisation that has none (ADR-0065) | exists; in process, used by `taktusctl guides publish` |
| `driven/connectors/pool.py`, `loopback` | the configured connectors resolved by capability; the instance served to its own processes. These and the directory connector run in the control plane's process. Every other connector is a separate deployable with an image of its own, under [`connectors/`](../../../connectors/README.md) (ADR-0158) | exist |
| `driven/clock` | system time, identifiers, randomness: the one place the control plane reads them | exists |
| `driven/signing` | the reporting component's `Signatures` over Ed25519: the key a sender signs its findings with, derived from a seed the component keeps, and the check the intake makes (ADR-0118) | exists |
| `driven/telemetry` | no-op spans; an OpenTelemetry exporter later | exists |
| everything else | see the tree in the project structure | from later versions |
