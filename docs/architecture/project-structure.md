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
| `governance` | autonomy levels, policies, anchors, budgets, limits, admission control; today: a tenant's anchors and which of them name a step's act (ADR-0042), whether a result has left the system (ADR-0022) |
| `decision` | decision requests, the decision register, rules derived from it; today: requests raised, answered, their reading confirmed, the register, the decider's list and response times (ADR-0042) |
| `catalog` | models, agents, skills, connectors, blueprints, maturity |
| `accounting` | consumption capture, Takt, forecasts, marginal value |
| `knowledge` | knowledge sources, embeddings, citations. Its package's first content is the guides beyond the repository (UC-13.6, ADR-0065): the manifest, the rendering by rule, the seven states a page in a knowledge system can be in, and the publishing through `knowledge.pages` |
| `value` | value ledger, cost and benefit entries, revert analysis |
| `ledger` | hash chain, verification, export |
| `reporting` | views and who may see them, reports and their delivery, the explanation of an action on request; owns no figure — every number is read from the component that produces it (ADR-0029). Its package arrived with the product finding (UC-6.12, ADR-0046); the owner-facing channel — a tenant's configuration and phrasebook, a report to the owner in three renderings, the answer in the channel read, reflected and confirmed — is in it too (ADR-0045), and so is the broken interface noticed from the run's failed calls (ADR-0047) |

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

