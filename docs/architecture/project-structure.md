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
| `governance` | autonomy levels, policies, anchors, budgets, limits, admission control; today: a tenant's anchors and which of them name a step's act (ADR-0042), whether a result has left the system (ADR-0022), a tenant's introduction in stages and the ceiling each keeps (ADR-0137) |
| `decision` | decision requests, the decision register, rules derived from it: requests raised, answered, their reading confirmed, the register, the decider's list and response times (ADR-0042); rules from precedent proposed, adopted and answering their kind (`decision_rule`, ADR-0161), wired with the requests in `composition/decisions.py` |
| `catalog` | models, agents, skills, connectors, blueprints, maturity |
| `accounting` | consumption capture, Takt, forecasts, marginal value |
| `knowledge` | knowledge sources, embeddings, citations. Its package's first content is the guides beyond the repository (UC-13.6, ADR-0065): the manifest, the rendering by rule, the seven states a page in a knowledge system can be in, and the publishing through `knowledge.pages`. Then the knowledge layer (UC-5.5, ADR-0265): the rule `citation`, which lets an answer drawn from knowledge leave its step only with its sources, and the index `KnowledgeEntry` of references and digests of what was read, never the text |
| `value` | value ledger, cost and benefit entries, revert analysis |
| `ledger` | hash chain, verification, export |
| `reporting` | views and who may see them, reports and their delivery, the explanation of an action on request; owns no figure — every number is read from the component that produces it (ADR-0029). Its package arrived with the product finding (UC-6.12, ADR-0046), which leaves an instance by pseudonym, only where its operator enabled it, and only past the one rule for what may leave, which a report written by hand passes too (ADR-0112); the owner-facing channel — a tenant's configuration and phrasebook, a report to the owner in three renderings, the answer in the channel or on the report's page in the web app read, reflected and confirmed — is in it too (ADR-0045, ADR-0120), and so is the broken interface noticed from the run's failed calls (ADR-0047), and what needs a person's action — a capacity crossing to *act*, a lost claim, a failed or missing backup — noticed from recorded facts (ADR-0106), and the signals judged against their corridors, with the daily report of what deviates (ADR-0109) |

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
│   ├── wire/                        # wire formats: SSE for conformance and adapters; BPMN for process
│   ├── conformance/                 # the contract suite — a client of adapters, no part of the core
│   └── composition/                 # composition root: wires and runs `taktusd` and `taktusctl`
│
├── workers/                         # separate deployables behind the worker contract, each with its own image; none in the control plane image (DEC-0011)
├── connectors/                      # the connectors behind the connector contract, package `taktus_connectors`: each an image of its own, a stage of connectors/Dockerfile; none in the control plane image, none importing it (ADR-0158)
│   ├── a2a/                         # an agent of the agent-to-agent protocol behind the contract, the binding of ADR-0172; it ships no capability of its own, its operator names one (composition/shipped.json)
│   ├── script/                      # the reference worker: shell commands, no AI
│   ├── claudecode/                  # the coding worker: a coding agent behind the contract, and the fake agent the gate runs it against
│   ├── codex/                       # the second coding worker: a second vendor's coding agent behind the contract, and its fake agent
│   ├── factory/                     # a software factory behind the contract, generic over its task API through a profile (ADR-0157); its release entry is in composition/shipped.json
│   └── mlbench/                     # the ML bench: trains, evaluates and serves classical models; embeddings next (#210)
│
├── contracts/                       # what third parties implement — JSON Schema
│   └── worker/v1/ connector/v1/ model/v1/ process/v1/ events/v1/ changes/v1/ shared/v1/
│
├── api/openapi.yaml                 # Taktus' OWN REST interface, generated from FastAPI by `make generate`, committed, held current by a test
├── migrations/                      # Alembic: alembic.ini, env.py, versions/ — explicit DDL, one head
├── deploy/{docker,k8s,backup,docs}/   # docker/compose.yml: Taktus and PostgreSQL, `make up`; compose.reference-worker.yml: the worker layered in for development; compose.dev.yml: the development database; backup/: the image of the database backup job (ADR-0087); docs/: how the documentation site is uploaded to web hosting (DEC-0234)
├── blueprints/{dev-orchestration,it-operations,self-operation,finance}/   # README.md: the blueprints and the example domains; self-operation: what Taktus runs for itself — S-01 the removal test, weekly; finance: a description
├── examples/processes/              # process bundles that run as they are; each exercised by a test
├── scaffolds/skills/                # the method scaffolds the catalogue ships: development, process automation, analysis — curated skills with a scaffold.yaml (ADR-0307)
├── web/                             # the web app: SvelteKit, TypeScript, a static build with the route after `#`, built into the image and served by the `api` role at {prefix}/app/; every link a channel carries to a report opens its page there (ADR-0120); tests beside the code; `make gate-web` (ADR-0063)
│
├── tests/
│   ├── architecture/                # adapter obligation, component boundaries, no product names
│   ├── conformance/                 # the contract suite, runnable against foreign adapters
│   ├── governance/                  # anchors hold, limits never breach, least privilege; test_anchors.py: anchors at the step boundary and decision requests; test_corrections.py: decisions on proposals counted, a level that falls by rule before the next step (ADR-0110)
│   ├── exactness/                   # `exact` steps never take their final value from AI
│   ├── contract/                    # the Python bindings match the schemas and their examples
│   ├── components/ adapters/        # domain tables and application tests against fakes/; adapters/persistence and adapters/queue: one suite, both implementations; adapters/connectors: the reference connector against fakes/repository_service.py, every other connector against a fake of its service; adapters/rest: the surface under two prefixes; adapters/execution: the process adapter, and the container adapter checked from inside a job; adapters/telemetry: spans nested, the trace id on every entry, no person and no secret in an attribute
│   ├── composition/                 # the daemon's settings, and that no secret reaches a log line
│   ├── integration/                 # the whole slice against the reference worker — by endpoint, as a process started per job, as a container started per job; the restart test; two runners, two schedulers, time triggers fired once per slot on a clock the test sets, a real SIGTERM, the daemon under a prefix; the control plane image built and inspected
│   └── security/ resilience/
│
├── docs/{architecture,adr,usecases,vision,decisions,runs,research,roadmap.md}   # research: dated, sourced evidence a decision rests on
├── docs/guides/                     # guides.yaml declares the guides for administrators, users and developers; the files beside it hold only the words no other document says (ADR-0065)
├── docs-site/                       # the documentation site's configuration and start page: `make docs-site` builds the guides into static files under build/docs-site/, which git ignores (DEC-0234, NTC-0272)
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
taktus_connectors    → nothing of taktus                 — and src/taktus never imports it (ADR-0158)
components.X         → components.X, ports, shared, wire
ports                → shared
shared               → nothing
```

A driving adapter calls application services and never builds them: the composition root
implements what the adapter declares it needs (`adapters/driving/cli/wiring.py`,
`adapters/driving/rest/wiring.py`) and starts it. That is why the console script `taktusctl`
begins in `composition/taktusctl.py` and `taktusd` in `composition/daemon.py` — the one place
that constructs an adapter and binds it to a port; anything else that did would be a finding.
A command that only reads a file and writes one, such as `taktusctl prices import`, needs no
wiring: it calls a pure function of the component and touches no port.

`wire` holds what two readers of one wire format share — today the Server-Sent Events reader,
used by the conformance suite and by the HTTP worker adapter. Neither may import the other, so
what they share lives in a package that imports nothing from either and no technology.
It also holds BPMN 2.0 (`wire/bpmn.py`, ADR-0168): an open standard's XML read, defused, into a
neutral graph and written from one. The process component gives the graph its meaning — a plan
draft in, a projection of a version out — and `taktusctl bpmn` (a driving adapter) calls it as a
pure function, needing no wiring, as `taktusctl prices import` does.

`conformance` is the executable reading of a contract, run against a live adapter. It is a
client, as a foreign control plane would be, and therefore imports nothing from the control
plane; `taktusctl conformance` (a driving adapter) is its entry point, and `tests/conformance` its
gate. It ships in the wheel together with `contracts/`, so that a third party can run it without
the rest of Taktus. It speaks HTTP and SSE to a worker and MCP to a connector; the reference
connector is a driven adapter and the suite its client, and neither imports the other.

`connectors/` holds every connector served as an MCP server, the package `taktus_connectors`
(ADR-0158). It is a separate deployable, as a worker is: each connector is an image of its own,
a stage of `connectors/Dockerfile`, and the control plane image copies nothing of it. The
control plane keeps its side of the port under `adapters/driven/connectors/` — the MCP client,
the pool, and the loopback and directory connectors, which reach the instance itself and run in
its process. A connector that reaches a cloud's API signs with its own copy of the key exchange
(`auth.py` in its directory), because an image holds nothing of another connector; the release's
list (`composition/shipped.json`, `make generate`) names each one with what it declares, the
books connector's `accounting.invoices` among them (ADR-0314).

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
| Lanes | every tracked path belongs to a lane of CI (`tools/lanes.py`): a change runs the lanes it touches and the always-on checks, locally (`make verify`) and in CI by the same code; `tests/architecture` fails a path that only the always-on checks would read and that is not documentation (ADR-0096 §3); the lane `rehearse` replays the self-development bundles from their recordings (`make rehearse`, ADR-0108), selected by a bundle, a recording, the export tool, a migration or any module under `src/`, which the replay reaches through the composition root |
| Time, randomness, IDs | only through ports (`ports/clock.py`) — otherwise no run is reproducible; enforced by `tests/architecture` |
| Logging | `structlog`, structured, never personal data; every line written inside a span carries `trace_id`, the same identifier the engine writes into its ledger entries (`composition/logging.py`) |
| Secrets | never a bare `str` — `ports/configuration.py`'s `Secret` masks on `repr` and `str`; `reveal()` is the one way to the value, and the database URL is read as one. **A secret is read from a file, not from the environment:** `TAKTUS_<KEY>_FILE` holds the path, the file holds the value; the inline variable is accepted for a value that carries no secret (the development database) and refused together with the file. The daemon logs its effective configuration at start with every secret masked and its source named, and `tests/composition` proves that no secret value reaches a line. A setting an operator chose below what Taktus would choose itself — the uncalibrated margin below its floor — follows as a warning naming the value and the floor (DEC-0047) |
| Configuration | every setting is a `TAKTUS_*` variable, read through the configuration port and validated once at start (`composition/settings.py`); a wrong one is refused with one sentence naming the variable, never a stack trace. `.env.example` lists every variable, names only. A credential an assignment references is read at the moment a unit is started, under `credential.<name>` — `TAKTUS_CREDENTIAL_<NAME>_FILE`, or `TAKTUS_WORKER_<WORKER>_CREDENTIAL_<NAME>_FILE` for a worker named in `TAKTUS_WORKERS`, which reads no other (ADR-0078) |
| Execution | `TAKTUS_EXECUTION` chooses how a `worker` step's unit comes to exist: by endpoint, as a process, as a container, as a Job in a cluster (`docs/architecture/contracts.md` §2.4). `TAKTUS_WORKERS` names several workers in the order a step is resolved in, each with its own kind (ADR-0078). A launched unit reaches the hosts of the step's frame and the hosts its worker's own service needs, `TAKTUS_EXECUTION_SERVICE_HOSTS`, the operator's configuration and never a bundle's; a probe reaches none (ADR-0089). Units reach their hosts through the instance's one egress gateway, by a token per job that names them, and a launched worker is estimated by the estimator it declares, so that no unit starts before admission (ADR-0115). Every unit of a worker receives the variables its program needs to start, `TAKTUS_EXECUTION_UNIT_ENV` — visible configuration, never a secret, a name that carries one refused (ADR-0090). The `process` adapter is refused from autonomy level 3 upwards and when the level is unknown; the rule lives in `ports/execution.py` and `tests/governance` holds the adapter to it |
| Capacity | every threshold of the capacity report and of admission against the platform is a `TAKTUS_CAPACITY_*` setting with a default, never a constant in a function; a quantity a platform adapter cannot observe is `Unobserved` with the reason, never a guess; every execution unit carries a memory limit its adapter enforces, or the job is refused (`docs/architecture/platform.md`); a unit in a cluster requests its whole memory limit and a share of its CPU limit, `TAKTUS_EXECUTION_CPU_REQUEST_SHARE`, 0.25 by default (NTC-0190) |
| Telemetry | spans for the run, every step, every worker call and every connector call, nested; consumption and method as attributes; no person and no secret in an attribute (`tests/adapters/telemetry`); exported where `TAKTUS_OTLP_*` says, real either way |
| Every step | carries method, reason, rejected alternatives, fallback; an exactness class if it produces a result (ADR-0018) |
| Provenance | one record per completed step run (ADR-0021), built by `run/domain/service/provenance.py` and written by the engine in the transaction of the `step.finished` entry; the `ProvenanceStore` port is append-only like the `LedgerStore`, and the database refuses update and delete. A record references — identifiers, tokens, digests — and never copies. The worker's own version reaches the record through `Capabilities.version` and the pool's `ResolvedWorker` |
| Artifact bytes | the object store port (`ports/objectstore.py`) has two adapters, chosen by `TAKTUS_OBJECT_STORE` in `composition/objects.py` (ADR-0165): `filesystem`, the default, files `<TAKTUS_STATE_DIR>/objects/<hex>` (`adapters/driven/memory/object_store.py`), and `s3`, keys `<prefix>/<hex>` in a bucket of an S3-compatible store, signed by signature version 4 on the HTTP client the control plane already has (`adapters/driven/s3/`). Both keep a bounded cache in memory; bytes that do not hash to their name read as absent; a store that cannot answer raises `ObjectStoreUnavailable`, never `None`. An erasure removes an object by its digest (`remove`, ADR-0176): a file deleted, or a `DELETE` of the key after a `HEAD` that says whether it was there. One suite, `tests/adapters/objectstore/`, runs against both and memory alone |
| Persistence | SQLAlchemy Core in the driven adapter only; no ORM object crosses into the domain. **Every repository call names its tenant** as an explicit parameter (ADR-0020); the adapter refuses another tenant than the open transaction's, and an aggregate that carries its tenant carries the one it is stored under. **Every call happens inside a unit of work** (`ports/persistence.py`, `UnitOfWork.transaction(tenant)`), opened by the application layer — a handler, the run engine — never by an adapter or the domain; a call outside one raises, blocks do not nest, and a store that raises inside a block spoils it. **An adapter stores documents, not classes:** it never imports a component (§3), so the composition root binds the aggregate class and the adapter maps `document()` to rows and back — one mapper per aggregate in `adapters/driven/postgres/_mapping.py`. **A foreign key never crosses a component boundary;** inside an aggregate, children hang off their parent and are replaced with it — a run's step runs, checkpoints and artifacts row by row, only those that changed (#325); a copy (the steps of a plan, of a run) is one JSON column, the source (the process version's steps) is rows. A step run's open block (ADR-0043) is one JSON column of `step_run`, like its estimate. The tables live in `_schema.py`, the history in `migrations/`, and `tests/adapters/persistence` fails on drift between them. **An advisory lock is taken in the two-key form:** a namespace per purpose (`_locks.py`) and a key within it, for a tenant's ledger its registry row's unique `lock_key`, never a hash of its id (#317), for a run's chain the hash of tenant and run; a writing transaction's marker of the stable head is the one negative one-key lock (ADR-0164). `ledger_entry` is partitioned by month of `ts`; `_schema.py` names the partitioned table, migration 0091 and `ledger_partitions()` the partitions |
| Shared kernel binding | `src/taktus/shared/v1/` is hand-written and **machine-checked**, not generated: one frozen model per schema of `contracts/shared/v1`, one module per schema file, and `tests/contract` fails on any difference in properties, required fields, enumerations or patterns, and runs every example of the contract through the models. The same holds for the worker contract's shapes in `ports/worker.py`. Why not generation: the schemas carry conditional rules (`if`/`then` over a step's method, "at least one quantity") that no generator turns into a constructor check, and the components need exactly those checks in the constructor; generating the shape and hand-writing the rules would be two files per concept with the seam in the wrong place. A checked binding is one file, and drift is a red test |
| Generated code | `api/openapi.yaml` from the REST interface — never edited by hand; `make generate` is its one place, the file is committed so that the interface can be read without running anything, and `tests/adapters/rest/test_openapi.py` fails when it differs from what `make generate` writes |
| Types | `mypy --strict` across `src/` and the Python tools under `tools/` (`make lint`, NTC-0076); no `Any` without a comment saying why |
| Tests | domain = table tests, no mocks; application = fakes of the ports (`tests/fakes/`); driven adapters = testcontainers. **One suite per port, run against every implementation** (`tests/adapters/persistence`: the memory adapter and PostgreSQL answer the same assertions; a disagreement is a finding about the port, and the port gains the rule) |
| Ledger facts | what a component tells the ledger is a `Fact` (`ports/ledger.py`): identifiers, method, adapter, measured consumption, an outcome *token*, a content digest — never text. A reason stays on the run; the ledger is content-free by construction |
| Ledger reads | a read costs what it returns (ADR-0105): `Ledger.entries(tenant, run_id)` reads one run's entries through `ledger_entry_run`, `Ledger.of_kinds` the entries of some kinds through `ledger_entry_kind`, and with `since=` through `ledger_entry_kind_ts`, `Ledger.of_runs` the entries of some kinds of some runs (#522). The correction figures are a projection and the alert sweep reads the capacity and claim kinds (#550). A value over the whole history is a `Projection` (`ports/ledger.py`), folded entry by entry, kept by the `ProjectionStore` port (`ports/persistence.py`; `ledger_projection` in the database, the transaction's journal in memory and never in a snapshot) with the last sequence number it read, and rebuilt from the ledger by `Ledger.rebuilt`. `ChainedLedger` takes the projection store as its third argument; without one it folds from the first entry every time, and verifies the whole chain. `Ledger.verify` walks from the last verified checkpoint; `verify(full=True)` and `taktusctl ledger verify --full` from the first entry. A run's entries form its own chain, anchored in the tenant's by `Ledger.anchor`, which the scheduler calls once a minute (`composition/anchors.py`); `LedgerStore.head` is the stable head, and a reader that keeps its place passes it to `after` as `through`; `composition/live.py` reads it in a transaction of its own before its snapshot (ADR-0164) |
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
  all. A daemon refuses to start against a schema that does not match the binary. A daemon
  that cannot bind its HTTP port winds down the roles it started and exits as not operable,
  saying why; the server's own exit no longer ends the process past them (#520).
- **`runner`** is the run component's `Runner` over the queue port: it claims due jobs for the
  tenants it serves, one transaction per claim, executes each through the engine's `resume`
  (which starts a submitted run, continues a halted one, or recovers one whose runner died),
  and renews the claim's lease from a heartbeat. Several runners share one database and never
  claim the same run; a runner that dies leaves its run for at most one lease. A run ends the
  job — completed when finished, halted by admission control or escalated; released when this
  runner was told to shut down, so that the next runner resumes it at the boundary. A claim
  takes at most the runner's free places, whatever plan the database chooses (NTC-0027). The places go one job per tenant in turn, and each round starts one tenant further on, so a tenant with much queued work holds back no other; a run that ends wakes the runner, which claims again at once (#319).
  Inside a tenant the claim shares the places between organisational units — the department a
  run's command named: a unit that holds fewer places comes first, and a tenant may limit a
  unit's concurrent runs, which the runner hands the claim, and its money committed per month,
  which the engine holds before a run's first step (`taktusctl units`, `ports/org_units.py`,
  `composition/org_units.py`, ADR-0166). A job
  whose run had already ended when it was claimed — its runner died between the two writes —
  is completed and nothing executes (NTC-0026). Proven with two runner processes, one killed
  mid-step (`tests/integration/test_runner_failover.py`). The claim is also a fence: a runner
  cut off for longer than the lease loses it, and its next write to the run is refused in the
  write's own transaction, so two runners never both commit to one run
  (`tests/integration/test_runner_fence.py`, NTC-0044). A run halted because its worker was at
  capacity is *deferred*: its job is claimable again after a delay that starts at the poll
  interval and doubles up to a minute, and the deferral is not a failed attempt (ADR-0037,
  `tests/integration/test_capacity_wait.py`). A `wait` step longer than the poll interval
  parks its run: the run halts with cause `parked`, and its job is deferred to the wait's next
  check, so a wait for time or for an outside system holds no place (ADR-0103). A wait for an outside state reads a `not_found` answer of its read as a state not reached yet and checks again (ADR-0103 §6). A worker step's assignment is named in the ledger
  before it is posted; a runner that recovers the run asks the worker about it and adopts it
  instead of handing over another, and a runner that loses its claim leaves it running for the
  next (ADR-0038, `tests/integration/test_handover.py`). A run is recovered only when its
  runner died. A step whose worker cannot be reached ends failed with that cause, and the run
  escalates. An exception out of the engine releases the job, and the next claim recovers the
  run, so a cause that raises again is recovered again (#589). At the job's last attempt, a
  step that raises fails with what it raised, and the run escalates naming the step and the
  exception; the runner reads the queue's limit of attempts from the queue it is wired with
  (#591). Every job's outcome goes to the log through `roles.said`. A run that did not finish
  is logged with the step it ended at, its cause and its reason. An exception is logged with
  the step it was raised in.
  The runner itself keeps only its latest outcomes, a thousand by default, and counts all of
  them, so that a runner that runs for weeks holds no more for them than one that ran an hour
  (#592).
- **`scheduler`** leads through the leadership port — a session-level advisory lock — and ticks
  while it leads; a second instance keeps trying and takes over when the leader's lead is
  gone, including when the leader was killed. While it leads, every tick fires the schedule
  triggers that are due (`composition/triggers.py`, ADR-0035): the process component answers
  which are due, and each due slot becomes a command on `channel.schedule`, a commissioned plan
  and a submitted run, which a runner executes. A slot starts its runs once — whoever leads,
  across a restart of the leader — because the run's identifier is derived from the trigger
  and the slot and the engine refuses a run that exists; slots missed while nobody led start
  one run (`tests/integration/test_time_triggers.py`). An `each` that says `once` derives the
  identifier from the trigger and the item alone, so an item listed again by a later slot —
  a document still in an inbox — starts no second run; its read takes the trigger's fixed
  `arguments` (ADR-0188). The release's list of what it ships (`composition/shipped.json`)
  names the operations every connector declares, the logs, secret metadata, signing
  credentials and model catalogue of ADR-0202 to ADR-0204 among them, generated from the
  connectors' declarations (`make generate`), so that a new connector reaches it without a hand
  edit. The tick also makes the capacity
  report, and once a minute it watches that every expected run happened: one that did not
  raises an incident (`composition/expected_runs.py`, ADR-0107,
  `tests/integration/test_expected_runs.py`), and judges every signal against its corridor,
  raising the daily report from 06:00 UTC (`composition/signals.py`, ADR-0109). Every ten
  minutes it sends each tenant's product findings where the operator enabled it, and records a
  change of that setting in the tenant's ledger either way (`composition/findings.py`,
  ADR-0046, ADR-0112); `taktusctl findings` shows them, and `taktusctl findings report` sends a
  report written by hand once it is checked, shown and confirmed. It reports
  to the owner what needs a person's action, a level that fell by rule and a raise Taktus
  proposes among it (`composition/alerts.py`, ADR-0106, ADR-0110). The run reaches the
  governance component's `Corrections` through `composition/decisions.py`, and `taktusctl
  corrections` reads and configures it; the same port reads the classes of request a version's
  statement names from the process component (ADR-0215). It reaches the tenant's anchors, and the ceilings its
  risk classes set on a level, the same way, and `taktusctl anchors set` stores both in one
  document, the column `anchor_configuration.levels` holding the ceilings (ADR-0170). It reaches the tenant's residency rule,
  `TenantResidency`, the same way, and `taktusctl residency` shows and sets it, narrowed per
  data class and per process; the run asks it with the run's process (ADR-0258). Registration
  reaches it through `ResidencyBindings`, which `composition/residency.py` answers from the
  pools and the declared host locations (ADR-0281). The run and
  registration reach the tenant's declaration of its sources, `TenantSources`, the same way,
  and `taktusctl sources` shows and changes it (ADR-0130). Registration reaches the roles the tenant's
  identities hold, `RoleStructure`, from the identity component's `IdentityDirectory`
  directly, and the process level reads a step's role from the version (ADR-0146). It reaches the
  rights of a process, `ProcessRights`, from the same directory (ADR-0257). The governance
  component's `TenantDomains` answers registration's `DomainOwners` and reads the takeover and
  removal tests through `composition/domains.py`, and `AnchorsInForce` reads the domains to scope
  the anchors (ADR-0259). Its `TenantBudgets` answers the run's `TenantBudget` through
  `BudgetOfTheRun` in `composition/decisions.py`, and `taktusctl budget` sets it (ADR-0260).
  Its `UnitLimits` answers the run's `UnitLimitsPort` through `UnitLimitsOfTheRun` in
  `composition/unit_limits.py`, which reads where an identity sits from the identity component's
  `IdentityDirectory`; `taktusctl units limit` sets the limits (ADR-0282), with the policy
  `halt`, `wait` or `cheaper` at the line (ADR-0298). The composition hands the engine the
  `Claims` of its persistence (`ports/persistence.py`; `MemoryClaims`, `PostgresClaims`): the
  admission of a step against a unit limit is checked again under the limit's claim before it
  commits, so two runners never both fit one line (ADR-0298). `RunEngine.demand` estimates a
  run before it starts; `taktusctl run` and `submit` show it and start a run that needs much
  only with `--accept-demand` (ADR-0299). The open `limit.harmful` reports are the figure
  `limit.held_seconds` that `composition/figures.py` hands to the views (ADR-0299).
  The accounting component's `BottlenecksHandler` reads its three ports through
  `composition/bottlenecks.py`: `RunAccounts` over the run's `BlockedTime`, which hands over the
  limits and the work held back and the waits on people only grouped; `MethodsOfTheRun` over the
  step measures; `RulesOfTheDecisions` over the decision component's rules. The run's
  `Departments` is answered there from the identity directory, and `taktusctl bottlenecks`
  prints the analysis (ADR-0283).
  `composition/acting.py`'s `ActingReads` gathers what acts for a tenant, what depends on it and
  how a process really runs from the catalog's maturity records, the pools, the process
  versions, the residency rule, the stops, the blocks, the provenance store and the identities'
  roles, and hands them to the reporting component's `acting` and `variants` views, which store
  nothing; the HTTP surface serves them in `rest/acting.py` (ADR-0147). The run reaches the tenant's rules
  for outward messages and the cases a person answered in, `TenantMessages`, through
  `MessagesOfTheRun`; `taktusctl messages` shows and sets the rules, and `taktusctl case
  answered` records an answer (ADR-0142). The run reaches a version's caps on
  open work in the process component through `CapsOfTheVersion`, and the tenant's limits on
  repetition with the incident a stop raises through `RepetitionOfTheRun` over the governance
  component's `Repetitions`, both in `composition/decisions.py`; `taktusctl incident configure`
  sets the limits (ADR-0132). The run keeps the tenant's stops of adapters in its own `Stops`,
  which the engine reads before every handover to a worker, every connector call and every
  question to a model, and the runner at every renewal; the
  scheduler confirms them in `composition/stops.py`, and `taktusctl stop` requests, shows and
  lifts them (ADR-0138). The same `Stops` keep the stops of a process and of a tenant, in
  `scoped_stop`; the engine reads them before it hands any step on, and `taktusctl stop
  process`, `tenant` and `global` request them. The governance component's `ResultDefects`
  stops a process where its rule decides `stop`, through `RuleStops` in `composition/stops.py`
  (ADR-0256). The run reaches a version's deadlines in the process component
  through `DeadlinesOfTheVersion`, in the same module, and its `DeadlineKeeper` keeps them;
  the scheduler takes their actions in `composition/deadlines.py`, which starts a process
  through the command component as a trigger does, and `taktusctl deadline` lists them and sets
  the tenant's working time (ADR-0133). The run keeps every event a worker reports as a line of
  its step's trace through `ports/traces.py`, masked by the composition root's `KnownSecrets`;
  the reporting component's `StepTraces` reads the trace beside the run level, shares it by role
  and keeps the tenant's retention, which `taktusctl trace retention` sets, and the scheduler
  erases what it ended in `composition/traces.py` (ADR-0135). The governance component's
  `SubjectRequests` prepares, carries out and withdraws a data-protection request; its port
  `SubjectHoldings` is answered by `composition/subjects.py`'s `RunHoldings`, which finds a
  subject through `ProvenanceStore.of_subject` and the runs' intake, erases a run's content
  through `ObjectStore.remove` and `Traces.erase_run`, and verifies the ledger and the run's
  provenance after it. `ProcessingEvidence` there hands the register's facts, the tenant's
  declarations and the ledger's `subject.*` entries to the reporting component's `evidence`,
  which draws the document; `taktusctl subject` and `taktusctl evidence` reach both
  (ADR-0176). The stage view of a run for a
  participant (UC-6.15) is `domain/service/stages.py`, computed from the run level's facts on
  each request, served at `GET /levels/runs/{run}/stages`, and stores nothing. The governance component's
  `Stages` keeps a tenant's introduction in stages; `composition/stages.py` answers its ports —
  the level a process runs at now, its takeover instructions, the identities and the
  owner-facing channel — and registration's `StageCeilings`, and the scheduler looks at every
  tenant's stages once an hour. `taktusctl stage` declares, shows and opens them, and the
  table `stage_plan` keeps each plan (ADR-0137). `adapters/driving/rest/stages.py` serves the
  same view and the opening at `GET /stages` and `POST /stages/{stage}/open`, for the plan's
  responsible role, through `RestServices.stages` (ADR-0191).
  While it leads it also looks at every process's evaluation cases
  once a minute (`composition/evaluations.py`, ADR-0134): `Evaluations` starts a drift
  evaluation at every slot of a version's evaluation schedule, moves every evaluation on — its
  case runs, then its judges' runs, then its score — and proposes a case for every corrected
  draft. A drift of a process that sends outward reaches the governance component's `Drifts`
  as an incident. `ProposalActs` (`composition/proposals.py`) starts a proposal's evaluation
  beside its rehearsal and holds commissioning to its verdict; the HTTP surface reads the
  evaluations and confirms the cases (`adapters/driving/rest/evaluations.py`), a proposal's view
  carries its evaluation case by case (`adapters/driving/rest/proposals.py`), and `taktusctl
  incident configure` sets the tenant's tolerance. `ChangeInChannel`
  (`composition/change_in_channel.py`) reads a commissioning back with that verdict, in the
  sentences of the shipped phrasebooks (`composition/phrasebooks/`). Maturation reads a step's
  score on the cases through the run's port `ports/scores.py`, which `RepositoryScores`
  (`composition/maturation.py`) answers for the daemon and for `taktusctl` (`composition/local.py`);
  `taktusctl maturation moves` shows both scores (ADR-0141). `Evaluations.start_guided` runs the same
  version on its cases under two kinds of know-how, a skill version pinned or a shared agent's
  profile under a new core. The same leader looks at every tenant's skills once a minute
  (`composition/skills.py`, ADR-0162): `SkillLifecycle` drafts a skill from corrections that
  recurred, scores its rounds, approves it by rule at level 4 once n rounds passed, puts it into
  production and falls it back by rule; `CatalogGuidance` answers the run's `Guidance` port,
  and the postgres adapter keeps the tables `skill_version`, `skill_ownership`, `skill_policy`,
  `agent_core` and `role_profile` (ADR-0163). A skill that carries a `scaffold.yaml` is a
  method scaffold and is registered with the origin `curated` (ADR-0307); `taktusctl bundle
  check` reads the declaration through `scaffold_of` (`adapters/driving/cli/bundle_command.py`),
  and never as a bundle. `InstanceScaffolds` (`composition/scaffolds.py`) reads a scaffold at
  its version in production, or a check at its newest readable one, and resolves the repository
  and the knowledge system by capability for the catalogue's `ScaffoldProjects`, which checks a
  project against it and furnishes the missing artifacts. `shipped.json` lists
  `repository.files.dates`. The models
  configured in `TAKTUS_MODELS` reach the run as one pool in chain order
  (`composition/execution.py`, `composition/settings.py`, ADR-0116), and each is held to the
  model contract's suite with its own endpoint (`composition/conformance.py`); deadlines and
  budget windows arrive with governance.
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
  its active version, with no trigger matched (UC-1.9, ADR-0088). It reads `intake.assistant`
  too: a placed person's message in a rollout channel `TAKTUS_ROLLOUT` names runs the agent's
  own process as that person (`composition/assistants.py`, UC-12.1, ADR-0261).
- **The stream of changes** is the `api` role's (`composition/live.py`, ADR-0055). Each process
  holds at most `TAKTUS_LIVE_STREAMS` streams and one listening connection. A notification for a
  tenant with open streams wakes one read of its ledger, after the oldest position its streams
  hold; a tenant that heard nothing is read every 2 seconds anyway. Each stream receives the
  entries after its own position, filtered when they are sent by the reader's key as it is then.
  A reader that reconnects to another process resumes from its position. Proven with two `api`
  processes, with the notification and without it (`tests/integration/test_live_changes.py`).
- **What keeps the operation running** is read on the HTTP surface
  (`adapters/driving/rest/operation.py`, ADR-0121) through the port `OperationReads` of
  `adapters/driving/rest/wiring.py`. `composition/operation.py` implements it over the
  governance component's incidents, which `composition/expected_runs.py` hands over, and the
  reporting component's alerts, backup and signals. The surface reads; nothing there decides.
- **The web app's sign-in** is the `api` role's (`adapters/driving/rest/session.py`,
  ADR-0119). `POST /session` exchanges the account key once for a session cookie, and
  `DELETE /session` ends it. The middleware `SessionCookies` hands the cookie to every route as
  the request's credential, the stream of changes included, and refuses a write with it from
  another site. The identity component keeps the session (`BrowserSession`, table
  `browser_session`) under a digest of its token. The composition root binds its repository and
  its lifetime, `TAKTUS_SESSION_HOURS`, in every composition (`daemon.py`, `local.py`,
  `replay.py`; `settings.py`).
- **The MCP surface** is the `api` role's too (`adapters/driving/rest/agent_surface.py`,
  ADR-0131), mounted at `<prefix>/mcp`. Each request is authenticated by its agent key and
  answered by a server built for that person and the rights of their roles; the MCP library is
  imported there only. Starting a process crosses the process, command and run components, so
  it is the port `AgentActs` of `adapters/driving/rest/wiring.py`, implemented in
  `composition/agent_surface.py`, which also records every call. The identity component keeps
  the agent key's digest on the identity and the rights per role (`RoleRights`, table
  `role_rights`).
- **A message to a running step** is the `api` role's (`adapters/driving/rest/steering.py`, the
  MCP tool `steer_step` under the right `agent.steer`, and the chat's read-back in
  `composition/takeover_in_channel.py` with the phrasebooks' `steer_*` entries; ADR-0156). Each
  hands the run engine `SteerStep` through the port `Takeovers` of
  `adapters/driving/rest/wiring.py`. The engine places the message on the run's job
  (`ports/queue.py`, `ask_message`), and the runner holding it hands it to the worker with each
  renewal of its lease.
- **A worker that connects outbound** is hosted by the `api` role
  (`adapters/driving/rest/relay.py`, ADR-0156) at `<prefix>/workers/<name>/relay`, admitted by
  its connect key. Its requests in flight live in the relay every instance shares
  (`ports/relay.py`; `adapters/driven/postgres/relay.py`, migration 0087), and every runner
  reaches it through `adapters/driven/workers/connected.py`. `composition/execution.py` opens a
  worker of kind `connected` over the relay, `composition/daemon.py` builds the host from the
  connect keys `composition/settings.py` reads, `composition/pools.py` names the binding in its
  configuration, and `composition/conformance.py` runs the instance's suite over it;
  `composition/local.py` uses the database's relay, so that `taktusctl` against an instance's
  database opens its services and runs a connected worker's suite over the binding as the
  daemon does (#672), and takes another one in tests.
- **A decision that takes effect** on the HTTP surface (`adapters/driving/rest/app.py`) or in
  the owner's channel (`composition/owner_channel.py`) is handed to the run engine, which
  continues or halts the run it holds, and to `composition/moves.py` with its request. A
  request that accepted a proposal to move a step to a trained model registers the moved
  version; one that accepted a proposal to roll a move back registers the replaced version again
  (ADR-0114, on DEC-0164's answer as UC-4.24 states it). A move that cannot be applied is logged, and `taktusctl maturation apply`
  (`adapters/driving/cli/maturation_command.py`) applies it once the cause is gone; `taktusctl
  maturation moves` and `rollback` measure and undo a move.
- **The maturity of every configured adapter** is `taktusctl conformance list`
  (`adapters/driving/cli/conformance_command.py`), answered by `composition/maturity.py` over
  the three pools and the catalog's records. `composition/pools.py` names, in the configuration
  a maturity rests on, the manifest a connector serves a vendor's MCP server under, and the run's
  maturity port keeps such a connector without one *experimental* (ADR-0117).
- **What governs the work** is read on the HTTP surface by `adapters/driving/rest/autonomy.py`
  (`GET /autonomy`) and `adapters/driving/rest/review.py` (`GET /findings` and the review).
  `RestServices` hands them the governance component's `Corrections` and the reporting
  component's `ProductFindings`; the daemon's `Wired` gives the ones it built (ADR-0122).
- **A running step taken over by a person** is asked and handed back on the HTTP surface
  (`adapters/driving/rest/takeover.py`, ADR-0128) through the port `Takeovers` of
  `adapters/driving/rest/wiring.py`; the daemon's `Wired` gives its engine. The ask is written
  on the run's job through the queue port, which `adapters/driven/postgres/queue.py` and the
  memory queue implement over three columns of `job` (migration `0064`). The runner reads the
  ask with its lease and passes its claim to the take-over at the step's boundary. The web
  app's run page offers it (`web/src/lib/TakeoverPanel.svelte`), and the owner's conversation
  reads it as words, read back before it acts (`composition/takeover_in_channel.py`, chained
  into `OwnerAnswers` beside the change in dialogue). Where a served take-over stands is read
  from the step run alone (`StepRun.takeovers`) and handed to the run level by
  `composition/levels.py`.
- **A heal in the run's report** (UC-4.6): `composition/levels.py`'s `RepositoryLevelRecords`,
  given the ledger and the object store, reads each `step.healed` of the run with the failure
  it answered and the outcome of the step's next `step.finished`, and hands it to the run level
  as the step's `heals`; the daemon's `Wired` gives both.
- **The processes Taktus proposes** (ADR-0270) are found by the process component's rule
  `domain/service/proposing.py` over facts `composition/process_proposals.py`'s
  `ProcessProposals` reads from the ledger and the runs. Accepting one hands its words to
  `ProposalActs.ask` (`composition/proposals.py`); a decision is a ledger entry, and nothing is
  stored to make the list. The daemon hands it to the HTTP surface as `process_proposals`
  (`rest/process_proposals.py`, `GET /process-proposals` and its `accept` and `decline`), and
  the web app reads it on its page *Proposed* (`web/src/routes/proposed/`).
- **A distribution and the window of a defect** (ADR-0271): the engine applies a check of kind
  `distribution` after the result counted (`_distributed` in
  `run/application/service/execute_run.py`, the statistic in `run/domain/service/checking.py`)
  and records `result.unchecked` for a result no check judged. `composition/contents.py`'s
  `StepContents` answers the governance port `RecordedContents`: the shape of what each result
  read, and the runs a check run again marks; the daemon gives it to `ResultDefects`.
- **Where a process's control sits** (ADR-0272): the version's `control`
  (`process/domain/model/process.py`), the run's port `ExternalControl`
  (`run/ports/control.py`) that the engine asks at every step boundary, and
  `composition/control.py`'s `TaskControl`, which reads a decoupled task's state through the
  connector that serves it; the daemon gives it to the engine.
- **A partner's data contract and a chain of processes** (ADR-0273, ADR-0274): the process
  component holds a version's `contracts` (`domain/model/process.py`) and its rule
  (`domain/service/partners.py`), and a chain's shape and rules (`domain/model/chain.py`,
  `domain/service/chains.py`); `composition/chains.py`'s `ChainRuns` runs a chain link by link
  and records every handover. A failed import or export check names the contract's clause it
  breaks: `run/domain/service/checking.py` says what is lacking, `partners.breach` the clause,
  and `composition/escalations.py` hands it to the governance component's `Escalated.breaks`
  (ADR-0303). The instance stores a chain and every run of it (`DeclaredChain`, `ChainRun`;
  tables `declared_chain`, `chain_run`, migration 0111) and shows them through
  `adapters/driving/rest/chains.py` and the web app's `/chains`; the scheduler's `chains_tick`
  goes on with a waiting chain once its link finished (ADR-0301). A halted handover's package is
  the governance component's `handover_package`, raised in the owner-facing channel; a person's
  decision goes through `ChainRuns.decide`; a chain that ended is measured against its own
  objectives (ADR-0302).
- **The load measurement** (S-04, ADR-0223) is `adapters/driving/cli/load_command.py`: it
  submits the probe `blueprints/self-operation/processes/S-04-load-probe.yaml`, which the control
  plane's image carries, through the same services as `taktusctl submit`, and reads each run's
  latency from its record.
- **The export of the figures** (UC-5.7, ADR-0241) is `adapters/driving/rest/figures.py`,
  `GET /figures` and `GET /figures.csv`, over `composition/figures.py`'s `FigureReads`. It
  gathers every owner's figures, among them the levels' own (UC-6.10): the overview's counts,
  the process level's runs (`process.runs`), and what a run and each of its steps consumed
  (`run.consumed`, `step.consumed`, of the scopes `run` and `step` of the reporting
  component's `Shown`), each read from the level through the predicate the read API asks.
- **A session reached from a chat, reading a project's sources** (ADR-0304) is
  `composition/sessions.py`: `SourceKnowledge` answers the session's `ProjectKnowledge` with what
  Taktus holds and what each source system of `TAKTUS_SESSION_SOURCES` shows the participant
  through their own credential; `SessionsInChat` is a reader of the owner channel's chain
  (`OwnerAnswers.sessions_with`), read in every chat.
- **An evaluation platform** (ADR-0305) is `composition/evaluation_platform.py`'s
  `EvaluationPlatform`, over the connector pool by the capabilities `evaluations.records`,
  `prompts.versions` and `observability.costs`: `Evaluations` hands it every scored evaluation,
  and the scheduler's `platform_tick` mirrors prompts and reconciles costs once an hour.
- **A tenant's export and import** (ADR-0221): the port `TenantArchive` of
  `ports/persistence.py`, implemented over every table with a `tenant` column by
  `adapters/driven/postgres/archive.py`; `composition/tenant_export.py`'s `TenantExports`
  writes and reads the document and checks the chains after an import. `taktusctl tenant
  export` and `import` (`adapters/driving/cli/tenant_command.py`) and the administration routes
  of `adapters/driving/rest/tenants.py` reach it; `composition/local.py` and the daemon's `Wired`
  give it where the state is a database. The web app's page `#/tenants` exports and imports by
  the same routes (ADR-0295).
