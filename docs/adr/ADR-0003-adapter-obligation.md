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
- The removal test becomes checkable rather than asserted. Since 2026-09-21 it is a process
  Taktus runs for itself, weekly, once per configured integration
  (`blueprints/self-operation/`): withhold, exercise, restore, record — *broke*, *changed* or
  *exception* — in the ledger as `removal.tested` and in the adapter's maturity. The suites
  report W-12 and C-10 as pending because the process, not the suite, is where the test runs.
- More ceremony per integration. That is the price and it is intended.

## Where this promise ends

The tests fail on what they can see: an import, a product name as a word, a write across a
boundary. They do not see a product's *behaviour* copied into the core without its name, and
they do not see an adapter whose declared capability is one only its product can serve. The
removal test shows that an integration can be removed only for the integrations and processes
that are configured and registered where it runs; it says nothing about an installation it has
not run in. Until it has run in an installation, "changes quality or cost but breaks no
process" is a claim for that installation, not a fact; the process under
`blueprints/self-operation/` is where the fact is made, weekly.