The tree of `src/taktus` is printed, not kept here: `make tree` lists every package and module
with the first sentence of its docstring, and `tests/architecture` fails a module without one.
A tree kept by hand named every module on a few long lines, which two pull requests adding a
module each extended and conflicted on (#392). Below is the shape, which changes rarely.

```
taktus/
├── src/taktus/                      # the control plane; `make tree` prints every package and module with the sentence its docstring opens with
│   ├── shared/v1/                   # shared kernel binding — one frozen model per schema, checked by tests/contract
│   ├── components/                  # one package per component of §1, each of the same shape:
│   │   └── <component>/             #   domain/{model,service,event}/ · application/{service,query}/ · ports/
│   ├── ports/                       # cross-cutting ports: worker, connector, model (the three contracts), execution, persistence, ledger, …
│   ├── adapters/
│   │   ├── driving/                 # cli/ (taktusctl) · rest/ (the HTTP surface)
│   │   └── driven/                  # every technology and product, each behind a port (ADR-0003); memory/ for development and tests only
│   ├── wire/                        # wire formats (SSE) shared by conformance and driven adapters
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core
│   └── composition/                 # composition root: wires and runs `taktusd` and `taktusctl`
│
├── workers/                         # separate deployables behind the worker contract, each with its own image; none in the control plane image (DEC-0011)
│   ├── script/                      # the reference worker: shell commands, no AI
│   ├── claudecode/                  # the coding worker: a coding agent behind the contract, and the fake agent the gate runs it against
│   ├── codex/                       # the second coding worker: a second vendor's coding agent behind the contract, and its fake agent
│   └── mlbench/                     # the ML bench: trains, evaluates and serves classical models; embeddings next (#210)
│
├── contracts/                       # what third parties implement — JSON Schema
│   └── worker/v1/ connector/v1/ model/v1/ process/v1/ events/v1/ changes/v1/ shared/v1/
│
├── api/openapi.yaml                 # Taktus' OWN REST interface, generated from FastAPI by `make generate`, committed, held current by a test
├── migrations/                      # Alembic: alembic.ini, env.py, versions/ — explicit DDL, one head
├── deploy/{docker,k8s,backup}/   # docker/compose.yml: Taktus and PostgreSQL, `make up`; compose.reference-worker.yml: the worker layered in for development; compose.dev.yml: the development database; backup/: the image of the database backup job (ADR-0087)
├── blueprints/{dev-orchestration,it-operations,self-operation,finance}/   # README.md: the blueprints and the example domains; self-operation: what Taktus runs for itself — S-01 the removal test, weekly; finance: a description
├── examples/processes/              # process bundles that run as they are; each exercised by a test
├── web/                             # the web app: SvelteKit, TypeScript, a static build with the route after `#`, built into the image and served by the `api` role at {prefix}/app/; tests beside the code; `make gate-web` (ADR-0063)
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege; test_anchors.py: anchors at the step boundary and decision requests
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   ├── contract/                    # the Python bindings match the schemas and their examples
│   ├── components/ adapters/        # domain tables and application tests against fakes/; adapters/persistence and adapters/queue: one suite, both implementations; adapters/connectors: the reference connector against fakes/repository_service.py; adapters/rest: the surface under two prefixes; adapters/execution: the process adapter, and the container adapter checked from inside a job; adapters/telemetry: spans nested, the trace id on every entry, no person and no secret in an attribute
│   ├── composition/                 # the daemon's settings, and that no secret reaches a log line
│   ├── integration/                 # the whole slice against the reference worker — by endpoint, as a process started per job, as a container started per job; the restart test; two runners, two schedulers, time triggers fired once per slot on a clock the test sets, a real SIGTERM, the daemon under a prefix; the control plane image built and inspected
│   └── security/ resilience/
│
├── docs/{architecture,adr,usecases,vision,decisions,runs,research,roadmap.md}   # research: dated, sourced evidence a decision rests on
├── docs/guides/                     # guides.yaml declares the administration guide and the guide for users; the files beside it hold only the words no other document says (ADR-0065)
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
- **a product name in `components/**` or `ports/**`** (`claude`, `slack`, `github`, `jira`, `bookstack`,
  `ollama`, …) — the sharpest test in the project — and in `contracts/**`, where a connector is
  named by what it can do and never by what it is
- a direct import between two components
- a write by one component into another's data
- `workers/**` importing `src/taktus/**`
- a domain model that is not frozen and closed
- the core reading the clock, minting an identifier or drawing randomness by itself — only
  through `ports/clock.py`; `adapters/driven/clock/` is the one place that does
- the core importing anything but the standard library, pydantic and itself
- a cluster client anywhere but the cluster execution adapter: its own client
  (`execution/kubernetes/api.py`) imported from outside `execution/kubernetes/`, or a cluster
  client library imported anywhere

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
| Lanes | every tracked path belongs to a lane of CI (`tools/lanes.py`): a change runs the lanes it touches and the always-on checks, locally (`make verify`) and in CI by the same code; `tests/architecture` fails a path that only the always-on checks would read and that is not documentation (ADR-0096 §3) |
| Time, randomness, IDs | only through ports (`ports/clock.py`) — otherwise no run is reproducible; enforced by `tests/architecture` |
| Logging | `structlog`, structured, never personal data; every line written inside a span carries `trace_id`, the same identifier the engine writes into its ledger entries (`composition/logging.py`) |
| Secrets | never a bare `str` — `ports/configuration.py`'s `Secret` masks on `repr` and `str`; `reveal()` is the one way to the value, and the database URL is read as one. **A secret is read from a file, not from the environment:** `TAKTUS_<KEY>_FILE` holds the path, the file holds the value; the inline variable is accepted for a value that carries no secret (the development database) and refused together with the file. The daemon logs its effective configuration at start with every secret masked and its source named, and `tests/composition` proves that no secret value reaches a line. A setting an operator chose below what Taktus would choose itself — the uncalibrated margin below its floor — follows as a warning naming the value and the floor (DEC-0047) |
| Configuration | every setting is a `TAKTUS_*` variable, read through the configuration port and validated once at start (`composition/settings.py`); a wrong one is refused with one sentence naming the variable, never a stack trace. `.env.example` lists every variable, names only. A credential an assignment references is read at the moment a unit is started, under `credential.<name>` — `TAKTUS_CREDENTIAL_<NAME>_FILE`, or `TAKTUS_WORKER_<WORKER>_CREDENTIAL_<NAME>_FILE` for a worker named in `TAKTUS_WORKERS`, which reads no other (ADR-0078) |
| Execution | `TAKTUS_EXECUTION` chooses how a `worker` step's unit comes to exist: by endpoint, as a process, as a container, as a Job in a cluster (`docs/architecture/contracts.md` §2.4). `TAKTUS_WORKERS` names several workers in the order a step is resolved in, each with its own kind (ADR-0078). A launched unit reaches the hosts of the step's frame and the hosts its worker's own service needs, `TAKTUS_EXECUTION_SERVICE_HOSTS`, the operator's configuration and never a bundle's; a probe reaches none (ADR-0089). Every unit of a worker receives the variables its program needs to start, `TAKTUS_EXECUTION_UNIT_ENV` — visible configuration, never a secret, a name that carries one refused (ADR-0090). The `process` adapter is refused from autonomy level 3 upwards and when the level is unknown; the rule lives in `ports/execution.py` and `tests/governance` holds the adapter to it |
| Capacity | every threshold of the capacity report and of admission against the platform is a `TAKTUS_CAPACITY_*` setting with a default, never a constant in a function; a quantity a platform adapter cannot observe is `Unobserved` with the reason, never a guess; every execution unit carries a memory limit its adapter enforces, or the job is refused (`docs/architecture/platform.md`); a unit in a cluster requests its whole memory limit and a share of its CPU limit, `TAKTUS_EXECUTION_CPU_REQUEST_SHARE`, 0.25 by default (NTC-0190) |
| Telemetry | spans for the run, every step, every worker call and every connector call, nested; consumption and method as attributes; no person and no secret in an attribute (`tests/adapters/telemetry`); exported where `TAKTUS_OTLP_*` says, real either way |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Provenance | one record per completed step run (ADR-0021), built by `run/domain/service/provenance.py` and written by the engine in the transaction of the `step.finished` entry; the `ProvenanceStore` port is append-only like the `LedgerStore`, and the database refuses update and delete. A record references — identifiers, tokens, digests — and never copies. The worker's own version reaches the record through `Capabilities.version` and the pool's `ResolvedWorker` |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain. **Every repository call names its tenant** as an explicit parameter (ADR-0020); the adapter refuses another tenant than the open transaction's, and an aggregate that carries its tenant carries the one it is stored under. **Every call happens inside a unit of work** (`ports/persistence.py`, `UnitOfWork.transaction(tenant)`), opened by the application layer — a handler, the run engine — never by an adapter or the domain; a call outside one raises, blocks do not nest, and a store that raises inside a block spoils it. **An adapter stores documents, not classes:** it never imports a component (§3), so the composition root binds the aggregate class and the adapter maps `document()` to rows and back — one mapper per aggregate in `adapters/driven/postgres/_mapping.py`. **A foreign key never crosses a component boundary;** inside an aggregate, children hang off their parent and are replaced with it; a copy (the steps of a plan, of a run) is one JSON column, the source (the process version's steps) is rows. A step run's open block (ADR-0043) is one JSON column of `step_run`, like its estimate. The tables live in `_schema.py`, the history in `migrations/`, and `tests/adapters/persistence` fails on drift between them |
| Shared kernel binding | `src/taktus/shared/v1/` is hand-written and **machine-checked**, not generated: one frozen model per schema of `contracts/shared/v1`, one module per schema file, and `tests/contract` fails on any difference in properties, required fields, enumerations or patterns, and runs every example of the contract through the models. The same holds for the worker contract's shapes in `ports/worker.py`. Why not generation: the schemas carry conditional rules (`if`/`then` over a step's method, "at least one quantity") that no generator turns into a constructor check, and the components need exactly those checks in the constructor; generating the shape and hand-writing the rules would be two files per concept with the seam in the wrong place. A checked binding is one file, and drift is a red test |
| Generated code | `api/openapi.yaml` from the REST interface — never edited by hand; `make generate` is its one place, the file is committed so that the interface can be read without running anything, and `tests/adapters/rest/test_openapi.py` fails when it differs from what `make generate` writes |
| Types | `mypy --strict` across `src/` and the Python tools under `tools/` (`make lint`, NTC-0076); no `Any` without a comment saying why |
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
  runner was told to shut down, so that the next runner resumes it at the boundary. A claim
  takes at most the runner's free places, whatever plan the database chooses (NTC-0027). A job
  whose run had already ended when it was claimed — its runner died between the two writes —
  is completed and nothing executes (NTC-0026). Proven with two runner processes, one killed
  mid-step (`tests/integration/test_runner_failover.py`). The claim is also a fence: a runner
  cut off for longer than the lease loses it, and its next write to the run is refused in the
  write's own transaction, so two runners never both commit to one run
  (`tests/integration/test_runner_fence.py`, NTC-0044). A run halted because its worker was at
  capacity is *deferred*: its job is claimable again after a delay that starts at the poll
  interval and doubles up to a minute, and the deferral is not a failed attempt (ADR-0037,
  `tests/integration/test_capacity_wait.py`). A worker step's assignment is named in the ledger
  before it is posted; a runner that recovers the run asks the worker about it and adopts it
  instead of handing over another, and a runner that loses its claim leaves it running for the
  next (ADR-0038, `tests/integration/test_handover.py`).
