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
│   │       │   └── query/           # read side (CQRS)
│   │       └── ports/               # ports this component alone needs (run/ports/workers.py)
│   │   … identity/ command/ process/ run/ governance/ decision/ catalog/
│   │     accounting/ knowledge/ value/ ledger/
│   │
│   ├── ports/                       # cross-cutting ports
│   │   ├── worker.py                # CONTRACT 1 — execution units: the contract's shapes and the protocol
│   │   ├── connector.py             # CONTRACT 2 — tools and channels (MCP)
│   │   ├── model.py                 # CONTRACT 3 — models
│   │   ├── execution.py             # process | container | kubernetes
│   │   ├── persistence.py           # Repository[T] per aggregate, LedgerStore
│   │   ├── ledger.py                # facts in, chained entries out, verify
│   │   ├── objectstore.py  clock.py  telemetry.py
│   │   ├── queue.py  eventbus.py  secret.py
│   │
│   ├── adapters/
│   │   ├── driving/                 # cli/ (taktusctl) — later rest/ mcp/ sse/ channel/ admin/ webui/
│   │   └── driven/
│   │       ├── memory/              # DEVELOPMENT AND TEST ONLY: in-memory stores, optional file snapshot
│   │       ├── clock/               # the system clock, identifiers, randomness — the only place
│   │       ├── telemetry/           # noop; an OpenTelemetry exporter later
│   │       ├── workers/http/        # the worker port over HTTP and SSE; workers/pool.py maps capabilities
│   │       ├── postgres/ objectstore/ secret/ execution/ ledger/
│   │       ├── connectors/{github,chat,http}/
│   │       └── models/{openai_compatible,anthropic,ollama}/
│   │
│   ├── wire/                        # wire formats (SSE) shared by conformance and driven adapters
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core
│   │
│   └── composition/                 # composition root: local.py wires a developer's machine, taktusctl.py is the console script
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
├── examples/processes/              # process bundles that run as they are; each exercised by a test
├── web/                             # SvelteKit app, embedded into the image
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   ├── contract/                    # the Python bindings match the schemas and their examples
│   ├── components/ adapters/        # domain tables and application tests against fakes/
│   ├── integration/                 # the whole slice against the reference worker
│   └── security/ resilience/
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
the rest of Taktus.

`tests/architecture` fails on:

- the core importing `httpx`, `sqlalchemy`, `psycopg`, `fastapi` or any driver
- **a product name in `components/**` or `ports/**`** (`claude`, `slack`, `github`, `jira`,
  `ollama`, …) — the sharpest test in the project
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
| Context | actor and tenant travel in an explicit `ActorContext` argument, never in a context variable read by business code |
| Time, randomness, IDs | only through ports (`ports/clock.py`) — otherwise no run is reproducible; enforced by `tests/architecture` |
| Logging | `structlog`, structured, never personal data, always with `trace_id` |
| Secrets | never a bare `str` — a `Secret` type masks on `repr`, `str` and serialisation |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain |
| Shared kernel binding | `src/taktus/shared/v1/` is hand-written and **machine-checked**, not generated: one frozen model per schema of `contracts/shared/v1`, one module per schema file, and `tests/contract` fails on any difference in properties, required fields, enumerations or patterns, and runs every example of the contract through the models. The same holds for the worker contract's shapes in `ports/worker.py`. Why not generation: the schemas carry conditional rules (`if`/`then` over a step's method, "at least one quantity") that no generator turns into a constructor check, and the components need exactly those checks in the constructor; generating the shape and hand-writing the rules would be two files per concept with the seam in the wrong place. A checked binding is one file, and drift is a red test |
| Generated code | `api/openapi.yaml` from the REST interface, once it exists — never edited by hand; `make generate` is its one place |
| Types | `mypy --strict` across `src/`; no `Any` without a comment saying why |
| Tests | domain = table tests, no mocks; application = fakes of the ports (`tests/fakes/`); driven adapters = testcontainers |
| Ledger facts | what a component tells the ledger is a `Fact` (`ports/ledger.py`): identifiers, method, adapter, measured consumption, an outcome *token*, a content digest — never text. A reason stays on the run; the ledger is content-free by construction |
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
