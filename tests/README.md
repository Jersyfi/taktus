# Tests

One directory per gate (docs/architecture/project-structure.md §2). A directory with no tests yet
reports "no targets yet" and green: `tools/gate.py` turns pytest's "no tests collected" into
success and nothing else.

| Directory | Gate | Checks |
|---|---|---|
| `architecture/` | `make gate-arch` | adapter obligation, component boundaries, no product name in the core (ADR-0003, ADR-0016) |
| `conformance/` | `make gate-conformance` | the stream rules against every transcript fixture; the suite (`src/taktus/conformance`) against the reference worker in both profiles, started as a separate process; the meta-test: every fault the reference worker can inject fails exactly its check; `taktusctl conformance run` end to end |
| `governance/` | `make gate-governance` | anchors hold, limits never breach, least privilege |
| `exactness/` | `make gate-exactness` | an `exact` step never takes its final value from a variable method (ADR-0014, ADR-0018): on the shared kernel's `Step`, on the process domain's own rule, on every example bundle, and at run time — an exact step executes as a rule of the run component |
| everything else | `make test` | `contract/`: the Python bindings of the shared kernel and the worker contract match the schemas, their enumerations and patterns, and every example · `components/<name>/`: domain rules as tables, no mocks; application services against `fakes/` (a deterministic clock and identifiers, a scripted worker) · `adapters/`: the in-memory adapters · `integration/`: the whole slice against the reference worker started as a separate process, and `taktusctl run` end to end. The four gate directories are excluded here and run under their own targets, so `make gates` runs every test exactly once |