- **`scheduler`** leads through the leadership port — a session-level advisory lock — and ticks
  while it leads; a second instance keeps trying and takes over when the leader's lead is
  gone, including when the leader was killed. While it leads, every tick fires the schedule
  triggers that are due (`composition/triggers.py`, ADR-0035): the process component answers
  which are due, and each due slot becomes a command on `channel.schedule`, a commissioned plan
  and a submitted run, which a runner executes. A slot starts its runs once — whoever leads,
  across a restart of the leader — because the run's identifier is derived from the trigger
  and the slot and the engine refuses a run that exists; slots missed while nobody led start
  one run (`tests/integration/test_time_triggers.py`). The tick also makes the capacity
  report; deadlines and budget windows arrive with governance.
- **`automation`** leads through the leadership port under its own name, as the scheduler does,
  and while it leads reacts to events (`composition/reactions.py`, ADR-0048). The intake writes
  the outbox entry `intake.accepted` in the transaction that keeps an event (`ports/outbox.py`);
  every pass reads the unpublished entries, asks the process component which active versions'
  event triggers match (`contracts/events/v1`), completes the intake into one command acting for
  the sender, and starts one run of each matching process. One delivery starts each process
  once — a redelivery changes nothing, the run's identifier is derived from the tenant, the
  process and the delivery, and the entry is published only after its runs exist — with two
  automation roles and across a stop of the leader (`tests/integration/test_event_reactions.py`).
  A trigger whose condition does not hold leaves its entry for a later pass.
  The same pass reads `intake.contribution`: an unknown sender's contribution on a channel
  `TAKTUS_TRIAGE` names starts that channel's triage process once, acting for whoever registered
  its active version, with no trigger matched (UC-1.9, ADR-0088).
