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
│   │       └── ports/               # ports this component alone needs (run/ports/workers.py, connectors.py, models.py)
│   │   … run/domain/service/provenance.py builds and verifies the provenance chain (ADR-0021)
│   │   … governance/domain/service/egress.py decides whether a result has left the system (ADR-0022)
│   │   … catalog/domain/model/maturity.py is an adapter's maturity with its last removal result; catalog/domain/service/removal.py the rules that decide broke, changed or exception; catalog/application/service/record_removal.py writes the result and the ledger entry `removal.tested`
│   │   … identity/ command/ process/ run/ governance/ decision/ catalog/
│   │     accounting/ knowledge/ value/ ledger/
│   │
│   ├── ports/                       # cross-cutting ports
│   │   ├── worker.py                # CONTRACT 1 — execution units: the contract's shapes and the protocol
│   │   ├── connector.py             # CONTRACT 2 — tools and channels: intake, and actions with a call context, a declared effect and a classified failure
│   │   ├── model.py                 # CONTRACT 3 — models: a prompt in, a completion with its tokens and the answering model out; resolved by purpose
│   │   ├── execution.py             # how a unit comes to exist for a job: process | container | cluster; the fail-closed refusal of no isolation from level 3
│   │   ├── persistence.py           # Repository[T] per aggregate, LedgerStore, ProvenanceStore, UnitOfWork — every call names its tenant
│   │   ├── ledger.py                # facts in, chained entries out, verify — one chain per tenant
│   │   ├── identity.py              # who acts: a sender on a channel placed in a tenant as an identity; served PROVISIONALLY by adapters/driven/identity (DEC-0013)
│   │   ├── configuration.py         # what an instance is told about itself, by key; Secret; ConfigurationError
│   │   ├── queue.py                 # jobs a runner claims once, as a lease it renews (ADR-0002)
│   │   ├── leadership.py            # one instance leads a singular role; a dead leader is replaced
│   │   ├── objectstore.py  clock.py  telemetry.py
│   │   ├── eventbus.py  secret.py
│   │
│   ├── adapters/
│   │   ├── driving/
│   │   │   ├── cli/                 # taktusctl: conformance run, run, submit
│   │   │   └── rest/                # the HTTP surface: health, readiness, webhook intake, the read API — under a prefix; RFC 9457 problems
│   │   └── driven/
│   │       ├── memory/              # DEVELOPMENT AND TEST ONLY: in-memory stores, queue and leadership, optional file snapshot
│   │       ├── postgres/            # persistence, queue (claim_jobs with a lease) and leadership (advisory lock) over PostgreSQL; SQLAlchemy Core
│   │       ├── configuration/       # the configuration port over TAKTUS_* variables; a secret from the file TAKTUS_<KEY>_FILE names
│   │       ├── clock/               # the system clock, identifiers, randomness — the only place
│   │       ├── telemetry/           # otel: real spans, exported where TAKTUS_OTLP_* says; noop for tests
│   │       ├── workers/http/        # the worker port over HTTP and SSE; workers/pool.py maps capabilities; workers/launched.py puts the port over the execution port
│   │       ├── execution/           # process.py: a unit as a child process; container/: a unit per job in a container with limits, credentials in memory, an egress proxy
│   │       ├── objectstore/ secret/ ledger/
│   │       ├── connectors/github/   # the reference connector: an MCP server behind contracts/connector/v1; the product name lives only here
│   │       ├── connectors/mcp/      # the connector port as an MCP client: intake and actions; connectors/pool.py maps capabilities
│   │       ├── connectors/loopback/ # Taktus reached by Taktus: the capabilities orchestrator.* behind the action side of the connector port, over an Orchestrator the composition root implements
│   │       ├── connectors/{chat,http}/
│   │       ├── identity/            # PROVISIONAL: one configured operator identity per tenant, until the identity component (DEC-0013)
│   │       └── models/              # openai_compatible/: the model port over the chat-completions dialect; pool.py maps purposes
│   │
│   ├── wire/                        # wire formats (SSE) shared by conformance and driven adapters
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core; connector/ is its MCP half
│   │
│   └── composition/                 # composition root: daemon.py wires and runs taktusd (settings.py, roles.py, logging.py); local.py wires taktusctl; execution.py opens the worker and the telemetry both share; loopback.py is the instance behind the loopback connector — pools with one adapter withheld, rehearsal runs, the removal verdict observed
│
├── workers/                         # separate deployables behind the worker contract, each with its own image; none in the control plane image (DEC-0011)
│   ├── script/                      # the reference worker: shell commands, no AI
│   ├── claudecode/                  # the coding worker: a coding agent behind the contract, and the fake agent the gate runs it against
│   ├── codex/                       # the second coding worker (0.4.0)
│   └── mlbench/                     # training, evaluation, embeddings, classical ML (0.4.0)
│
├── contracts/                       # what third parties implement — JSON Schema
│   └── worker/v1/ connector/v1/ model/v1/ process/v1/ events/v1/ shared/v1/
│
├── api/openapi.yaml                 # Taktus' OWN REST interface, generated from FastAPI by `make generate`, committed, held current by a test
├── migrations/                      # Alembic: alembic.ini, env.py, versions/ — explicit DDL, one head
├── deploy/{docker,k8s,observability}/   # docker/compose.yml: Taktus and PostgreSQL, `make up`; compose.reference-worker.yml: the worker layered in for development; compose.dev.yml: the development database
├── blueprints/{dev-orchestration,it-operations,self-operation}/   # self-operation: what Taktus runs for itself — S-01 the removal test, weekly
├── examples/processes/              # process bundles that run as they are; each exercised by a test
├── web/                             # SvelteKit app, embedded into the image
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   ├── contract/                    # the Python bindings match the schemas and their examples
│   ├── components/ adapters/        # domain tables and application tests against fakes/; adapters/persistence and adapters/queue: one suite, both implementations; adapters/connectors: the reference connector against fakes/repository_service.py; adapters/rest: the surface under two prefixes; adapters/execution: the process adapter, and the container adapter checked from inside a job; adapters/telemetry: spans nested, the trace id on every entry, no person and no secret in an attribute
│   ├── composition/                 # the daemon's settings, and that no secret reaches a log line
│   ├── integration/                 # the whole slice against the reference worker — by endpoint, as a process started per job, as a container started per job; the restart test; two runners, two schedulers, a real SIGTERM, the daemon under a prefix; the control plane image built and inspected
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
implements what the adapter declares it needs (`adapters/driving/cli/wiring.py`,
`adapters/driving/rest/wiring.py`) and starts it. That is why the console script `taktusctl`
begins in `composition/taktusctl.py` and `taktusd` in `composition/daemon.py` — the one place
that constructs an adapter and binds it to a port; anything else that did would be a finding.

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
| Logging | `structlog`, structured, never personal data; every line written inside a span carries `trace_id`, the same identifier the engine writes into its ledger entries (`composition/logging.py`) |
| Secrets | never a bare `str` — `ports/configuration.py`'s `Secret` masks on `repr` and `str`; `reveal()` is the one way to the value, and the database URL is read as one. **A secret is read from a file, not from the environment:** `TAKTUS_<KEY>_FILE` holds the path, the file holds the value; the inline variable is accepted for a value that carries no secret (the development database) and refused together with the file. The daemon logs its effective configuration at start with every secret masked and its source named, and `tests/composition` proves that no secret value reaches a line |
| Configuration | every setting is a `TAKTUS_*` variable, read through the configuration port and validated once at start (`composition/settings.py`); a wrong one is refused with one sentence naming the variable, never a stack trace. `.env.example` lists every variable, names only. A credential an assignment references is read at the moment a unit is started, under `credential.<name>` — `TAKTUS_CREDENTIAL_<NAME>_FILE` |
| Execution | `TAKTUS_EXECUTION` chooses how a `worker` step's unit comes to exist: by endpoint, as a process, as a container (`docs/architecture/contracts.md` §2.4). The `process` adapter is refused from autonomy level 3 upwards and when the level is unknown; the rule lives in `ports/execution.py` and `tests/governance` holds the adapter to it |
| Telemetry | spans for the run, every step, every worker call and every connector call, nested; consumption and method as attributes; no person and no secret in an attribute (`tests/adapters/telemetry`); exported where `TAKTUS_OTLP_*` says, real either way |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Provenance | one record per completed step run (ADR-0021), built by `run/domain/service/provenance.py` and written by the engine in the transaction of the `step.finished` entry; the `ProvenanceStore` port is append-only like the `LedgerStore`, and the database refuses update and delete. A record references — identifiers, tokens, digests — and never copies. The worker's own version reaches the record through `Capabilities.version` and the pool's `ResolvedWorker` |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain. **Every repository call names its tenant** as an explicit parameter (ADR-0020); the adapter refuses another tenant than the open transaction's, and an aggregate that carries its tenant carries the one it is stored under. **Every call happens inside a unit of work** (`ports/persistence.py`, `UnitOfWork.transaction(tenant)`), opened by the application layer — a handler, the run engine — never by an adapter or the domain; a call outside one raises, blocks do not nest, and a store that raises inside a block spoils it. **An adapter stores documents, not classes:** it never imports a component (§3), so the composition root binds the aggregate class and the adapter maps `document()` to rows and back — one mapper per aggregate in `adapters/driven/postgres/_mapping.py`. **A foreign key never crosses a component boundary;** inside an aggregate, children hang off their parent and are replaced with it; a copy (the steps of a plan, of a run) is one JSON column, the source (the process version's steps) is rows. The tables live in `_schema.py`, the history in `migrations/`, and `tests/adapters/persistence` fails on drift between them |
| Shared kernel binding | `src/taktus/shared/v1/` is hand-written and **machine-checked**, not generated: one frozen model per schema of `contracts/shared/v1`, one module per schema file, and `tests/contract` fails on any difference in properties, required fields, enumerations or patterns, and runs every example of the contract through the models. The same holds for the worker contract's shapes in `ports/worker.py`. Why not generation: the schemas carry conditional rules (`if`/`then` over a step's method, "at least one quantity") that no generator turns into a constructor check, and the components need exactly those checks in the constructor; generating the shape and hand-writing the rules would be two files per concept with the seam in the wrong place. A checked binding is one file, and drift is a red test |
| Generated code | `api/openapi.yaml` from the REST interface — never edited by hand; `make generate` is its one place, the file is committed so that the interface can be read without running anything, and `tests/adapters/rest/test_openapi.py` fails when it differs from what `make generate` writes |
| Types | `mypy --strict` across `src/`; no `Any` without a comment saying why |
| Tests | domain = table tests, no mocks; application = fakes of the ports (`tests/fakes/`); driven adapters = testcontainers. **One suite per port, run against every implementation** (`tests/adapters/persistence`: the memory adapter and PostgreSQL answer the same assertions; a disagreement is a finding about the port, and the port gains the rule) |
| Ledger facts | what a component tells the ledger is a `Fact` (`ports/ledger.py`): identifiers, method, adapter, measured consumption, an outcome *token*, a content digest — never text. A reason stays on the run; the ledger is content-free by construction |
| Language | everything in English — code, comments, commits, documentation |
| Commands in documentation | every invocation shown is the one that works from a checkout. `taktusctl`, `taktusd` and every module of the package live in the project environment and not on the machine's path, so a command is written `uv run taktusctl …`, `uv run taktusd`, `uv run python -m …`; never bare. A tool that is on the path (`make`, `docker`, `python3 workers/script/worker.py`, which needs nothing installed) is written bare |

