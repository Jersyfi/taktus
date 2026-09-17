# Project structure and conventions

Explicit Architecture (ADR-0016): DDD layers, ports and adapters, onion and CQRS brought together.
The coarse cut is by **component** (bounded context); layers live inside each component.

Python ≥ 3.13 for everything server-side (ADR-0001). Because there is no compiler enforcing the
boundaries, `import-linter` contracts and `tests/architecture` are not optional — they belong to
`0.1.0`.

---

## 1. Components

| Component | Owns |
|---|---|
| `identity` | tenants, accounts, org structure, channel identity, roles |
| `command` | channel normalisation, command, plan, commissioning |
| `process` | process, version, step, method, exactness class, bundle |
| `run` | run, step run, checkpoint, artifact, blocked-time account |
| `governance` | autonomy levels, policies, anchors, budgets, limits, admission control; today: whether a result has left the system (ADR-0022) |
| `decision` | decision requests, the decision register, rules derived from it |
| `catalog` | models, agents, skills, connectors, blueprints, maturity |
| `accounting` | consumption capture, Takt, forecasts, marginal value |
| `knowledge` | knowledge sources, embeddings, citations |
| `value` | value ledger, cost and benefit entries, revert analysis |
| `ledger` | hash chain, verification, export |

**Rules between components:** no direct import · communication through events · reading another
component's data is allowed, writing is not · what is shared lives in the **language-neutral** shared
kernel (JSON Schema under `contracts/shared/`, bound to Python under `src/taktus/shared/` — see §4,
*Shared kernel binding*).

**Where the first slice draws its lines.** `run` applies admission control (ADR-0005) against the
budget a run is given; the budgets, limits and policies themselves belong to `governance` and
arrive with `0.2.0`. `command` commissions a plan from steps it receives as shared-kernel `Step`s;
the process version that holds those steps is `process`'s, and the two never import each other.
What a step *does* when it runs — its `work` — is carried by the process version as data and
interpreted by `run` (`examples/README.md`); its shape belongs to the bundle format of `0.3.0`.

---

## 2. Tree

```
taktus/
├── src/taktus/
│   ├── shared/v1/                   # shared kernel binding — one frozen model per schema, checked by tests/contract
│   ├── components/
│   │   └── process/                 # every component has the same shape
│   │       ├── domain/
│   │       │   ├── model/           # Process, ProcessVersion, Edge, Trigger, Slo; Step is the kernel's
│   │       │   ├── service/         # validation (graph and step rules); later MethodSelection, Planner
│   │       │   └── event/
│   │       ├── application/
│   │       │   ├── service/         # one use case per module
│   │       │   └── query/           # read side (CQRS): run/application/query/provenance.py walks and verifies the chain
│   │       └── ports/               # ports this component alone needs (run/ports/workers.py)
│   │   … run/domain/service/provenance.py builds and verifies the provenance chain (ADR-0021)
│   │   … governance/domain/service/egress.py decides whether a result has left the system (ADR-0022)
│   │   … identity/ command/ process/ run/ governance/ decision/ catalog/
│   │     accounting/ knowledge/ value/ ledger/
│   │
│   ├── ports/                       # cross-cutting ports
│   │   ├── worker.py                # CONTRACT 1 — execution units: the contract's shapes and the protocol
│   │   ├── connector.py             # CONTRACT 2 — tools and channels (MCP)
│   │   ├── model.py                 # CONTRACT 3 — models
│   │   ├── execution.py             # process | container | kubernetes
│   │   ├── persistence.py           # Repository[T] per aggregate, LedgerStore, ProvenanceStore, UnitOfWork — every call names its tenant
│   │   ├── ledger.py                # facts in, chained entries out, verify — one chain per tenant
│   │   ├── configuration.py         # what an instance is told about itself, by key; Secret
│   │   ├── objectstore.py  clock.py  telemetry.py
│   │   ├── queue.py  eventbus.py  secret.py
│   │
│   ├── adapters/
│   │   ├── driving/                 # cli/ (taktusctl) — later rest/ mcp/ sse/ channel/ admin/ webui/
│   │   └── driven/
│   │       ├── memory/              # DEVELOPMENT AND TEST ONLY: in-memory stores, optional file snapshot
│   │       ├── postgres/            # the persistence port over PostgreSQL: SQLAlchemy Core, one mapper per aggregate; ledger and provenance stores
│   │       ├── configuration/       # the configuration port over TAKTUS_* environment variables
│   │       ├── clock/               # the system clock, identifiers, randomness — the only place
│   │       ├── telemetry/           # noop; an OpenTelemetry exporter later
│   │       ├── workers/http/        # the worker port over HTTP and SSE; workers/pool.py maps capabilities
│   │       ├── objectstore/ secret/ execution/ ledger/
│   │       ├── connectors/github/   # the reference connector: an MCP server behind contracts/connector/v1; the product name lives only here
│   │       ├── connectors/{chat,http}/
│   │       └── models/{openai_compatible,anthropic,ollama}/
│   │
│   ├── wire/                        # wire formats (SSE) shared by conformance and driven adapters
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core; connector/ is its MCP half
│   │
│   └── composition/                 # composition root: local.py wires a developer's machine (memory or database), taktusctl.py is the console script
│
├── workers/                         # separate deployables behind the worker contract
│   ├── script/ claudecode/ codex/
│   └── mlbench/                     # training, evaluation, embeddings, classical ML
│
├── contracts/                       # what third parties implement — JSON Schema
│   └── worker/v1/ connector/v1/ model/v1/ process/v1/ events/v1/ shared/v1/
│
├── api/openapi.yaml                 # Taktus' OWN REST interface, generated from FastAPI
├── migrations/                      # Alembic: alembic.ini, env.py, versions/ — explicit DDL, one head
├── deploy/{docker,k8s,observability}/   # docker/compose.dev.yml is the development database
├── blueprints/{dev-orchestration,it-operations}/
├── examples/processes/              # process bundles that run as they are; each exercised by a test
├── web/                             # SvelteKit app, embedded into the image
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   ├── contract/                    # the Python bindings match the schemas and their examples
│   ├── components/ adapters/        # domain tables and application tests against fakes/; adapters/persistence: one suite, both implementations; adapters/connectors: the reference connector against fakes/repository_service.py
│   ├── integration/                 # the whole slice against the reference worker; the restart test against PostgreSQL
│   └── security/ resilience/
│
├── docs/{architecture,adr,usecases,roadmap.md}
├── tools/                           # gates, checkdocs, preflight, generators
├── pyproject.toml  Makefile  .importlinter  .env.example   # .env.example lists TAKTUS_* names, never values
└── CLAUDE.md  README.md  LICENSE  NOTICE  CONTRIBUTING.md  CREDENTIALS.md
```

