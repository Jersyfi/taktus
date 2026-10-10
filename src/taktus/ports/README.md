# Ports

Protocols the core calls; driven adapters implement them. Designed for what the core needs,
never mirroring a tool (ADR-0016). Nothing here imports a component or a technology.

| Port | Purpose | Implemented by |
|---|---|---|
| `worker.py` | CONTRACT 1, the client side: the worker contract's shapes and the `Worker` protocol | `adapters/driven/workers/http/` |
| `persistence.py` | `Repository[T]` for one aggregate kind, `LedgerStore` append-only (its `summary` counts one kind without reading the chain; `head`, `after` and `position` are what a reader resumes from), `UnitOfWork` — every call names its tenant and happens inside a transaction; `StateSize`, the state's size on disk | `adapters/driven/postgres/`; `adapters/driven/memory/` (development and test only); one suite checks both |
| `ledger.py` | facts in, chained entries out, `verify` — one chain per tenant | `components/ledger` |
| `configuration.py` | what an instance is told about itself, by key; `Secret` for what must not be shown | `adapters/driven/configuration/` |
| `objectstore.py` | artifact bytes by digest | `adapters/driven/memory/` |
| `clock.py` | time, identifiers, randomness — the core never reads them by itself | `adapters/driven/clock/` |
| `execution.py` | how an execution unit comes to exist for one job, with what isolation; the fail-closed rule that refuses an unisolated unit from autonomy level 3 (ADR-0002) | `adapters/driven/execution/` (`process`, `container`); `adapters/driven/workers/launched.py` puts the worker port over it |
| `platform.py` | what the machine or container the instance runs on has left — CPU, memory, the state directory's storage — each observed with its source or `Unobserved` with the reason (`docs/architecture/platform.md`) | `adapters/driven/platform/` (`host`) |
| `administration.py` | the platform this instance runs on and the platforms each credential administers, as one value; `refusal` says why a step may not use a credential here (ADR-0052) | `composition/settings.py` reads it from configuration |
| `telemetry.py` | spans around units of work, and histograms of what is measured in operation (`observe`) | `adapters/driven/telemetry/` (`otel`, `noop`) |
| `signal.py` | the signal that a tenant's ledger gained entries: it wakes a reader of the ledger and is never a record (ADR-0055) | `adapters/driven/postgres/signal.py` (a database notification) |
| `connector.py`, `model.py`, `queue.py`, `eventbus.py`, `secret.py` | see the tree in `docs/architecture/project-structure.md`; the queue's and outbox's tables and claiming functions already exist in the schema | from later versions |
