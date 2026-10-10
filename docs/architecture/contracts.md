# Contracts

The boundary between what Taktus builds and what it conducts.

---

## 1. Three adapter families

| Contract | For | Basis | Directory |
|---|---|---|---|
| **Worker** | execution units: coding agents, agent runtimes, script runners, training runs | HTTP + Server-Sent Events, JSON Schema | `contracts/worker/v1` |
| **Connector** | tools and channels: repositories, ticket systems, chat, knowledge, warehouses | MCP | `contracts/connector/v1` |
| **Model** | models | OpenAI-compatible endpoints | `contracts/model/v1` |
| *(Process)* | the portable process bundle — a format, not an adapter | JSON Schema | `contracts/process/v1` |
| *(Shared kernel)* | the concepts all of the above share — a vocabulary, not an adapter | JSON Schema | `contracts/shared/v1` |

HTTP and SSE rather than gRPC for workers: a worker must be buildable without knowing the core's
language — as a script, as a small service, as a shell wrapper around a foreign CLI. Efficiency is
not the bottleneck here; adapter variety is.

---

## 2. The contracts in brief

### 2.1 Worker

| Capability | Why it is required |
|---|---|
| **Accept an assignment** — task, context, frame, autonomy level | governance reaches into execution |
| **Stream events** — progress, decisions, tool calls | ledger and status queries |
| **Report consumption per step** — tokens, compute seconds, resource class | accounting in normalised units |
| **Estimate demand before starting** and **signal step boundaries** | admission control; stopping without data loss |
| **Hand over artifacts** — code, documents, structured data, model files | a result is data, not prose |
| **Accept credentials at runtime, never store them** | secret safety |
| **Least privilege** — only the tools the process allows | permission model |
| **Declare capabilities** — what this worker can do, and optionally its own version | processes reference capabilities, never product names; the version is recorded in the provenance of every result (ADR-0021) |

Full specification: [`contracts/worker/v1/README.md`](../../contracts/worker/v1/README.md).
The core's side of it is the worker port (`src/taktus/ports/worker.py`): the contract's shapes
as frozen types and the protocol the run component calls. `tests/contract` holds those types to
`Worker.json` and its examples, so that the port and the contract cannot drift apart. A worker's
`503` to a new assignment reaches the core as `WorkerAtCapacity`, on which the step waits
(ADR-0037). How a
worker comes to exist for a job — as a process, as a container — is the execution port's
business (§2.4), and a worker that is already running is reached by endpoint.

Two workers exist. The reference worker `script` runs shell commands and no AI. The coding
worker (`workers/claudecode/`, named by capability everywhere else) wraps a coding agent: a
step per completed tool call, tokens per step, money at the end, two authentication modes,
and a session that expires halts at the last boundary. It passes the same suite, faults
included, against a stand-in for the agent; its README states what it cannot do.

### 2.2 Connector

A connector is an MCP server; the contract is what Taktus needs on top of MCP (ADR-0024). Two
directions, governed differently: **actions**, where Taktus calls an operation, and **intake**,
where an event from the outside becomes a command or is refused.

| Capability | Why it is required |
|---|---|
| **Declare capabilities and operations** — by function, never by product; served as one MCP resource | processes bind capabilities; the tool list is checked against the declaration |
| **Declare the effect of every operation** — `read`, `write`, `delivery` | `write` and `delivery` leave the system: the run records them as egress entries, and correcting their result afterwards is anchored (ADR-0022). Declared, "has left the system" is a field, not a judgement |
| **Declare the idempotency of every outward operation** — `native`, `marked`, `none` — and honour the idempotency key of every call | a step retried after a restart must not open a second pull request (ADR-0005). `none` is allowed and honest: Taktus then never repeats the call on its own |
| **Act with the requesting identity's credentials, by name, read at the call** | source-system permissions remain in force; the connector has no credential of its own |
| **Classify every error** — a failure with cause, effect and retryable | the run knows whether the effect happened and whether the same call may be repeated (ADR-0021) |
| **Report consumption per call** | connector calls cost close to nothing and are counted, not ignored |
| **Verify the signature of every incoming event before reading it**, then normalise it as far as the channel can | intake without a signature is not a valid declaration; the identity component completes the command |

