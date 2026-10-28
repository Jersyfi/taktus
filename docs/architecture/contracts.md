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
| **Run the task's own commands around the work** — one before it, which prepares the workspace, and one after it, whose output is an artifact; never a model's (ADR-0053, ADR-0100) | a fixed operation stays fixed, and a workspace can run its repository's checks |
| **Stream events** — progress, decisions, tool calls | ledger and status queries |
| **Report consumption per step** — tokens, compute seconds, resource class | accounting in normalised units |
| **Estimate demand before starting** and **signal step boundaries** | admission control; stopping without data loss |
| **Hand over artifacts** — code, documents, structured data, model files | a result is data, not prose |
| **Accept credentials at runtime, never store them** | secret safety |
| **Least privilege** — only the tools the process allows; a worker that offers its work only those may state so, once, as `reach.stated` (ADR-0098), and the core reads the event and acts on nothing in it | permission model |
| **Declare capabilities** — what this worker can do, and optionally its own version | processes reference capabilities, never product names; the version is recorded in the provenance of every result (ADR-0021) |
| **Optionally: take a message at a boundary, hand an assignment over, connect outbound only** — steering, a `handover.state` document another place continues from, and the outbound binding, which carries the same requests from the control plane to a worker that opens no port; a tool call may say whether it acts outward, and a model's answer may be reported (ADR-0139) | a person corrects or takes over running work; a worker runs inside a customer's network; a worker's repeated calls can be counted |