- **The instance's health, the backup's listing and administrative plans** (ADR-0295,
  ADR-0296): the port `BackupLog` of `ports/backups.py` answers a tenant's newest backup runs
  as `BackupHistory.recent`, which both backup log adapters fill and `composition/alerts.py`
  carries into the reporting component's `BackupState`. `adapters/driving/cli/instance_command.py`
  is `taktusctl health`, `backup list` and `update`; `adapters/driving/rest/administration.py`
  answers `/administration/health` and opens an update's plan at `/administration/update`;
  `rest/planning.py` opens a draft with an act. `composition/administration.py` names the acts a
  plan carries out (`IN_DIALOGUE`) and why every other act of `adapters/driving/inventory.py`
  stays by hand (`BY_HAND_ONLY`); its `AdministrationPlans` checks the right and carries the act
  out through the identity component when the plan is commissioned. `composition/planning.py`,
  `composition/workspace.py`, the daemon and `composition/local.py` wire it, the command line's
  `Services.planning` included.
- **Data-protection requests and the processing evidence** (ADR-0176) are served on the HTTP
  surface by `adapters/driving/rest/subjects.py` through the ports `SubjectActs` and
  `EvidenceReads` of `adapters/driving/rest/wiring.py`; the daemon's `Wired` builds the
  governance component's `SubjectRequests` over `composition/subjects.py`'s `RunHoldings`, with
  an uncached object store, and `ProcessingEvidence`, as `composition/local.py` does for
  `taktusctl subject` and `evidence`. The web app's page is `web/src/routes/subjects/`.
