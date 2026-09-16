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
| `governance` | autonomy levels, policies, anchors, budgets, limits, admission control |
| `decision` | decision requests, the decision register, rules derived from it |
| `catalog` | models, agents, skills, connectors, blueprints, maturity |
| `accounting` | consumption capture, Takt, forecasts, marginal value |
| `knowledge` | knowledge sources, embeddings, citations |
| `value` | value ledger, cost and benefit entries, revert analysis |
| `ledger` | hash chain, verification, export |

**Rules between components:** no direct import · communication through events · reading another
component's data is allowed, writing is not · what is shared lives in the **language-neutral** shared
kernel (JSON Schema, generated into `src/taktus/shared/`).

---

## 2. Tree

```
taktus/
├── src/taktus/
│   ├── shared/                      # shared kernel — GENERATED from contracts/shared, never edited
│   ├── components/
│   │   └── process/                 # every component has the same shape
│   │       ├── domain/
│   │       │   ├── model/           # Process, ProcessVersion, Step, Method, Exactness, Bundle
│   │       │   ├── service/         # MethodSelection, Planner, Validation
│   │       │   └── event/
│   │       ├── application/
│   │       │   ├── service/         # one use case per module
│   │       │   ├── repository/      # abstract repository protocols
│   │       │   └── query/           # read side (CQRS)
│   │       └── ports/               # ports this component needs
│   │   … identity/ command/ run/ governance/ decision/ catalog/
│   │     accounting/ knowledge/ value/ ledger/
│   │
│   ├── ports/                       # cross-cutting ports
│   │   ├── worker.py                # CONTRACT 1 — execution units
│   │   ├── connector.py             # CONTRACT 2 — tools and channels (MCP)
│   │   ├── model.py                 # CONTRACT 3 — models
│   │   ├── execution.py             # process | container | kubernetes
│   │   ├── persistence.py  queue.py  eventbus.py
│   │   ├── objectstore.py  secret.py  telemetry.py  clock.py
│   │
│   ├── adapters/
│   │   ├── driving/                 # rest/ mcp/ sse/ cli/ channel/ admin/ webui/
│   │   └── driven/
│   │       ├── postgres/ objectstore/ secret/ execution/ telemetry/ ledger/
│   │       ├── connectors/{github,chat,http}/
│   │       └── models/{openai_compatible,anthropic,ollama}/
│   │
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core
│   │
│   └── composition/                 # composition root, dependency wiring, role runners
│
├── workers/                         # separate deployables behind the worker contract
│   ├── script/ claudecode/ codex/
│   └── mlbench/                     # training, evaluation, embeddings, classical ML
│
├── contracts/                       # what third parties implement — JSON Schema
│   └── worker/v1/ connector/v1/ model/v1/ process/v1/ events/v1/ shared/v1/
│
├── api/openapi.yaml                 # Taktus' OWN REST interface, generated from FastAPI
├── migrations/                      # Alembic
├── deploy/{docker,k8s,observability}/
├── blueprints/{dev-orchestration,it-operations}/
├── web/                             # SvelteKit app, embedded into the image
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   └── integration/ contract/ security/ resilience/ fixtures/
│
├── docs/{architecture,adr,usecases,roadmap.md}
├── tools/                           # gates, checkdocs, preflight, generators
├── pyproject.toml  Makefile  .importlinter
└── CLAUDE.md  README.md  LICENSE  NOTICE  CONTRIBUTING.md  CREDENTIALS.md
```

---

## 3. Dependency rules (enforced by `import-linter`)

```
composition          → everything
adapters.driving     → components.*.application, ports, shared, conformance
adapters.driven      → ports, shared
conformance          → contracts only                    — nothing in src/taktus
workers/*            → contracts only                    — NEVER src/taktus
components.X         → components.X, ports, shared
shared               → nothing
```

`conformance` is the executable reading of a contract, run against a live adapter. It is a
client, as a foreign control plane would be, and therefore imports nothing from the control
plane; `taktusctl conformance` (a driving adapter) is its entry point, and `tests/conformance` its
gate. It ships in the wheel together with `contracts/`, so that a third party can run it without
the rest of Taktus.

`tests/architecture` fails on:

- the core importing `httpx`, `sqlalchemy`, `psycopg`, `fastapi` or any driver
- **a product name in `components/**` or `ports/**`** (`claude`, `slack`, `github`, `jira`,
  `ollama`, …) — the sharpest test in the project
- a direct import between two components
- a write by one component into another's data
- `workers/**` importing `src/taktus/**`
- a domain model carrying serialisation concerns

---

## 4. Conventions

| Topic | Rule |
|---|---|
| Modules | `snake_case`; one use case per module |
| Domain types | frozen Pydantic models or dataclasses; invariants checked in the constructor, never after |
| Application services | one `Command`/`Query` dataclass, one `Handler` with `async def execute(self, cmd) -> Result` |
| Errors | typed exceptions in each component's `domain/model/errors.py` |
| Async | `async` throughout; no blocking call in a coroutine, enforced by lint |
| Context | actor and tenant travel in an explicit `ActorContext` argument, never in a context variable read by business code |
| Time, randomness, IDs | only through ports — otherwise no run is reproducible |
| Logging | `structlog`, structured, never personal data, always with `trace_id` |
| Secrets | never a bare `str` — a `Secret` type masks on `repr`, `str` and serialisation |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain |
| Generated code | `src/taktus/shared/`, `api/openapi.yaml`, contract types — never edited by hand |
| Types | `mypy --strict` across `src/`; no `Any` without a comment saying why |
| Tests | domain = table tests, no mocks; application = fakes of the ports; driven adapters = testcontainers |
| Language | everything in English — code, comments, commits, documentation |

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
