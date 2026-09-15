# ADR-0003 — The adapter obligation, enforced in CI

**Status:** accepted

## Context
The central promise of the product is freedom from vendor lock-in. A promise that lives only in
documentation erodes the first time a deadline presses.

## Decision
The core is technology-free. Every outward access goes through one of three adapter types — worker,
connector, model — plus the internal ports (persistence, queue, secret, object store, execution,
telemetry, ledger).

`import-linter` contracts and `tests/architecture` fail on:
- a foreign or driver import in the core
- **a product name in the core** (`claude`, `slack`, `github`, `jira`, `ollama`, …) — the sharpest
  test in the project
- adapter code importing the core
- a direct import between two components (ADR-0016)
- a write by one component into another's data

Processes, agents and skills reference adapters **by capability only**, never by product name.
Mapping a capability to a concrete adapter is configuration.

**Removal test:** for every integration it must be shown automatically that removing it changes
quality or cost but breaks no process.

## Alternatives
- **Convention instead of tests** — works until it is urgent. With Python in the core (ADR-0001)
  there is no compiler to fall back on, so this is not optional.
- **Adapters for models only** — would have left the worker layer unguarded, and that is where the
  churn is highest.

## Consequences
- The removal test becomes checkable rather than asserted.
- More ceremony per integration. That is the price and it is intended.
