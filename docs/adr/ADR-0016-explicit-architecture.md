# ADR-0016 — Explicit Architecture: cut by component

**Status:** accepted

## Context
Ports and adapters orders the outer boundary, not the inside. An orchestrator holding governance,
processes, runs, decisions, a catalogue, accounting and knowledge gets crowded quickly. With Python
in the core (ADR-0001) there is no compiler to catch the drift, so the structure has to be explicit
and tested.

## Decision
Explicit Architecture after Herberto Graça — DDD layers, ports and adapters, onion and CQRS brought
together. Four commitments:

1. **Dependencies point inward.** Adapters outside, application layer next, domain model at the
   centre.
2. **Ports belong inside, adapters outside.** A port is designed for what the core needs, never to
   mirror the API of the tool it will later cover.
3. **The coarse cut is by component, not by layer.** The top-level division follows the bounded
   contexts: `identity`, `command`, `process`, `run`, `governance`, `decision`, `catalog`,
   `accounting`, `knowledge`, `value`, `ledger`. Layers live *inside* each component. Open the
   repository and you see the domain, not the framework.
4. **Components talk through events.** A component knows no class of another. What they share lives
   in the **shared kernel**, and that kernel is **language-neutral** (JSON Schema), because the web
   app and third-party adapters must read it too. Graça names exactly this case.

Reading across a component boundary is allowed; writing is not.

## Alternatives
- **Ports and adapters only, cut by layer** — works to about five contexts, after which a single
  change is spread over four directories.
- **A microservice per context** — the same separation at much higher operating cost. The component
  split keeps that road open without taking it today.

## Consequences
- `import-linter` contracts enforce: no direct import between components, no write across a
  boundary, no product name in the core.
- The shared kernel stays small — every change there touches everything.