- **A process's takeover instructions and their trials** (ADR-0180) belong to the process
  component: `domain/model/takeover.py`, the rules registration holds them to in
  `domain/service/takeover.py`, and `application/service/takeover.py`'s `TakeoverTrials`, which
  reads the active version's instructions with each step's skills — `SkillLifecycle.of_version`
  of `composition/skills.py` derives them — and records a trial. The HTTP surface reads and
  records them in `adapters/driving/rest/takeover_instructions.py` through the port
  `InstructionActs` of `adapters/driving/rest/wiring.py`, and adds a step's entry to the state
  a take-over hands the person (`adapters/driving/rest/takeover.py`); `taktusctl takeover` is
  `adapters/driving/cli/takeover_command.py`. The daemon's `Wired` and `composition/local.py`
  give them. A trial is a row of `takeover_trial` and the instructions a column of
  `process_version` (`adapters/driven/postgres/_schema.py`, `_mapping.py`, migration `0098`).
  `composition/levels.py` reads the trials to mark a version *untried* on the process level and
  the overview, and `composition/stages.py`'s `InstructionsOfTheVersion` answers the stages'
  port from the active version. Since ADR-0225 `composition/acting.py`'s `ActingReads` reads
  them for the register, and `composition/stages.py`'s `LevelsOfTheProcess` for the stages'
  view and the report that proposes opening a stage.