---

## 3. Dependency rules (enforced by `import-linter`)

```
composition          → everything
adapters.driving     → components.*.application, ports, shared, conformance
adapters.driven      → ports, shared, wire
conformance          → contracts, wire                   — nothing else in src/taktus
wire                 → nothing                           — stdlib only
workers/*            → contracts only                    — NEVER src/taktus
components.X         → components.X, ports, shared
ports                → shared
shared               → nothing
```

A driving adapter calls application services and never builds them: the composition root
implements what the adapter declares it needs (`adapters/driving/cli/wiring.py`) and starts it.
That is why the console script `taktusctl` begins in `composition/taktusctl.py`.

`wire` holds what two readers of one wire format share — today the Server-Sent Events reader,
used by the conformance suite and by the HTTP worker adapter. Neither may import the other, so
what they share lives in a package that imports nothing from either and no technology.

`conformance` is the executable reading of a contract, run against a live adapter. It is a
client, as a foreign control plane would be, and therefore imports nothing from the control
plane; `taktusctl conformance` (a driving adapter) is its entry point, and `tests/conformance` its
gate. It ships in the wheel together with `contracts/`, so that a third party can run it without
the rest of Taktus. It speaks HTTP and SSE to a worker and MCP to a connector; the reference
connector is a driven adapter and the suite its client, and neither imports the other.

`tests/architecture` fails on:

- the core importing `httpx`, `sqlalchemy`, `psycopg`, `fastapi` or any driver
- **a product name in `components/**` or `ports/**`** (`claude`, `slack`, `github`, `jira`,
  `ollama`, …) — the sharpest test in the project — and in `contracts/**`, where a connector is
  named by what it can do and never by what it is
- a direct import between two components
- a write by one component into another's data
- `workers/**` importing `src/taktus/**`
- a domain model that is not frozen and closed
- the core reading the clock, minting an identifier or drawing randomness by itself — only
  through `ports/clock.py`; `adapters/driven/clock/` is the one place that does
- the core importing anything but the standard library, pydantic and itself

---

## 4. Conventions

