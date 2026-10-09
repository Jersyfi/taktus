# Components

The bounded contexts of `docs/architecture/project-structure.md` §1, each with domain and
application layers inside. No component imports another; what they share is the shared kernel.

| Component | State |
|---|---|
| `process` | process version as a validated graph: steps, edges, triggers, service level; the bundle use case |
| `run` | run, step run, checkpoint; the engine with step atomicity and admission control; the built-in rules; the blocked-time accounts (ADR-0043) |
| `ledger` | the content-free hash chain and its verification |
| `command` | command → commissioned plan |
| `governance` | whether a result has left the system (ADR-0022); the capacity report — what the platform has left and the date a person must act by (`docs/architecture/platform.md`) |
| every other | a package with its docstring; filled from the version that needs it (`docs/roadmap.md`) |
| `reporting` | the product finding: one finding per lack of the product, read from the run's blocked-time accounts by a rule, shown to the operator and sent where enabled (UC-6.12, ADR-0046) |

Each package's docstring states what it owns and where its lines are drawn.