- **The exactness statement where its reader is** (ADR-0152 §6) is generated by the process
  component and handed over unchanged by `composition/levels.py`: `statement_of` gives it to
  the process level, every run level and the overview, and `VersionStatements` answers the run's
  port `Statements` for a report step's `{"$run": "exactness"}`; `composition/local.py`,
  `composition/daemon.py` and `composition/replay.py` wire it into their engines. Since
  ADR-0226 the residual risk carries the measured correction rate: the `value` component folds
  it into the projection `value.corrections.v1` (`components/value/domain/service/corrections.py`)
  and answers it by `CorrectionRates` (`application/query/correction_rates.py`);
  `composition/levels.py`'s `measured_of` reads it and hands it to the statement, for the levels
  and `VersionStatements`. An `llm` step that reads the statement carries `explains` and a
  closing line naming it (`explaining` in `run/application/service/execute_run.py`).
- **A result defect found, remedied and delivered** (ADR-0179, ADR-0184, ADR-0227) is wired in
  `composition/defects.py`: `DefectWatch` raises it, `Remedies` starts the remediation run of the
  wrong run and, once it finished, of every run built on its result (`follow`), `RecheckWatch`
  applies the checks that read a source again, `IncidentDelivery` delivers the incident through
  `repository.issues` or else `tasks.items`, `IncidentReports` has a model write its report, and
  `CorrectionRequests` answers governance's port `OpenCorrections`, which holds an incident open
  while its correction waits. A step done by hand is a happening of the incident
  (`ResultDefects.by_hand`, `taktusctl defect by-hand`).
