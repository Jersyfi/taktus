# Taktus

**An operating layer for a business.**

A person states what should be achieved. Taktus breaks that into processes, decides for each step
which *method* is best suited to it, runs it or has it run, measures the result, corrects within an
agreed frame, and reports back.

Taktus does not replace ticket systems, repositories or knowledge tools. It conducts them.

Python, PostgreSQL, Explicit Architecture. Self-hostable from day one.

> **Status: draft, on the way to `0.1.0`.** The contracts, the conformance suite, the first
> vertical slice of the control plane and the daemon exist: a process bundle runs against a
> worker, every step lands in a verifiable ledger, a stop resumes at a step boundary, a step
> that would breach the budget never starts, the state lives in PostgreSQL, and Taktus runs as
> a service — two containers, several runners that never claim the same run, one elected
> scheduler, a shutdown that lands on a step boundary, a killed container that resumes at its
> last boundary. A `worker` step runs in an isolated container the control plane starts per
> job, and a coding agent works behind the worker contract, so that Taktus can have code
> written for it. Without governance. What runs today: [examples/README.md](examples/README.md).
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
| [workers/README.md](workers/README.md) | The workers of this repository, each in its own image: the reference worker, and the coding worker with what it can and cannot do |
| [docs/architecture/project-structure.md](docs/architecture/project-structure.md) | Components, tree, dependency rules, conventions |
| [examples/README.md](examples/README.md) | Running a process bundle with `uv run taktusctl run`; the shape of a bundle |
| [blueprints/dev-orchestration/README.md](blueprints/dev-orchestration/README.md) | The dev-orchestration blueprint: P-02 Refinement and P-03 Implementation run; the rest remain descriptions |
| [docs/runs/](docs/runs/) | What happened when Taktus was used rather than tested: one record per run worth keeping, with what each step consumed against what was estimated, where a person had to step in, and every piece of friction. [first-run.md](docs/runs/first-run.md) is the first issue of this repository that became a pull request opened by Taktus |
| [docs/adr/README.md](docs/adr/README.md) | every architecture decision with the alternatives rejected |
| [docs/status.md](docs/status.md) | Where the project stands and what is needed from the owner, kept current by every pull request |
| [docs/decisions/](docs/decisions/README.md) | The project's decision register: which questions reach the owner, what was answered, and what only the owner can provide |
| [docs/roadmap.md](docs/roadmap.md) | Milestones `0.1.0` to `1.0.0` |
| [docs/usecases/](docs/usecases/) | The worked use cases |

---

## Technology

| Area | Choice |
|---|---|
| Language | Python ≥ 3.13, `asyncio` throughout |
| Database | PostgreSQL 16+ — state, queue, outbox, ledger, vector search (`pgvector`) |
| API | FastAPI, OpenAPI 3.1 (`api/openapi.yaml`, generated and committed), RFC 9457 problem details, everything under a configurable path prefix; SSE later |
| Agent and tool interface | MCP — Taktus is a client of every connector (`contracts/connector/v1`, the `mcp` package for the suite and the reference connector), and exposes itself as a server later |
| Domain types | Pydantic v2 value objects; SQLAlchemy Core at the boundary, never in the domain — the adapter stores an aggregate's document and never imports its class |
| Shared kernel | JSON Schema under `contracts/shared`, bound to Python by hand and checked by a test |
| Process bundles | YAML, read by PyYAML in the command-line adapter only |
| Migrations | Alembic, `make migrate`; every table tenant-scoped with row-level security, the ledger and the provenance append-only in the database (ADR-0020, ADR-0021) |
| ML bench | scikit-learn, PyTorch, sentence-transformers — as a worker, never in the core |
| Architecture enforcement | `import-linter` contracts, run in CI |
| Tooling | `uv`, `ruff`, `mypy --strict`, `pytest`, `testcontainers`; `make gates` installs its own environment; `make doctor` says what is missing. `taktusctl` lives in that environment: `uv run taktusctl …`. Docker is optional: without it the PostgreSQL tests skip and say so; CI runs them |
| Observability | OpenTelemetry from day one: spans for run, step, worker and connector calls, exported where `TAKTUS_OTLP_*` names an endpoint; the trace identifier is on every ledger entry and log line |
| Web | SvelteKit, embedded into the image |
| Deployment | one image for the control plane, roles via `TAKTUS_ROLES`; one image per worker, none of them in the control plane image; Docker Compose for self-hosting (`make up`), Kubernetes for scale |
| Execution | `TAKTUS_EXECUTION`: a worker by endpoint, a unit started per job as a process (development only; refused from autonomy level 3), or as a container with limits, credentials in memory and a network allowlist — over the engine's API, Docker or Podman |

