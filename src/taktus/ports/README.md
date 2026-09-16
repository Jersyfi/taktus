# Ports

Protocols the core calls; driven adapters implement them. Designed for what the core needs,
never mirroring a tool (ADR-0016). Nothing here imports a component or a technology.

| Port | Purpose | Implemented by |
|---|---|---|
| `worker.py` | CONTRACT 1, the client side: the worker contract's shapes and the `Worker` protocol | `adapters/driven/workers/http/` |
| `persistence.py` | `Repository[T]` for one aggregate kind, `LedgerStore` append-only, `UnitOfWork` — every call names its tenant and happens inside a transaction | `adapters/driven/postgres/`; `adapters/driven/memory/` (development and test only); one suite checks both |
| `ledger.py` | facts in, chained entries out, `verify` — one chain per tenant | `components/ledger` |
| `configuration.py` | what an instance is told about itself, by key; `Secret` for what must not be shown | `adapters/driven/configuration/` |
| `objectstore.py` | artifact bytes by digest | `adapters/driven/memory/` |
| `clock.py` | time, identifiers, randomness — the core never reads them by itself | `adapters/driven/clock/` |
| `telemetry.py` | spans around units of work | `adapters/driven/telemetry/` (no-op) |
| `connector.py`, `model.py`, `execution.py`, `queue.py`, `eventbus.py`, `secret.py` | see the tree in `docs/architecture/project-structure.md`; the queue's and outbox's tables and claiming functions already exist in the schema | from later versions |