- **An outside participant's answer** (ADR-0155) is taken from a channel's intake by
  `composition/participants.py`: `ParticipantAnswers` stands ahead of `OwnerAnswers` in the
  daemon's intake, finds the waiting `human` step of the tenant by the intake's channel and
  thread, hands the message to `RunEngine.answer_participant`, and says the engine's reply in
  the thread through `ConnectorReplies`. A message it does not match goes on to `OwnerAnswers`.
- **What a person may ask for** (ADR-0159 §1 to §3) is `AgentSurface.catalogue`
  (`composition/agent_surface.py`), drawn by the reporting component's pure
  `domain/service/catalogue.py` and served at `GET /catalogue` (`adapters/driving/rest/catalogue.py`).
  Every start of a process — the command line, the MCP surface, `POST /catalogue/{process}/start`
  and the chat — builds its command with the command component's `domain/service/start.py`.
  `composition/catalogue_in_channel.py` reads the list and a confirmed start in the owner's
  conversation, handed to `OwnerAnswers` by `catalogue_with`.
- **The organisation as value streams** (ADR-0159 §4 to §6): the process component keeps a
  stream's revisions (`domain/model/stream.py`, `application/service/streams.py`, the table
  `value_stream`); `composition/streams.py` gathers the active versions, the finished runs, their
  blocks and `IdentityDirectory.role_units`, and the reporting component's pure
  `domain/service/streams.py` draws the map and the swimlanes, stored nowhere. The HTTP surface
  is `adapters/driving/rest/streams.py`, through the port `StreamActs`.
