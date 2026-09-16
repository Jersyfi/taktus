# Adapters

Driving adapters call into the core; driven adapters are called by it through ports
(`docs/architecture/project-structure.md` §3).

| Adapter | Kind | Status |
|---|---|---|
| `driving/cli` | `taktusctl` — one command so far, `conformance run`, which drives the conformance suite and imports no component | exists |
| everything else | see the tree in the project structure | from `0.1.0` |