Full specification: [`contracts/worker/v1/README.md`](../../contracts/worker/v1/README.md).
The core's side of it is the worker port (`src/taktus/ports/worker.py`): the contract's shapes
as frozen types and the protocol the run component calls. `tests/contract` holds those types to
`Worker.json` and its examples, so that the port and the contract cannot drift apart. A worker's
`503` to a new assignment reaches the core as `WorkerAtCapacity`, on which the step waits
(ADR-0037). A worker that cannot be asked for its capabilities reaches the core as
`UnaskedWorker`, which names the worker's configuration and keeps the cause. The step fails with
that cause, or waits when the cause is `WorkerAtCapacity` (#589). How a
worker comes to exist for a job — as a process, as a container — is the execution port's
business (§2.4), and a worker that is already running is reached by endpoint.

Two workers exist. The reference worker `script` runs shell commands and no AI. The coding
worker (`workers/claudecode/`, named by capability everywhere else) wraps a coding agent: a
step per completed tool call, tokens per step, money at the end, two authentication modes,
and a session that expires halts at the last boundary. It passes the same suite, faults
included, against a stand-in for the agent; its README states what it cannot do. Both coding
workers hand their agent the target repository's `AGENTS.md`, the open convention's file of a
repository's rules for coding agents, in its brief before the task, once per session. No worker
depends on a file named after one agent's product (ADR-0113 §3).

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
| **Declare which capabilities serve a subject's data, and answer a scoped call with that subject's data only** — `scoped`, cause `out_of_scope` | a step that serves a case sees only its case's data, whatever a model names (ADR-0130) |

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
(`components/run/domain/service/ready.py`, DEC-0051); P-02 Refinement asks it which sections an
issue lacks, and an issue that lacks none is no failure but an empty list, on which P-02's
writing steps skip themselves. P-01 Roadmap control feeds the open
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

**What a step may see (ADR-0130).** A step that serves a case names its subject from the run's
inputs (`scope`), and every connector call of it carries the scope. A connector that declares a
capability `scoped` answers with the subject's data only and refuses another subject's with
`out_of_scope`; the run records the refusal as `frame.refused`. A step that analyses
(`analytic`) reaches its one source through reads only, and only a source its tenant declares
free of personal fields (`taktusctl sources`). A step that reads a capability serving personal
data — by its connector's declaration or its tenant's — without a scope waits for a person at
every level (`components/run/domain/service/frame.py`, `tests/components/run/test_case_scope.py`).

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
| **Say when the provider is at its rate limit** — apart from every other refusal | nothing was produced and the call may be made again: the step waits at its boundary instead of failing, booked to `limit.provider` (ADR-0043). The port's `ModelAtLimit`; the adapter raises it for `429`, with the delay its `Retry-After` asks for |

| **Declare what it can compute before a call** — how it counts input, whether its output limit is hard, which price kinds it reports, how its provider bills | a budget is only as strong as the provider permits; the run derives from the declaration what it can promise and says so when the budget is set (ADR-0005, third amendment) |
| **Report the tokens by price kind** where the provider does — uncached input, cache read, cache write, output | money is computed from the record at a versioned price table (ADR-0010). The adapter reads cached tokens nested in `prompt_tokens_details` and at the top level of the usage (`contracts/model/v1` §5). The record names the model as the endpoint named it; a dated name is priced at the table's undated entry where it has no dated one (§6) |

The contract is a schema with a conformance suite (`contracts/model/v1`): the declaration
(`Calculability`), the usage of one call, the price table, the weighting table of the Takt, and the checks M-01 to M-04 —
`uv run taktusctl conformance run --contract model/v1`. The core's side is the model port
(`src/taktus/ports/model.py`) and its one adapter (`adapters/driven/models/openai_compatible/`),
configured by `TAKTUS_MODEL_ENDPOINT`, `TAKTUS_MODEL_NAME` and `TAKTUS_MODEL_PURPOSES` — one model,
for the purposes it is named for or for all — and by `TAKTUS_MODEL_BILLING`,
`TAKTUS_MODEL_OUTPUT_CAP`, `TAKTUS_MODEL_PROVIDER_LIMIT` and `TAKTUS_MODEL_USAGE_KINDS`, what its
provider permits and reports; it is
recorded in the ledger as `model.endpoint`. Over the dialect it counts input as an upper bound
(the contract's §3). A process names a *purpose* (`reasoning`, `triage`), never a product
(ADR-0003). `tests/adapters/models` proves the adapter against a fake of the endpoint, and
`tests/conformance/test_model_v1.py` the suite against the same fake, honest and faulty; the
run's `llm` step is `components/run` (`examples/README.md`). The evidence of what providers
permit is `docs/research/2026-09-30-what-providers-allow.md`.

**A chain of models per purpose (ADR-0116).** `TAKTUS_MODELS` names several models in order,
each configured under `TAKTUS_MODELS_<MEMBER>_…` and recorded as `model.<member>`. The chain
of a purpose is every member that serves it, in that order. Each member declares where it
processes (`…_LOCATION`: `own`, `eu`, `elsewhere`) and the exactness classes it may produce for
(`…_EXACTNESS`). A step is routed to the first member that its tenant's residency rule admits,
that may produce its class, and that is not cooling down
(`components/run/domain/service/routing.py`). A member that answered `429` or failed cools
down, and the step moves to the next member at its boundary. The provenance record names the
member and the route (`route`). `tests/components/run/test_model_routing.py` proves it. A
gateway stands behind a member only as a pass-through: `deploy/docker/README.md`.

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
| `container` | process, filesystem, network | `adapters/driven/execution/container/` | operation. One container per job with limits, credentials in memory only, and a network that reaches the job's hosts — `frame.allowed_hosts` and the worker's service hosts — and nothing else |
| `cluster` | process, filesystem; network where the cluster enforces network policies | `adapters/driven/execution/kubernetes/` | a cluster the control plane runs in. One Job per job in the execution namespace with limits and a deadline, a `restricted` pod with no service-account token, credentials from a Secret that lives as long as the job, and the instance's egress gateway with a token per job (ADR-0115); refuses hosts, and every job from level 3 upwards, where network policies are not enforced (`deploy/k8s/README.md` §7); a unit no node has room for, or one still being created when its health bound passes, is at capacity, and its step waits (ADR-0037 §6, ADR-0145) |

The worker port over the execution port is `adapters/driven/workers/launched.py`: one unit
per assignment, started with the credentials, the hosts and the autonomy level the assignment
carries, and with the hosts the worker's own service needs — its agent's or its model's
provider — which the operator configures per worker and no bundle names
(`TAKTUS_EXECUTION_SERVICE_HOSTS`, ADR-0089). A *probe* — a unit with no credential and no
host — answers `capabilities` once, and the answer is kept. The estimate before every worker
step starts no unit: it is what the estimator the worker declares in its capabilities yields
(`contracts/worker/v1` §5), and a launched worker that declares none has its steps refused for
want of an estimate. No unit starts before admission control has said yes (ADR-0005, ADR-0115).
A unit the adapter killed — memory, wall clock — is a failed step with that cause, never a hang. The same holds for an artifact fetch the kill cut off: the launched worker asks the unit's exit before it reports a failed fetch, so the step names the kill and not the refused connection, and keeps the artifacts fetched before it (#587). A fetch that fails while the unit lives names the connection error.

**The launch convention** is the one thing a unit must know when an adapter starts it: it reads
`TAKTUS_UNIT_PORT` for the port to serve the contract on and `TAKTUS_UNIT_STATE_DIR` for the
directory that outlives the job, and it is told `TAKTUS_UNIT_WALL_SECONDS`, the wall clock the
adapter ends it at: a worker that can stops at a boundary before it, `stopped` without `limit`,
and the run continues the step from its checkpoint in a new unit, at most three times (ADR-0102). Both workers of this repository take them as defaults; a
foreign worker is wrapped by a shell script that translates. Beside them, every unit of a worker
— an assignment's, a probe's, the conformance suite's — receives the variables its program needs
to start, which the operator configures per worker (`TAKTUS_EXECUTION_UNIT_ENV`, ADR-0090): the
coding worker's `CODING_AGENT_AUTH`, for one. They are visible configuration and never a
secret; a name that carries one is refused (`ports/execution.py: variable_refusal`).

**Several workers on one instance** (ADR-0078). `TAKTUS_WORKERS` names them in the order a step
is resolved in: the first whose declared capabilities cover what the step requires serves it.
Each is the adapter `worker.<name>`, with its own kind and the settings it needs, read as
`TAKTUS_WORKER_<NAME>_…` and taken from the instance's `TAKTUS_EXECUTION_*` where it sets none.
Its endpoint and its credentials are its own alone: two workers that reference the same
credential name each receive the value configured for that worker. An instance that names no
workers reads its one worker as before, as `worker.<kind>`. Each worker is withheld by the
removal test and earns its conformance half on its own.

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
internal, whose only other member is the instance's *egress gateway* (ADR-0115). The gateway
joins the job's network for the job's life. It forwards `/units/<unit>/<port>/…` inward so the
control plane can reach the unit, listening for that only on the network it started on. Outward
it is an HTTP proxy that admits exactly the hosts the job's token names — `frame.allowed_hosts`,
and for an assignment the worker's service hosts (ADR-0089) — answers 403 to every other host
and 407 without a token its key signed, and refuses every address on a job's network. A job
without hosts gets no token and reaches nothing (this is where DEC-0008's field becomes a wall).
The token reaches the unit as its proxy variables, in memory, as a credential does. The gateway's
key is `execution.gateway.key`; without one a key is drawn for the process, whose gateway is its
own and is removed when it closes. One named volume per unit for its
state and no other mount, the engine's socket never among them. The adapter speaks the
engine's HTTP API over its socket — Docker or Podman — so that the control plane image needs
no client. Where the gateway publishes its inbound port on the host, the engine
chooses the host port from its own record, which does not see a port another program holds;
a start the engine refuses with `address already in use` is repeated, up to five times, and
the engine chooses again. `tests/adapters/execution/test_container.py` proves every one of these from inside
a job, and `tests/integration/test_launched_container.py` runs a process through it, stops it
at a boundary and resumes it in a new container.

**The cluster adapter's wall** is the same shape in a cluster's terms, specified in
`deploy/k8s/README.md` §4 to §7: a Job instead of a container, a Pod Security level instead of
engine flags, a namespace's default-deny network policy instead of an internal network, and the
same gateway as a Deployment of the chart instead of a container (ADR-0115). It admits the hosts
the job's token names, because a namespace's policy cannot tell one job from another; the token
is in the job's Secret, signed with the key the runner and the gateway share.
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
runs W-01 to W-11 and W-13 to W-20 against a live worker — W-21 too over the outbound binding — and C-01 to C-09 and C-11 against a live connector, and reports
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

**A replay answers every step of a rehearsal from a recorded run (ADR-0108).** A rehearsal of
ADR-0030 answers only an outward operation from a recording, and calls everything else. A replay
goes further: an engine given a replay (`components/run/ports/replay.py`) resolves every
rehearsal from it, so that a connector call of any effect, a wait on a connector, a model call
and a worker step are each answered by the recorded result of the same step in a real run of
the same process. The recording is a directory of data (`adapters/driven/replay`); what a step
sent is kept as digests only, what it received as the run kept it. A step that sends anything
other than its recorded step sent fails, naming the parts that differ. The replay asks the step
boundaries — anchors, a step's own `ask`, the level — and not an adapter's maturity, because its
adapter is the recording. `tools/record_rehearsal.py` writes a recording from a run in an
instance's database; `make rehearse` replays the self-development bundles from theirs. CI runs
it as the lane `rehearse`: on a pull request that touches a bundle, a recording or the core, and
on every commit on `main` (ADR-0096 §1).

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

The maturity record derives *verified* from both halves and names which is missing. A connector
that serves a vendor's MCP server without a manifest of its effects stays *experimental* whatever
it passed, and its configuration names the manifest it serves the server under, so that a
changed manifest is another configuration (ADR-0117). `taktusctl conformance list` prints every
configured adapter with its maturity, until the catalogue of #339 and #348 does. What a
release ships is a list of its own, `src/taktus/composition/shipped.json`: every connector's
declared capabilities and operations, and every worker's `CAPABILITIES`, which each worker
states in its `worker.py`. `make generate` writes it, and a lack is classified against it
(ADR-0118). The
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
W-01..W-21 and C-01..C-11 has a fixture (`tools/validate_contracts.py`).

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
| Worker | `codex` | the second real coding worker; validates the contract against a second vendor. Exists (`workers/codex/`), offers the four capabilities a coding step requires, passes the suite in both authentication modes, faults included, against a stand-in for its agent; tokens per step come from the agent's session file. With both coding workers in one pool, the removal test withholds either and the step is served by the other (`tests/integration/test_two_coding_workers.py`). An instance configures both in `TAKTUS_WORKERS` (#209, ADR-0078), and the removal test says *changed* for each with the other as its alternative. Its image and live run are #208 |
| Connector | `github` | repository: issues, pull requests, pipelines, comments, branches, labels, and one file read at a ref — actions and webhook intake. Exists (`src/taktus/adapters/driven/connectors/github/`), passes the suite against a fake of its service; the example of idempotency: a pull request opened for a step is opened once, proven across a restart of the connector against the fake and, with a credential, against the real service (`tests/adapters/connectors/test_repository_live.py`). Acts as Taktus's own app when configured with the app's identifier and key — the requesting identity behind the name it declares for actions, minting an installation token that lives an hour for its one repository, never stored — and with a token otherwise (ADR-0033); the suite passes in both modes, and against the real service with the scenario it ships, whose pull request comes from the branch its branch write made (#300). A repeated issue create is found at once although the service's issue list lags: the issues above the newest listed number are read one by one (ADR-0024, amendment of 2026-10-12). Reached by the daemon's webhook intake and by the run's connector steps. Reads every secret — the webhook's included — from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, and from the variable only without one (DEC-0130); never acts with its own secrets — the app's key, the webhook secret — when a call names them, and names a transport fault by its type alone, as the chat connector does (#267); on a cluster the chart deploys it beside the roles (`deploy/k8s/README.md` §2). A branch it writes
keeps the mode each file has in the base — an executable a change touches stays executable —
read from the base tree before the new tree is written (DEC-0020). A file entry may carry
`executable`, and the coding worker's changeset sets it on every file its index records as
executable, so a script a change adds arrives executable too; a file the base does not have
and that carries no flag is written as a plain file (issue #28). A branch's base is a branch by
name or a commit by its full sha: P-03 makes its branch from the commit the coding worker's
workspace was cloned from, the changeset's `source`, so that its whole files revert nothing the
base branch gained meanwhile (#496). It creates references besides branches, `repository.refs.create`: up to ten fully qualified names, each on a child commit of a target that carries the key and changes nothing, a name somebody else holds answered `conflict`. What a reference means is the caller's; P-03 reserves the numbers of the records its change adds with it (ADR-0095) |
| Connector | `slack` | the chat service the owner of this tenant uses: both a command channel and a delivery channel, the capability `chat.threads` and the channel `channel.chat`. Exists (`src/taktus/adapters/driven/connectors/slack/`): a thread read, a message posted into a conversation or a thread as a `delivery` that is `marked` by its metadata — posted once across a restart of the connector — and event intake under `hmac-sha256-timestamped`, a delivery signed more than 300 seconds before it arrived refused as a replay (ADR-0024, amendment). Passes the suite against a fake of its service, fault for fault; against the real service when NEED-0018 is provided. Added to an instance by one entry of `TAKTUS_CONNECTORS`, nothing in the core changed (`tests/adapters/connectors/test_chat_channel.py`). The URL check the service makes before it sends events is answered: verified, refused as no event with the challenge as its `answer`, which the HTTP surface returns as it is (ADR-0024, amendment of 2026-10-09; `tests/adapters/rest/test_intake_over_mcp.py`) |
| Connector | `http` | the generic fallback for anything with a documented API |
| Connector | `directory` | the knowledge system of an organisation that has none: the capability `knowledge.pages` over one directory, a Markdown file per page, the mark and the key in the file's last line as a comment a viewer does not show (ADR-0065). Exists (`src/taktus/adapters/driven/connectors/directory/`): a list, a read, and a write that replaces a page only where it holds the expected text, `marked` by the key beside the page. Runs inside the process that uses it, as the loopback connector does; it has no MCP binding and so is not held to the suite. `taktusctl guides publish --to` uses it, and an instance serves it where `TAKTUS_KNOWLEDGE_DIRECTORY` names a directory (ADR-0066). The wiki connector serves the same capability (row below) |
| Connector | `bookstack` | the wiki the guides are read in (UC-13.6, NEED-0021, DEC-0176): the capability `knowledge.pages` against a wiki of shelves, books and pages, a place of three names. Exists (`src/taktus/adapters/driven/connectors/bookstack/`): a list, a read, and a write that replaces a page only where it holds the expected text, `marked` by the key in the page's tags. The mark and the digest of the text written are kept in the tags too, with the digest of the text as the wiki stored it, so that a page nobody touched reads with the digest of what was written although the wiki changed it. Passes the suite against a fake of the wiki, fault for fault; against the real wiki once NEED-0021 is provided. Added to an instance by one entry of `TAKTUS_CONNECTORS`; S-05 then publishes into it, and with it removed into the directory where one is configured (`tests/adapters/connectors/test_guides_wiki.py`) |
| Connector | `mail` | mail over two open standards (ADR-0111, #441): the capability `mail.messages` and the channel `channel.mail`. Exists (`src/taktus/adapters/driven/connectors/mail/`): a message read over IMAP; a message sent over SMTP as a `delivery` that is `marked` by its message identifier, derived from the key and found in the sent folder before sending; a reply on the channel. Its relay reads the inbox and delivers each new message to the intake, signed under `hmac-sha256`; the event identifier is the `Message-ID`, so the same message relayed twice is one event. Passes the suite against a fake mail server, fault for fault (`tests/conformance/test_connector_v1_open_standards.py`); `untested` by the removal test, because no process uses it yet |
| Connector | `prometheus` | metrics by the Prometheus HTTP query API (ADR-0111): the capability `metrics.series`, a series read by a query at one moment or over a range, every value as a number and as the store's text. Both operations `read`; its scenario names no write, and C-05 passes as not applicable. Passes the suite against a fake store, fault for fault; `untested` by the removal test. An OpenTelemetry receiver is not built: ADR-0111 §7 |
| Connector | `httpcheck` | an HTTP check (ADR-0111): the capability `check.http`, one request to a path of a configured service, judged against a declared status, body text and longest duration, reported as `passed` or `failed` with the duration. A service that does not answer is a failed check, not an error. Passes the suite against a fake service, fault for fault; `untested` by the removal test |
| Connector | `aws` | cloud billing (ADR-0150, #447): the capability `billing.costs`, a cloud account's cost per day by service, account or region. Exists (`src/taktus/adapters/driven/connectors/aws/`): every amount the provider's decimal text, each day's total their exact sum, `estimated` where the provider has not closed the day; each request signed with the requesting identity's key pair, `BILLING_KEY`, whose secret half never goes on the wire. `read`; passes the suite against a fake that recomputes every signature, fault for fault |
| Connector | `openai` | a model provider's costs (ADR-0150): the capability `models.costs`, the organisation's cost per day by line item or project, in the shape `billing.costs` has. `read`; passes the suite against a fake of the API, fault for fault |
| Connector | `anthropic` | a model provider's costs (ADR-0150): the capability `models.costs` over the Admin API's cost report, the organisation's cost per day by description or workspace, the report's cents turned into dollars by moving the decimal point. Same shape as `openai`. `read`; passes the suite against a fake of the report, fault for fault |
| Connector | `sentry` | error tracking (ADR-0150): the capability `errors.issues`, the issues of a period and one issue, with their counts and links; no field that names a person. `read`; passes the suite against a fake of the API, fault for fault |
| Connector | `stripe` | a payment provider (ADR-0150): the capability `payments.subscriptions`, the subscriptions of a status and one subscription, with their items and metadata; the customer by identifier only. `payments.customers` is scoped: one customer's subscriptions, refused for another customer under a case's scope (C-11, ADR-0130). A direct connector, not the vendor's own server, because a match held `exact` needs fields, not text (ADR-0150 §3). `read`; passes the suite against a fake of the API, fault for fault |
| Connector | `vendor` | a vendor's own MCP server behind the contract (ADR-0117, #410). Exists (`src/taktus/adapters/driven/connectors/vendor/`): it reaches the vendor's server at the MCP URL its operator names, serves the tools a manifest (`Connector.json#/$defs/Manifest`) declares with their effect and idempotency, `native` or `none`, and sends the requesting identity's credential as a bearer token. Without a manifest it serves only the tools the vendor marks as reading, each a read, and its maturity stays `experimental`. A tool whose effect nobody declared is not served. It hosts no vendor's server. Passes the suite against the MCP project's reference time server, without a manifest and with one, and against a stand-in with tools that write under its manifest, fault for fault (`tests/conformance/test_connector_v1_vendor.py`); `taktusctl conformance list` shows each such connector with its maturity |
| Model | `openai_compatible` | covers Ollama, vLLM and most vendors. Exists (`src/taktus/adapters/driven/models/openai_compatible/`), proven against a fake of the endpoint; the one model `llm` steps ask |
| Model | `anthropic` | native capabilities the common denominator does not carry |
| Connector | `loopback` | Taktus reached by Taktus. Exists (`src/taktus/adapters/driven/connectors/loopback/`): the capabilities `orchestrator.integrations`, `orchestrator.removal`, `orchestrator.maturity` and `orchestrator.conformance` behind the action side of the connector port, every operation `read` because nothing it does leaves the system — except `orchestrator.conformance.run`, which runs a suite and is declared `write` (NTC-0091) — over an `Orchestrator` the composition root implements on the instance's own services (`composition/loopback.py`; ADR-0027). And `orchestrator.guides`, the guides' sources, rendering, measuring, publishing and the report of a hand edit, over the `Guides` of `composition/guides.py` (ADR-0066); its `publish` writes into the knowledge system and is declared `write`, `marked`. And `orchestrator.maturation`, every step's measures and the proposals of method maturation, over the `Maturation` of `composition/maturation.py` (ADR-0086); both operations are `read`, because the training and the trial are runs of their own that record their effects, and a proposal is a decision request. It is what the removal test calls, and what a process calls to have the instance run an adapter's conformance suite; it is never itself an integration the removal test lists. In an installation with several instances the same capabilities can be served over the HTTP surface instead |

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