---

## 5. Roles at runtime

One image, roles via `TAKTUS_ROLES`; `all` runs every role in one process, which is the
self-hosting shape and not a development convenience (`deploy/docker/compose.yml`). Each role
is justified because its scaling behaviour or its failure effect differs from the others.

| Role | Runs | Scales with | Effect if it stops |
|---|---|---|---|
| `api` | REST, MCP, SSE, channel intake, web UI, admin | users and channel events | the interface is down, runs continue |
| `runner` | run execution, admission control, worker delegation | concurrent runs | runs halt at step boundaries, nothing is lost |
| `scheduler` | time triggers, deadlines, budget windows, reports | not at all — must be singular | triggers are late |
| `automation` | event reactions, drift checks, method review, proposals | event rate | proposals are late, operation unaffected |

**No role executes AI.** Anything that runs or trains a model is a worker behind the contract. As a
role it would tie the core to a model stack and the removal test would be lost.

**How the roles turned out in operation** (`composition/daemon.py`, `composition/roles.py`):

- **Every process serves health and readiness**, whatever its roles, under the configured
  prefix; the `api` role adds intake and the read API. A platform probes each process the same
  way. Readiness is a question asked every time — the database answers and is at the schema
  this build needs — never a memory of an earlier answer; health is the process answering at
  all. A daemon refuses to start against a schema that does not match the binary.
