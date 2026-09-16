# Adapters

Driving adapters call into the core; driven adapters are called by it through ports
(`docs/architecture/project-structure.md` §3).

| Adapter | Kind | Status |
|---|---|---|
| `driving/cli` | `taktusctl`: `conformance run` drives the conformance suite; `run` drives the control plane through the services the composition root hands it (`cli/wiring.py`) | exists |
| `driven/workers/http` | the worker port over HTTP and SSE, the client side of `contracts/worker/v1`; `workers/pool.py` maps required capabilities to a configured worker | exists |
| `driven/memory` | repositories, ledger store, object store in memory with an optional file snapshot — **development and test only** | exists |
| `driven/clock` | system time, identifiers, randomness: the one place the control plane reads them | exists |
| `driven/telemetry` | no-op spans; an OpenTelemetry exporter later | exists |
| everything else | see the tree in the project structure | from later versions |