Full specification: [`contracts/connector/v1/README.md`](../../contracts/connector/v1/README.md).
The connector port on the core's side (`src/taktus/ports/connector.py`, over MCP in
`adapters/driven/connectors/mcp/`) serves both directions. **Intake:** the HTTP surface hands a
webhook delivery to the connector that serves the channel and keeps what it accepted.
**Actions:** the run calls an operation with a call context and reads the result — the
declaration's shapes, the context, the result and the classified error are bound as frozen
types, held to `Connector.json` by `tests/contract`. A `rule` step whose work is
`rule: connector` is bound this way (`components/run/domain/model/work.py`,
`examples/README.md`); a `wait` step can wait on an external state read the same way.

What a read returns is the connector's to declare, not the contract's. The reference repository
connector reads an issue with its labels and milestone, lists the open issues to the last page,
and lists a directory at a ref (issue #70). P-03 Implementation feeds those readings to the run
component's built-in rule `ready`, the backlog's ready standard
(`components/run/domain/service/ready.py`, DEC-0051). P-01 Roadmap control feeds the open
issues and the roadmap's text, read as a file, to the rules `backlog` and `roadmap` of the same
component (issue #71). The rules judge the readings; the connector judges nothing. An issue's
form ends at a horizontal rule: a footer after it belongs to no section (DEC-0116). Both
connectors read their platform's member list — account, name, kind, and role or address with
whether the platform confirmed it, nothing else of a member — as the proof DEC-0127 rests on;
nothing calls it yet (NTC-0107).

**What idempotency requires of a connector, seen from the run.** The run derives the
idempotency key of every call from the run, the step and the step's *attempt*:
`taktus:<run id>:<step id>:<attempt>`. It is never stored, so that a resumed attempt after a restart
derives the same key; a step recovered from a crash, or resumed from a stop, therefore repeats
its call with the key of the attempt that was interrupted, and a `marked` or `native` connector
answers with the original record and `replayed: true`. The attempt advances only when a step is
retried after a failure the connector said was *not* retryable, so that a retry after
`unavailable` or `unknown` on a `marked` operation still finds the original. What the run does
with the declaration: the effect of an outward result becomes an `egress.write` or
`egress.delivery` entry in the same transaction as `step.finished`, referencing the result
artifact and the digest the connector reported (ADR-0022 §4); an operation declared
`idempotency: none` is **never repeated by the run on its own** — a call that failed with
effect `unknown` ends the step failed and the run escalated, and the run's reason says that
resuming repeats the call, so that the person who resumes has checked the target first
(ADR-0024 §3). No call is retried automatically in this version; every retry is a resume.

### 2.3 Model

A model is reached by an OpenAI-compatible endpoint: `POST /chat/completions` with a model
name, messages and an output limit, the first choice's message as the answer, the usage as the
consumption. A vendor's API, a local model server and most gateways answer this dialect, which
is why it is the basis and why no vendor's own extensions are used.

| Capability | Why it is required |
|---|---|
| **Answer a prompt** — a system message, a user message, an output limit | an `llm` step is one completion |
| **Report the tokens used** and **which model answered** | tokens are counted per step (ADR-0005); a variable method is reproducible only at a pinned version, so the answering model goes into the provenance (ADR-0021) |
| **Say why it stopped** — the end of the answer, or the output limit | an answer cut off at the limit does not leave the step |
| **Take a bearer credential at the call, or none** | a local endpoint needs none; a vendor's key is a parameter (`CREDENTIALS.md`) |
| **Say when the provider is at its rate limit** — apart from every other refusal | nothing was produced and the call may be made again: the step waits at its boundary instead of failing, booked to `limit.provider` (ADR-0043). The port's `ModelAtLimit`; the adapter raises it for `429` |

| **Declare what it can compute before a call** — how it counts input, whether its output limit is hard, which price kinds it reports, how its provider bills | a budget is only as strong as the provider permits; the run derives from the declaration what it can promise and says so when the budget is set (ADR-0005, third amendment) |
| **Report the tokens by price kind** where the provider does — uncached input, cache read, cache write, output | money is computed from the record at a versioned price table (ADR-0010) |

The contract is a schema with a conformance suite (`contracts/model/v1`): the declaration
(`Calculability`), the usage of one call, the price table, and the checks M-01 to M-04 —
`uv run taktusctl conformance run --contract model/v1`. The core's side is the model port
(`src/taktus/ports/model.py`) and its one adapter (`adapters/driven/models/openai_compatible/`),
configured by `TAKTUS_MODEL_ENDPOINT`, `TAKTUS_MODEL_NAME` and `TAKTUS_MODEL_PURPOSES` — one model,
for the purposes it is named for or for all — and by `TAKTUS_MODEL_BILLING`,
`TAKTUS_MODEL_OUTPUT_CAP` and `TAKTUS_MODEL_PROVIDER_LIMIT`, what its provider permits; it is
recorded in the ledger as `model.endpoint`. Over the dialect it counts input as an upper bound
(the contract's §3). A process names a *purpose* (`reasoning`, `triage`), never a product
(ADR-0003). `tests/adapters/models` proves the adapter against a fake of the endpoint, and
`tests/conformance/test_model_v1.py` the suite against the same fake, honest and faulty; the
run's `llm` step is `components/run` (`examples/README.md`). The evidence of what providers
permit is `docs/research/2026-09-30-what-providers-allow.md`.

### 2.4 The execution port

The worker contract says how the core talks to an execution unit. It says nothing about how
the unit comes to exist for a job, with what isolation, and how a credential reaches it. That
is the execution port (`src/taktus/ports/execution.py`; ADR-0002): one job, one unit, started
by an adapter, reachable at an endpoint that speaks the worker contract, torn down when the
job ends. A job's workspace does not outlive the job; a unit's *state* — its checkpoints — does,
so that a resumed assignment finds them in a new unit.

| `TAKTUS_EXECUTION` | Isolation | Adapter | For |
|---|---|---|---|
| `endpoint` | whoever runs the worker | `adapters/driven/workers/http/` | a worker that is already running, at `TAKTUS_WORKER`; the default |
| `process` | none | `adapters/driven/execution/process.py` | local development, a single user. **Refused from autonomy level 3 upwards, and when the level is unknown** — the rule is `ports/execution.py:refusal()`, and `tests/governance` holds the adapter to it. The unit's memory limit is enforced on Linux (`RLIMIT_DATA`, per process) and refused elsewhere unless `TAKTUS_EXECUTION_MEMORY_UNENFORCED=true` accepts it unenforced (`docs/architecture/platform.md` §5) |
| `container` | process, filesystem, network | `adapters/driven/execution/container/` | operation. One container per job with limits, credentials in memory only, and a network that reaches `frame.allowed_hosts` and nothing else |
| `cluster` | process, filesystem; network where the cluster enforces network policies | `adapters/driven/execution/kubernetes/` | a cluster the control plane runs in. One Job per job in the execution namespace with limits and a deadline, a `restricted` pod with no service-account token, credentials from a Secret that lives as long as the job, and an egress proxy of its own; refuses hosts, and every job from level 3 upwards, where network policies are not enforced (`deploy/k8s/README.md` §7) |

The worker port over the execution port is `adapters/driven/workers/launched.py`: one unit
per assignment, started with the credentials, the hosts and the autonomy level the assignment
carries; a *probe* — a unit with no credential and no host — answers `capabilities` once and
`estimate` before every worker step, which costs one unit start per estimate and is the price
of never starting a unit with credentials before admission control has said yes (ADR-0005).
A unit the adapter killed — memory, wall clock — is a failed step with that cause, never a hang.

**The launch convention** is the one thing a unit must know when an adapter starts it: it reads
`TAKTUS_UNIT_PORT` for the port to serve the contract on and `TAKTUS_UNIT_STATE_DIR` for the
directory that outlives the job. Both workers of this repository take them as defaults; a
foreign worker is wrapped by a shell script that translates.

**Credentials** travel as names through the contract. At the moment a unit is started the
adapter reads each value through the configuration port under `credential.<name>` — the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` points at — and injects it. The `process` adapter puts it into
the unit's environment and refuses a credential injected as a file: without a filesystem of
its own, a job has nowhere to keep one. The `container` adapter starts the unit's container
behind a launcher it places there, writes each value into a memory-backed directory after
the container has started, and the launcher exports the environment kind and removes the
files before it starts the unit: no value is on a volume, in an image layer, in the
container's recorded configuration, on a command line, or in a log. The launcher stays in front
of the unit as its parent, forwards signals to it, and after the unit died reads the kernel's
own count of out-of-memory kills in the unit's cgroup. The engine's flag for such a kill comes
from a separate event that may arrive late or never, so the adapter classifies a memory kill
from either record (issue #29).

**The container adapter's wall**, per job: a container from the unit's image with no
capability, no privilege escalation, a process limit, a memory limit without swap and a CPU
limit — the engine kills on memory, the adapter on the wall clock; an engine that reports it
cannot limit memory or swap is refused before anything is created; a network of its own,
internal, whose only other member is the job's *egress container*, which forwards the unit's
port inward so the control plane can reach it and is an HTTP proxy outward that admits
exactly `frame.allowed_hosts` and answers 403 to every other host, an empty list reaching
nothing (this is where DEC-0008's field becomes a wall); one named volume per unit for its
state and no other mount, the engine's socket never among them. The adapter speaks the
engine's HTTP API over its socket — Docker or Podman — so that the control plane image needs
no client. `tests/adapters/execution/test_container.py` proves every one of these from inside
a job, and `tests/integration/test_launched_container.py` runs a process through it, stops it
at a boundary and resumes it in a new container.

**The cluster adapter's wall** is the same shape in a cluster's terms, specified in
`deploy/k8s/README.md` §4 to §7: a Job instead of a container, a Pod Security level instead of
engine flags, a namespace's default-deny network policy instead of an internal network, and an
egress proxy that is a second Job instead of a second container. The proxy asks for a token
only the job's own unit holds, because a namespace's policy cannot pair a unit with its proxy.
Credentials come from a Secret created for the job: a file credential is mounted at its path,
an env credential is a variable from the Secret. The adapter speaks the cluster's API with
`httpx` and makes only the calls of the Role Taktus's service account holds.
`tests/adapters/execution/test_kubernetes.py` holds it to all of it against a fake of the API;
`test_kubernetes_cluster.py` runs the container adapter's checks from inside a job on a real
cluster, and skips with the reason where none is configured (NEED-0015).

---

## 3. Conformance and maturity

Every adapter tests itself:

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
uv run taktusctl conformance run --contract connector/v1 --endpoint http://localhost:9100/mcp \
    --scenario scenario.json
```

(`taktusctl` lives in the project environment, hence `uv run`.) `conformance run` checks an
endpoint the caller names and records nothing. `conformance record <identifier>` has the instance
run the same suite against the adapter its configuration resolves, and record it (below).

| Maturity | Condition |
|---|---|
| **experimental** | from the community, no evidence |
| **verified** | conformance suite passed **and** removal test passed |
| **reference** | maintained by the project, the model for new adapters |

**Production processes at autonomy level 3 and above may only use adapters at *verified* or above.**
The run engine holds it before a step starts (ADR-0039): a step at level 3 or above whose
adapter is below *verified* is not run on it, and the finding names the step and the adapter. The
engine asks the catalog's record through its maturity port; a rehearsal and the loopback
connector, which act on nothing outside, are not held to it (NTC-0079). An integration reaches
*verified* once the instance has recorded both halves for the configuration that resolves it now;
until then a real run at level 3 halts at its first step that needs it.

The conformance suite is the real asset here — not the adapter code, but the ability to check.
Without it, "interchangeable" is an assertion.

The suite lives in `src/taktus/conformance/` and imports nothing from the control plane; it talks
to a worker over HTTP and SSE, and to a connector over MCP, as a foreign control plane would. It
runs W-01 to W-11 and W-13 to W-18 against a live worker and C-01 to C-09 against a live connector, and reports
W-12 and C-10, the removal test, as *pending*: a suite that talks to one adapter cannot remove
it from processes. Its report states which half of *verified* it proves.

**The removal test is a process, not a suite check.** `blueprints/self-operation/processes/
S-01-removal-test.yaml` runs weekly, once per configured integration: it withholds the
integration, exercises the registered processes that use it, restores it, and records one of
four verdicts in the ledger as `removal.tested` and in the adapter's maturity record
(`components/catalog`, table `adapter_maturity`). A process is exercised by **rehearsing** it
twice, with and without the integration (ADR-0030): a rehearsal run sends no outward connector
call, answers each with the recorded response of the operation's last real call through the
same adapter, and marks every ledger entry `rehearsal: true`. A process whose outward
operation was never called for real, or whose worker may reach hosts, is resolved statically
instead, and the finding says why. *Broke*: a step lost its only adapter and no person takes it
over. *Changed*: another adapter or a person serves the step; quality and cost changed.
*Untested*: no registered process uses the integration, so nothing was exercised; it does not
count towards *verified*. *Exception*: the integration cannot be removed by design — the
database, ADR-0002. Every result names the configuration it was taken under: the adapter that
served the identifier, what it declared and its version.

**The conformance half is recorded by the instance that ran the suite (ADR-0044).** The instance
runs the suite of an adapter's contract against the endpoint its own configuration resolves for
the adapter identifier: the configured worker (or one unit started for the suite, for a launched
kind), the connector `TAKTUS_CONNECTORS` maps the label to, with the scenario
`conformance.connector.<label>.scenario` names, the configured model endpoint. A person starts it
with `taktusctl conformance record <identifier>`; a process through the loopback operation
`orchestrator.conformance.run`. Both take the identifier and nothing else. One transaction writes
the ledger entry `conformance.tested` — its digest covers the report and the configuration — and
the conformance half of the adapter's maturity record: the contract and its version, the Taktus
version, the configuration, the outcome with the checks that failed or were inconclusive, the
digest, the time and the actor. `passed` is what the report computes: no check failed, none
inconclusive, a pending one counts against nothing. A run that did not pass is recorded too. No
command, endpoint or operation takes a report, a verdict or a date; a report run elsewhere is
never recorded. **A pass counts only for the configuration it names**: the run's maturity port
compares it with the configuration the run resolves for the identifier now, and where they differ
the adapter is *experimental* and the record says the pass was for another configuration.

The maturity record derives *verified* from both halves and names which is missing. The
blueprint's README carries the removal test as instructions a person follows by hand, and the
record of the first run; each contract's `CONFORMANCE.md` carries the suite, run by hand against
the same endpoint with its report kept as evidence. What both halves share — the report, the
findings, the catalogue of checks, the schema validators — lives at the package level; the
connector half is `src/taktus/conformance/connector/`. How a third party runs it against an
adapter of their own: [`contracts/worker/v1/CONFORMANCE.md`](../../contracts/worker/v1/CONFORMANCE.md),
[`contracts/connector/v1/CONFORMANCE.md`](../../contracts/connector/v1/CONFORMANCE.md) and
[`contracts/model/v1/CONFORMANCE.md`](../../contracts/model/v1/CONFORMANCE.md).
`make gate-conformance` proves the suite itself for both contracts: the reference worker passes
it in both profiles, the reference connector passes it against a fake of its service, and for
every fault either reference adapter can inject the suite fails on exactly that check — run the
way the instance runs it, and recorded as not passed (NTC-0092).

Before the suite runs against an adapter, `make gate-contracts` checks the contract itself: every
schema is valid and carries the `$id` its path prescribes, every example validates, and every check
W-01..W-18 and C-01..C-10 has a fixture (`tools/validate_contracts.py`).

Every schema is identified by `https://taktus.eu/contracts/<family>/v1/<Concept>.json` — its path
under `contracts/` behind the project's domain. A released v1 schema is immutable; changes become
v2 (ADR-0019).

---

## 4. Reference adapters

Under `workers/`, `src/taktus/adapters/driven/connectors/` and `.../models/`. They are proof and
example, not a requirement. The core runs with all of them removed — it simply cannot reach anything.

| Family | Adapter | Why this one |
|---|---|---|
| Worker | `script` | the trivial worker. **Mandatory from day one:** a contract a shell script cannot satisfy is built around one specific coding agent. Exists (`workers/script/`), passes the suite; its `longrun` profile has the shape of the second proof case and trains nothing. The control plane reaches it through the HTTP worker adapter (`src/taktus/adapters/driven/workers/http/`), the client side of this contract; `examples/processes/` runs a process against it. |
| Worker | `mlbench` | training, evaluation, embeddings, classical ML. The second proof case: hours of runtime, a GPU held, a model artifact returned. Exists (`workers/mlbench/`) for classical models on a CPU: it trains a linear classifier one epoch per step, evaluates it on held-out rows and serves predictions with their confidence, reproducibly at a pinned version, and passes the suite, faults included (#89). Embeddings and a run on an accelerator are #210 |
| Worker | `claudecode` | the first real coding worker. Exists (`workers/claudecode/`), passes the suite in both authentication modes, faults included, against a stand-in for its agent; a live run needs a credential the operator supplies |
| Worker | `codex` | the second real coding worker; validates the contract against a second vendor |
| Connector | `github` | repository: issues, pull requests, pipelines, comments, branches, labels, and one file read at a ref — actions and webhook intake. Exists (`src/taktus/adapters/driven/connectors/github/`), passes the suite against a fake of its service; the example of idempotency: a pull request opened for a step is opened once, proven across a restart of the connector against the fake and, with a credential, against the real service (`tests/adapters/connectors/test_repository_live.py`). Acts as Taktus's own app when configured with the app's identifier and key — the requesting identity behind the name it declares for actions, minting an installation token that lives an hour for its one repository, never stored — and with a token otherwise (ADR-0033); the suite passes in both modes. Reached by the daemon's webhook intake and by the run's connector steps. Reads every secret — the webhook's included — from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, and from the variable only without one (DEC-0130); on a cluster the chart deploys it beside the roles (`deploy/k8s/README.md` §2). A branch it writes
keeps the mode each file has in the base — an executable a change touches stays executable —
read from the base tree before the new tree is written (DEC-0020). A file entry may carry
`executable`, and the coding worker's changeset sets it on every file its index records as
executable, so a script a change adds arrives executable too; a file the base does not have
and that carries no flag is written as a plain file (issue #28) |
| Connector | `slack` | the chat service the owner of this tenant uses: both a command channel and a delivery channel, the capability `chat.threads` and the channel `channel.chat`. Exists (`src/taktus/adapters/driven/connectors/slack/`): a thread read, a message posted into a conversation or a thread as a `delivery` that is `marked` by its metadata — posted once across a restart of the connector — and event intake under `hmac-sha256-timestamped`, a delivery signed more than 300 seconds before it arrived refused as a replay (ADR-0024, amendment). Passes the suite against a fake of its service, fault for fault; against the real service when NEED-0018 is provided. Added to an instance by one entry of `TAKTUS_CONNECTORS`, nothing in the core changed (`tests/adapters/connectors/test_chat_channel.py`). The URL check the service makes before it sends events is answered: verified, refused as no event with the challenge as its `answer`, which the HTTP surface returns as it is (ADR-0024, amendment of 2026-10-09; `tests/adapters/rest/test_intake_over_mcp.py`) |
| Connector | `http` | the generic fallback for anything with a documented API |
| Connector | `directory` | the knowledge system of an organisation that has none: the capability `knowledge.pages` over one directory, a Markdown file per page, the mark and the key in the file's last line as a comment a viewer does not show (ADR-0065). Exists (`src/taktus/adapters/driven/connectors/directory/`): a list, a read, and a write that replaces a page only where it holds the expected text, `marked` by the key beside the page. Runs inside the process that uses it, as the loopback connector does; it has no MCP binding and so is not held to the suite. `taktusctl guides publish --to` uses it, and an instance serves it where `TAKTUS_KNOWLEDGE_DIRECTORY` names a directory (ADR-0066). A connector to a wiki serves the same capability (issue #197) |
| Model | `openai_compatible` | covers Ollama, vLLM and most vendors. Exists (`src/taktus/adapters/driven/models/openai_compatible/`), proven against a fake of the endpoint; the one model `llm` steps ask |
| Model | `anthropic` | native capabilities the common denominator does not carry |
| Connector | `loopback` | Taktus reached by Taktus. Exists (`src/taktus/adapters/driven/connectors/loopback/`): the capabilities `orchestrator.integrations`, `orchestrator.removal`, `orchestrator.maturity` and `orchestrator.conformance` behind the action side of the connector port, every operation `read` because nothing it does leaves the system — except `orchestrator.conformance.run`, which runs a suite and is declared `write` (NTC-0091) — over an `Orchestrator` the composition root implements on the instance's own services (`composition/loopback.py`; ADR-0027). And `orchestrator.guides`, the guides' sources, rendering, measuring, publishing and the report of a hand edit, over the `Guides` of `composition/guides.py` (ADR-0066); its `publish` writes into the knowledge system and is declared `write`, `marked`. It is what the removal test calls, and what a process calls to have the instance run an adapter's conformance suite; it is never itself an integration the removal test lists. In an installation with several instances the same capabilities can be served over the HTTP surface instead |

**Rule:** a second real worker of each shape exists **before** features build on worker behaviour.
Otherwise there is a contract with one implementation, and that is not a contract.

---

## 5. What Taktus does not ship

Taktus bundles no foreign CLIs, no foreign clients, no foreign runtimes. It ships the contract, the
check and the references. Anything else would be the tool landscape Taktus explicitly is not.

---

## 6. Where adapters live

**Until `1.0.0`:** all in the main repository, because the contract still moves and separate
repositories would mean a version matrix instead of progress.

**From `1.0.0`:** the contract is frozen and versioned. Community adapters move to their own
repositories; the main one keeps the references and the suite. See
[ADR-0009](../adr/ADR-0009-adapter-monorepo.md).

---

## 7. Integration code

Two tiers, because core dependencies and customer tools need different standards.

**Tier 1 — what Taktus itself needs to run** (database, queue, secret store, telemetry, reference
workers): an open contract · an OSI-conforming licence · self-hostable · data exportable · removal
test passed · an active community or a named replacement.

**Tier 2 — what Taktus conducts:** liberal. Taktus orchestrates what the organisation already has,
including proprietary systems. Condition: connected through the connector contract, source-system
permissions remain in force, no circumvention.

**Excluded outright in both tiers:** tools with a surveillance character towards individuals
(keystroke logging, productivity scoring, location tracking) · tools that bypass source-system
permissions · tools with no data export for Taktus's own data.