- **`runner`** is the run component's `Runner` over the queue port: it claims due jobs for the
  tenants it serves, one transaction per claim, executes each through the engine's `resume`
  (which starts a submitted run, continues a halted one, or recovers one whose runner died),
  and renews the claim's lease from a heartbeat. Several runners share one database and never
  claim the same run; a runner that dies leaves its run for at most one lease. A run ends the
  job — completed when finished, halted by admission control or escalated; released when this
  runner was told to shut down, so that the next runner resumes it at the boundary.
- **`scheduler`** leads through the leadership port — a session-level advisory lock — and ticks
  while it leads; a second instance keeps trying and takes over when the leader's lead is
  gone, including when the leader was killed. The tick does nothing yet: time triggers arrive
  with governance (`0.2.0`). The election is real and proven first, so that nothing later
  depends on an election that was never tested.
- **`automation`** starts, says so, and waits: nothing publishes events yet (the outbox
  exists, nothing writes it). It is wired now so that the image and its configuration do not
  change when reactions arrive.
- **Shutdown** is the same for every role: on SIGTERM the HTTP surface stops, the runner claims
  nothing more, every running run is asked to stop at its next step boundary and the running
  worker step may finish up to `TAKTUS_SHUTDOWN_CEILING_SECONDS`, the claims are released, the
  process exits 0. A role still running at the ceiling is abandoned and its run recovered by
  the next runner from its last persisted boundary.
- **Tenants.** Until the identity component exists, an instance is told which tenants it serves
  (`TAKTUS_TENANTS`, default `default`); the runner claims for each in turn. An intake lands
  in the tenant the identity port places its sender in — with the provisional identity
  (`TAKTUS_PROVISIONAL_IDENTITY`, DEC-0013), the one configured tenant; with none configured,
  the first tenant, as a stated fallback.