- **The stream of changes** is the `api` role's (`composition/live.py`, ADR-0055). Each process
  holds at most `TAKTUS_LIVE_STREAMS` streams and one listening connection. A notification for a
  tenant with open streams wakes one read of its ledger, after the oldest position its streams
  hold; a tenant that heard nothing is read every 2 seconds anyway. Each stream receives the
  entries after its own position, filtered when they are sent by the reader's key as it is then.
  A reader that reconnects to another process resumes from its position. Proven with two `api`
  processes, with the notification and without it (`tests/integration/test_live_changes.py`).
- **Memory once started.** Once wired, the daemon collects and freezes what its start left
  alive — the modules, the wiring — so that a full garbage collection, which stops every thread
  of the process, no longer scans it: 2 000 runs read at once paused the event loop half as long
  (#360).
- **Shutdown** is the same for every role: on SIGTERM the HTTP surface stops, the runner claims
  nothing more, every running run is asked to stop at its next step boundary and the running
  worker step may finish up to `TAKTUS_SHUTDOWN_CEILING_SECONDS`, the claims are released, the
  process exits 0. A role still running at the ceiling is abandoned and its run recovered by
  the next runner from its last persisted boundary.
- **Tenants.** An instance is told which tenants it serves (`TAKTUS_TENANTS`, default
  `default`); the runner claims for each in turn. An intake lands in the tenant of the identity
  the sender's account is linked to, and nowhere when it is linked to none (ADR-0040); the
  first tenant is only where such a sender is answered from. Such a sender is answered only
  for what they wrote — an intake whose `intent.authored` is `false`, such as a label added, is
  answered nothing — and once per conversation within `TAKTUS_OFFER_WINDOW_SECONDS`, a day by
  default. The `api` role makes the offers of one conversation one at a time, and keeps when it
  made each in memory; the offer's key names the stretch of the window, so that another
  process finds an offer made in the same stretch (ADR-0040, amended).
- **The instance's own platform.** `TAKTUS_PLATFORM` names it and `TAKTUS_ADMINISTERS` declares,
  per credential, the platforms it administers (`ports/administration.py`, ADR-0052). The
  composition root reads both once and hands the one value to the process component's
  registration and to the run engine's admission; without a platform the daemon warns at start.