| Topic | Rule |
|---|---|
| Modules | `snake_case`; one use case per module |
| Domain types | frozen Pydantic models or dataclasses; invariants checked in the constructor, never after |
| Application services | one `Command`/`Query` dataclass, one `Handler` with `async def execute(self, cmd) -> Result` |
| Errors | typed exceptions in each component's `domain/model/errors.py` |
| Async | `async` throughout; no blocking call in a coroutine, enforced by lint |
| Context | actor and tenant travel as explicit arguments — today as fields of every command (`StartRun.tenant`), later bundled in an `ActorContext` — never in a context variable read by business code |
| Time, randomness, IDs | only through ports (`ports/clock.py`) — otherwise no run is reproducible; enforced by `tests/architecture` |
| Logging | `structlog`, structured, never personal data, always with `trace_id` |
| Secrets | never a bare `str` — `ports/configuration.py`'s `Secret` masks on `repr` and `str`; `reveal()` is the one way to the value, and the database URL is read as one |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Provenance | one record per completed step run (ADR-0021), built by `run/domain/service/provenance.py` and written by the engine in the transaction of the `step.finished` entry; the `ProvenanceStore` port is append-only like the `LedgerStore`, and the database refuses update and delete. A record references — identifiers, tokens, digests — and never copies. The worker's own version reaches the record through `Capabilities.version` and the pool's `ResolvedWorker` |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain. **Every repository call names its tenant** as an explicit parameter (ADR-0020); the adapter refuses another tenant than the open transaction's, and an aggregate that carries its tenant carries the one it is stored under. **Every call happens inside a unit of work** (`ports/persistence.py`, `UnitOfWork.transaction(tenant)`), opened by the application layer — a handler, the run engine — never by an adapter or the domain; a call outside one raises, blocks do not nest, and a store that raises inside a block spoils it. **An adapter stores documents, not classes:** it never imports a component (§3), so the composition root binds the aggregate class and the adapter maps `document()` to rows and back — one mapper per aggregate in `adapters/driven/postgres/_mapping.py`. **A foreign key never crosses a component boundary;** inside an aggregate, children hang off their parent and are replaced with it; a copy (the steps of a plan, of a run) is one JSON column, the source (the process version's steps) is rows. The tables live in `_schema.py`, the history in `migrations/`, and `tests/adapters/persistence` fails on drift between them |
| Shared kernel binding | `src/taktus/shared/v1/` is hand-written and **machine-checked**, not generated: one frozen model per schema of `contracts/shared/v1`, one module per schema file, and `tests/contract` fails on any difference in properties, required fields, enumerations or patterns, and runs every example of the contract through the models. The same holds for the worker contract's shapes in `ports/worker.py`. Why not generation: the schemas carry conditional rules (`if`/`then` over a step's method, "at least one quantity") that no generator turns into a constructor check, and the components need exactly those checks in the constructor; generating the shape and hand-writing the rules would be two files per concept with the seam in the wrong place. A checked binding is one file, and drift is a red test |
| Generated code | `api/openapi.yaml` from the REST interface, once it exists — never edited by hand; `make generate` is its one place |
| Types | `mypy --strict` across `src/`; no `Any` without a comment saying why |
| Tests | domain = table tests, no mocks; application = fakes of the ports (`tests/fakes/`); driven adapters = testcontainers. **One suite per port, run against every implementation** (`tests/adapters/persistence`: the memory adapter and PostgreSQL answer the same assertions; a disagreement is a finding about the port, and the port gains the rule) |
| Ledger facts | what a component tells the ledger is a `Fact` (`ports/ledger.py`): identifiers, method, adapter, measured consumption, an outcome *token*, a content digest — never text. A reason stays on the run; the ledger is content-free by construction |
| Language | everything in English — code, comments, commits, documentation |
| Commands in documentation | every invocation shown is the one that works from a checkout. `taktusctl`, `taktusd` and every module of the package live in the project environment and not on the machine's path, so a command is written `uv run taktusctl …`, `uv run taktusd`, `uv run python -m …`; never bare. A tool that is on the path (`make`, `docker`, `python3 workers/script/worker.py`, which needs nothing installed) is written bare |

---

## 5. Roles at runtime

One image, roles via `TAKTUS_ROLES`. Each role is justified because its scaling behaviour or its
failure effect differs from the others.

| Role | Runs | Scales with | Effect if it stops |
|---|---|---|---|
| `api` | REST, MCP, SSE, channel intake, web UI, admin | users and channel events | the interface is down, runs continue |
| `runner` | run execution, admission control, worker delegation | concurrent runs | runs halt at step boundaries, nothing is lost |
| `scheduler` | time triggers, deadlines, budget windows, reports | not at all — must be singular | triggers are late |
| `automation` | event reactions, drift checks, method review, proposals | event rate | proposals are late, operation unaffected |

**No role executes AI.** Anything that runs or trains a model is a worker behind the contract. As a
role it would tie the core to a model stack and the removal test would be lost.
