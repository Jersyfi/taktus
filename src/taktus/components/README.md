# Components

The bounded contexts of `docs/architecture/project-structure.md` §1, each with domain and
application layers inside. No component imports another; what they share is the shared kernel.

| Component | State |
|---|---|
| `process` | process version as a validated graph: steps, edges, triggers, service level; the bundle use case |
| `run` | run, step run, checkpoint; the engine with step atomicity and admission control; the built-in rules |
| `ledger` | the content-free hash chain and its verification |
| `command` | command → commissioned plan |
| every other | a package with its docstring; filled from the version that needs it (`docs/roadmap.md`) |

Each package's docstring states what it owns and where its lines are drawn.
