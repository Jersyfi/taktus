# Taktus

**An operating layer for a business.**

A person states what should be achieved. Taktus breaks that into processes, decides for each step
which *method* is best suited to it, runs it or has it run, measures the result, corrects within an
agreed frame, and reports back.

Taktus does not replace ticket systems, repositories or knowledge tools. It conducts them.

Python, PostgreSQL, Explicit Architecture. Self-hostable from day one.

> **Status: draft.** This repository is currently an architecture, not an application. Contracts and
> decisions first, code second. First milestone: `0.1.0`.
>
> **Public for transparency, but not licensed for use.** See `LICENSE` and `NOTICE`. Third-party
> contributions are not accepted until the licence is settled.

---

## What is different

**AI is not the same thing as a language model.** That conflation is the mistake this project does
not make.

Every process step picks one of eight methods: `rule`, `statistics`, `ml`, `neural`, `llm`,
`worker`, `human`, `wait`. **Four of them are reproducible.** Taktus chooses per step, records why,
measures the choice, and proposes a change when a cheaper and more reproducible method would do the
same job.

The path usually runs in one direction:

```
language model  →  classical ML or a specialised model  →  rule
   expensive                  cheap                        free
    variable                reproducible                  exact
```

Operating time therefore becomes an asset: an organisation collects the training data for its own
models while it works, and Taktus notices when there is enough of it.

**Nobody has to know that classical ML exists in order to benefit from it.** That is the difference
from a workflow tool with AI nodes.

---

## The rest of it

- **Exactness is a property of the step, not a hope.** A step classed `exact` may only take its final
  value from a rule or a computation. A number produced by a language model never reaches the
  accounting journal. CI enforces this.
- **No vendor lock-in.** Swapping a model, an execution unit or a tool is a configuration change.
  Every integration must pass the *removal test*: taking it out may change quality or cost, never
  break a process.
- **The whole autonomy range**, at every size. No level is reserved for large organisations.
- **Final human control at declared points.** *Legal anchors* and *strategic anchors* keep certain
  acts with a person regardless of the autonomy level, and every organisation defines its own.
- **No bus factor of zero.** Every process carries maintained handover documentation. The *takeover
  test* passes when a person can run the process without Taktus.
- **Not a surveillance tool.** Taktus data steers processes and cost, never people. Enforced in the
  data model, not promised in a policy.

---

## Architecture in one paragraph

Three layers. The **control plane** is built here and is the core of the product: command, plan,
process, run, governance, ledger, consumption, value, views. The **execution plane** is made of
interchangeable workers, connectors and models behind adapters — including training runs and
inference on an organisation's own models. The **contracts** between them are open, live under
`contracts/`, and come with an executable conformance suite. Nothing external is called directly; an
architecture test fails if core code touches a foreign system, or even a product name.

Inside, the core is divided by **component** (bounded context), not by layer. Open the repository and
you see the domain, not the framework.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture/methods.md](docs/architecture/methods.md) | Method kinds, the duty to justify a choice, maturation, exactness classes |
| [docs/architecture/control-plane.md](docs/architecture/control-plane.md) | Command → plan → process → run → ledger; state model |
| [docs/architecture/governance.md](docs/architecture/governance.md) | Autonomy levels, anchors, decision requests, limits |
| [docs/architecture/throughput.md](docs/architecture/throughput.md) | Blocked-time accounts, bottlenecks, marginal value of raising a limit |
| [docs/architecture/accounting.md](docs/architecture/accounting.md) | Consumption measurement and the Takt as a unit |
| [docs/architecture/contracts.md](docs/architecture/contracts.md) | Worker, connector and model contracts; maturity levels |
| [docs/architecture/project-structure.md](docs/architecture/project-structure.md) | Components, tree, dependency rules, conventions |
| [docs/adr/README.md](docs/adr/README.md) | 16 architecture decisions with the alternatives rejected |
| [docs/roadmap.md](docs/roadmap.md) | Milestones `0.1.0` to `1.0.0` |
| [docs/usecases/](docs/usecases/) | The worked use cases |

---

## Technology

| Area | Choice |
|---|---|
| Language | Python ≥ 3.13, `asyncio` throughout |
| Database | PostgreSQL 16+ — state, queue, outbox, ledger, vector search (`pgvector`) |
| API | FastAPI, OpenAPI 3.1, RFC 9457 problem details, SSE |
| Agent interface | MCP — Taktus is a client, and exposes itself as a server |
| Domain types | Pydantic v2 value objects; SQLAlchemy Core at the boundary, never in the domain |
| Migrations | Alembic |
| ML bench | scikit-learn, PyTorch, sentence-transformers — as a worker, never in the core |
| Architecture enforcement | `import-linter` contracts, run in CI |
| Tooling | `uv`, `ruff`, `mypy --strict`, `pytest`, `testcontainers` |
| Observability | OpenTelemetry from day one |
| Web | SvelteKit, embedded into the image |
| Deployment | Docker Compose for self-hosting, Kubernetes for scale |

---

## Operating it

A minimal installation is **two containers**: Taktus and PostgreSQL. Everything else is a port with a
default adapter that needs no extra service.

- **Docker Compose:** all roles in one container.
- **Kubernetes:** one deployment per role, each scaled independently.

Workers run isolated — as a process (local development only), as a container (the default in
operation) or as a Kubernetes job. **The process adapter is not permitted from autonomy level 3
upwards.**