- **A role's profile** (ADR-0167 §3 to §5): `composition/profiles.py` gathers the active
  versions, the value streams, the anchors, the open decision requests, the runs and the blocks;
  the reporting component's `domain/service/profiles.py` derives the profile and its draft
  position description, stored nowhere. The HTTP surface is `adapters/driving/rest/profiles.py`,
  through the port `ProfileReads`.
- **A first process from the gallery** (ADR-0136) is read and proposed by
  `composition/gallery.py`: `Gallery` reads the directory `TAKTUS_GALLERY_DIRECTORY` names
  (`composition/settings.py`) on every request, offers a bundle that `parse_bundle` accepts at
  level 1 or 2, writes the person's choices into its schedule triggers and hands it to the
  process component's `Proposals`, which makes a proposal against no version where the process
  has none. The HTTP surface serves it (`adapters/driving/rest/gallery.py`) through the port
  `GalleryActs` of `adapters/driving/rest/wiring.py`; the daemon's `Wired` gives the one it
  built. `ProposalActs` rehearses such a proposal on its trigger's inputs and commissions it as
  the first version. `taktusctl first start` and `first rehearsal`
  (`adapters/driving/cli/first_command.py`) are what `make start`'s script calls.
- **The catalogue of signed adapters and bundles** (ADR-0175) is the catalog component's
  `domain/model/catalogue.py` (the index, the entry, the trusted key, the installation),
  `domain/service/catalogue.py` (the signed payload, the admission, the count after the
  installation) and `application/service/catalogue.py` (`CatalogueInstalls`, the one writer of
  the installation and of `catalogue.installed`), over the port `Signatures` the Ed25519 adapter
  serves. `composition/catalogue.py` reads the index files and the trusted keys that
  `TAKTUS_CATALOGUE_DIRECTORY` and `TAKTUS_CATALOGUE_KEYS` name (`load_catalogue` of
  `composition/settings.py`) and turns a bundle into a proposal; `CatalogMaturities` of
  `composition/maturity.py` counts only the halves taken after an installation, in the daemon and
  on the command line alike. `taktusctl catalogue` (`adapters/driving/cli/catalogue_command.py`)
  reaches it through `catalogue_index` and `catalogue_author` of the command line's wiring; the
  table `catalogue_installation` is migration 0096.
