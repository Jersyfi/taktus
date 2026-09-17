# Taktus

**An operating layer for a business.**

A person states what should be achieved. Taktus breaks that into processes, decides for each step
which *method* is best suited to it, runs it or has it run, measures the result, corrects within an
agreed frame, and reports back.

Taktus does not replace ticket systems, repositories or knowledge tools. It conducts them.

Python, PostgreSQL, Explicit Architecture. Self-hostable from day one.

> **Status: draft, on the way to `0.1.0`.** The contracts, the conformance suite, and the first
> vertical slice of the control plane exist: a process bundle runs against a worker, every step
> lands in a verifiable ledger, a stop resumes at a step boundary, a step that would breach the
> budget never starts, and the state lives in PostgreSQL — a killed process resumes at its last
> step boundary. From the command line, without governance. What runs today:
> [examples/README.md](examples/README.md).
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
| [contracts/worker/v1/CONFORMANCE.md](contracts/worker/v1/CONFORMANCE.md) | How to check a worker of your own against the contract |
| [contracts/connector/v1/CONFORMANCE.md](contracts/connector/v1/CONFORMANCE.md) | How to check a connector of your own against the contract |
| [docs/architecture/project-structure.md](docs/architecture/project-structure.md) | Components, tree, dependency rules, conventions |
| [examples/README.md](examples/README.md) | Running a process bundle with `uv run taktusctl run`; the shape of a bundle |
| [docs/adr/README.md](docs/adr/README.md) | 24 architecture decisions with the alternatives rejected |
| [docs/decisions/](docs/decisions/README.md) | The project's decision register: which questions reach the owner, and what was answered |
| [docs/roadmap.md](docs/roadmap.md) | Milestones `0.1.0` to `1.0.0` |
| [docs/usecases/](docs/usecases/) | The worked use cases |

---

## Technology

| Area | Choice |
|---|---|
| Language | Python ≥ 3.13, `asyncio` throughout |
| Database | PostgreSQL 16+ — state, queue, outbox, ledger, vector search (`pgvector`) |
| API | FastAPI, OpenAPI 3.1, RFC 9457 problem details, SSE |
| Agent and tool interface | MCP — Taktus is a client of every connector (`contracts/connector/v1`, the `mcp` package for the suite and the reference connector), and exposes itself as a server later |
| Domain types | Pydantic v2 value objects; SQLAlchemy Core at the boundary, never in the domain — the adapter stores an aggregate's document and never imports its class |
| Shared kernel | JSON Schema under `contracts/shared`, bound to Python by hand and checked by a test |
| Process bundles | YAML, read by PyYAML in the command-line adapter only |
| Migrations | Alembic, `make migrate`; every table tenant-scoped with row-level security, the ledger and the provenance append-only in the database (ADR-0020, ADR-0021) |
| ML bench | scikit-learn, PyTorch, sentence-transformers — as a worker, never in the core |
| Architecture enforcement | `import-linter` contracts, run in CI |
| Tooling | `uv`, `ruff`, `mypy --strict`, `pytest`, `testcontainers`; `make gates` installs its own environment; `make doctor` says what is missing. `taktusctl` lives in that environment: `uv run taktusctl …`. Docker is optional: without it the PostgreSQL tests skip and say so; CI runs them |
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

**Today, on a developer's machine.** The application container arrives with the daemon; until
then Taktus runs from a checkout, against the development database or in memory:

```bash
make db-up
```

```bash
export TAKTUS_DATABASE_URL=postgresql://taktus@127.0.0.1:5432/taktus && make migrate
```

```bash
uv run taktusctl run --process examples/processes/six-times-seven.yaml
```

`make db-up` starts PostgreSQL alone (`deploy/docker/compose.dev.yml`, bound to `127.0.0.1`,
no password; `TAKTUS_DB_PORT` when 5432 is taken); `make migrate` brings it to the current
schema; `make db-down` stops it and keeps its data. With `TAKTUS_DATABASE_URL` set, runs survive the process and a killed one resumes at
its last step boundary with `--resume`. Without it, `taktusctl run` uses the in-memory
implementation with a file snapshot and says so in its first line of output — development
only, not durable. Neither is a silent default. Every `TAKTUS_*` variable is listed in
`.env.example`, names only; the database URL is a secret and is registered in `CREDENTIALS.md`.

**Tenants and instances** are different boundaries (ADR-0020). Tenants share one instance and
one database, kept apart by a tenant column on every table and row-level security. Instances
share nothing. The Taktus project itself runs two instances: a development instance on `main`
and a project instance on a tagged release, so that a version under development can never take
down productive work.