---

## Operating it

The control plane is **two containers**: Taktus and PostgreSQL. Everything else the control
plane needs is a port with a default adapter that needs no extra service. What those two
containers can do on their own is run every process built from `rule`, `statistics`, `wait`
and `human` steps.

Every process that has a `worker` step needs **one execution unit** in addition — a worker,
a separate deployable behind the worker contract, in its own image. A process built without
worker steps needs none, and method maturation moves processes in that direction over time
(`docs/architecture/methods.md`). No worker code is part of the control plane image: a worker
executes foreign code, and code that is not in the image cannot be started from a compromised
control plane (DEC-0011).

- **Docker Compose:** all roles in one container (`deploy/docker/compose.yml`); a worker is
  configured by endpoint, or started per job by the execution port.
- **Kubernetes:** one deployment per role, each scaled independently — the chart arrives with
  the next pull request; the daemon already scales that way: runners claim work through
  database locks and never claim the same run, the scheduler is one instance elected by an
  advisory lock, and every process answers health and readiness.

Workers run isolated — as a process (local development only), as a container (the default in
operation) or, next, as a pod. **The process adapter is not permitted from autonomy level 3
upwards**, and the refusal is in code: an unknown level is refused too. The container adapter
gives every job CPU, memory and wall-clock limits, credentials that live in memory only, a
network that reaches the hosts its frame names and nothing else, and no access to the
engine's socket (`docs/architecture/contracts.md` §2.4).

**Operating it is one command.**

```bash
make up
```

It writes the two secret files the containers read (a random database password and the URL
that carries it, under `deploy/docker/secrets/`, never committed), builds the image, starts
PostgreSQL and Taktus, applies the migrations on start, and returns when readiness answers.
Two containers: Taktus with every role in one process (`TAKTUS_ROLES=all`, the self-hosting
shape), and PostgreSQL. `make down` stops them and keeps every volume. `make up-dev` adds the
reference worker in its own image, for trying a bundle out
(`deploy/docker/compose.reference-worker.yml`, development only).

**Readiness means** the database answers and is at the schema this build needs:
`GET /ready` answers `200`, or `503` with the reason. **Health means** the process is alive:
`GET /health`. A container that has lost its database is not ready and receives no traffic; it
is not therefore unhealthy, and nothing restarts it in a loop. A daemon refuses to start against
a database whose schema does not match the binary: silent drift is worse than a refusal.

Everything is configured through `TAKTUS_*` variables, validated at start with a message that
names the variable; a secret is read from a file the variable points at
(`TAKTUS_DATABASE_URL_FILE`), never from the environment; the effective configuration is
logged with every secret masked. `.env.example` lists every variable, names only.
`deploy/docker/README.md` has the rest: the HTTP surface, `taktusctl submit`, the shutdown,
and `make verify-compose`, which proves from nothing that a killed container resumes its run
at the last step boundary.

**On a developer's machine**, without the container:

```bash
make db-up
```

```bash
export TAKTUS_DATABASE_URL=postgresql://taktus@127.0.0.1:5432/taktus && make migrate
```

```bash
export TAKTUS_PROVISIONAL_IDENTITY=default=idn_owner && uv run taktusctl run --process examples/processes/six-times-seven.yaml
```

Nothing executes without an identity: until the identity component exists, the identity every
command of a tenant acts as is configured — `TAKTUS_PROVISIONAL_IDENTITY`, provisional and
named so (DEC-0013) — or given as `--identity`. `make db-up` starts PostgreSQL alone (`deploy/docker/compose.dev.yml`, bound to `127.0.0.1`,
no password — which is why the URL may be inline here; `TAKTUS_DB_PORT` when 5432 is taken);
`make migrate` brings it to the current schema; `make db-down` stops it and keeps its data.
`uv run taktusd` then runs the daemon against the same database, and `uv run taktusctl submit`
queues a bundle for it. With `TAKTUS_DATABASE_URL` set, runs survive the process and a killed
one resumes at its last step boundary. Without it, `taktusctl run` uses the in-memory
implementation with a file snapshot and says so in its first line of output — development
only, not durable, and `taktusd` refuses to start. Neither is a silent default. The database
URL is a secret, and `CREDENTIALS.md` describes it as a parameter.

**Tenants and instances** are different boundaries (ADR-0020). Tenants share one instance and
one database, kept apart by a tenant column on every table and row-level security. Instances
share nothing. The Taktus project itself runs two instances: a development instance on `main`
and a project instance on a tagged release, so that a version under development can never take
down productive work.