- **Models by dialect, and local first** (ADR-0248). `model_pool` of `composition/execution.py`
  builds each configured model by `TAKTUS_MODEL_DIALECT`: `adapters/driven/models/openai_compatible/`
  for chat completions, `adapters/driven/models/vertex/` for a regional `generateContent`
  endpoint, whose region names its location when none is declared. `load_model` of
  `composition/settings.py` binds every purpose to `TAKTUS_MODEL_LOCAL_ENDPOINT` under
  `TAKTUS_MODEL_LOCAL_FIRST` and refuses a named model there without its location.
- **Shares of the catalogue** (ADR-0246, ADR-0247) are the catalog component's
  `domain/model/shares.py` (the share, the circle, the caller's credential),
  `domain/service/shares.py` (who is inside, the withdrawal by the removal verdict, the use per
  unit, the caller's parameters) and `application/service/shares.py` (`CatalogueShares`, the
  one writer of both records and of `catalogue.shared`, `catalogue.withdrawn`,
  `catalogue.share_refused` and `credential.bound`). `composition/shares.py` answers the run's
  port `Shares` (`run/ports/shares.py`) from it: the engine passes over a model the run's
  identity may not use (`not_shared`) and replaces a shared connector's credential names with
  the caller's own, or refuses the call (`frame.refused`). Whether a connector call is
  admitted is one rule, `SharesOfTheRun.connector_refused` (ADR-0294): the identity is inside
  the share, and the run's process may use the connector by the placement the identity
  component's `OrganisationStructure` holds, which `shares_of` is handed. `SharedAgents`
  refuses a caller outside an agent's share (`agent.refused`), and `CatalogGuidance` hands a run only the skills
  shared with its identity. `CatalogueUse` reads an entry's use per unit and the viewer's own.
  `taktusctl catalogue share`, `withdraw`, `shares`, `use` and `bind-credential` reach it
  through `shares` and `catalogue_use` of the command line's wiring, and `taktusctl skill
  export` writes skills back as their directories; the tables `catalogue_share` and
  `caller_credential` are migration 0103.
- **Domain blueprints** (ADR-0263, UC-15.1) are the catalog component's
  `domain/model/blueprint.py` (the blueprint, what a bundle came to, the instance and its
  answers, the offer, the figures per domain), `domain/service/blueprints.py` (the admission
  with every finding, the open questions, the starting level, the runs counted per domain) and
  `application/service/domains.py` (`DomainInstances`, the one writer of the instance), over the
  ports of `ports/domains.py`: `ProcessProposals`, `People` and `Adapters`.
  `composition/domain_blueprints.py` reads a blueprint's directory, holds each bundle to
  `parse_bundle`, answers the three ports from `Proposals`, the identity directory and the
  release's list of connectors, and exports a blueprint as its files. `taktusctl domain`
  (`adapters/driving/cli/domain_command.py`) reaches it through `domains` of the command line's
  wiring; the table `domain_instance` is migration 0106.
- **A halted run raised and resumed** is `taktusctl resume` (`adapters/driving/cli/resume_command.py`, #458): it reads no bundle, so the process's active version stays; it raises a run's money or its quota (DEC-0208).
- **Memory once started.** Once wired, the daemon collects and freezes what its start left
  alive — the modules, the wiring — so that a full garbage collection, which stops every thread
  of the process, no longer scans it: 2 000 runs read at once paused the event loop half as long
  (#360).
- **Shutdown** is the same for every role: on SIGTERM the HTTP surface stops, the runner claims
  nothing more, every running run is asked to stop at its next step boundary and the running
  worker step may finish up to `TAKTUS_SHUTDOWN_CEILING_SECONDS`, the claims are released, the
  process exits 0. A role still running at the ceiling is abandoned and its run recovered by
  the next runner from its last persisted boundary.
- **Tenants.** An instance serves every tenant of its registry, the table `tenant`, which the
  identity component owns (ADR-0104). An administrator adds to it with `taktusctl tenant
  create` or `POST /administration/tenants`, and Taktus generates the identifier. Every role
  reads the registry at every round, so a tenant created while the daemon runs is served
  without a restart; the runner claims for each tenant in turn. Nothing narrows the
  registry: the variable that did is removed, and a daemon that still sets it refuses to start
  (ADR-0104 §7). An intake lands in the
  tenant of the identity the sender's account is linked to, and nowhere when it is linked to
  none (ADR-0040); the oldest tenant is only where such a sender is answered from. Such a sender is answered only
  for what they wrote — an intake whose `intent.authored` is `false`, such as a label added, is
  answered nothing — and once per conversation within `TAKTUS_OFFER_WINDOW_SECONDS`, a day by
  default. The `api` role makes the offers of one conversation one at a time, and keeps when it
  made each in memory; the offer's key names the stretch of the window, so that another
  process finds an offer made in the same stretch (ADR-0040, amended).
- **The instance's own platform.** `TAKTUS_PLATFORM` names it and `TAKTUS_ADMINISTERS` declares,
  per credential, the platforms it administers (`ports/administration.py`, ADR-0052). The
  composition root reads both once and hands the one value to the process component's
  registration and to the run engine's admission; without a platform the daemon warns at start.
- **The machine's hardware.** The hardware port (`ports/hardware.py`, ADR-0284) is served by
  `adapters/driven/platform/hardware.py`, which reads the kernel's device classes and runs no
  program. `composition/hardware.py` hands it, with every configured model and its
  `TAKTUS_MODEL_NEEDS`, to governance's `ReportHardwareHandler`; `taktusctl hardware` prints the
  report through `Wiring.hardware`, with no state and no database.
