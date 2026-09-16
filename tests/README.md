# Tests

One directory per gate (docs/architecture/project-structure.md §2). A directory with no tests yet
reports "no targets yet" and green: `tools/gate.py` turns pytest's "no tests collected" into
success and nothing else.

| Directory | Gate | Checks |
|---|---|---|
| `architecture/` | `make gate-arch` | adapter obligation, component boundaries, no product name in the core (ADR-0003, ADR-0016) |
| `conformance/` | `make gate-conformance` | the contract suite, runnable against a foreign adapter |
| `governance/` | `make gate-governance` | anchors hold, limits never breach, least privilege |
| `exactness/` | `make gate-exactness` | an `exact` step never takes its final value from a variable method (ADR-0014) |
| everything else | `make test` | domain: table tests, no mocks · application: fakes of the ports · driven adapters: testcontainers |
