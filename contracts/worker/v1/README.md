# Worker contract v1

An execution unit — coding agent, agent runtime, script runner, training job — is connected through
this contract. **Workers execute. They do not decide.**

Transport: HTTP for control, Server-Sent Events for the event stream, JSON Schema as the definition.
Rationale: [ADR-0007](../../../docs/adr/ADR-0007-worker-contract.md).

| File | Contents |
|---|---|
| [`Worker.json`](Worker.json) | every body and every event, as JSON Schema 2020-12; shared concepts are referenced from [`contracts/shared/v1`](../../shared/v1) |
| [`openapi.yaml`](openapi.yaml) | the endpoints, with every body referencing the schema |
| [`examples/`](examples/) | valid examples per definition and the must-fail fixtures for the conformance checks below |

Where this text and the schema disagree, the schema is the finding and this text is corrected.
`make gate-contracts` checks the schema and every example.

---

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/capabilities` | what this worker can do |
| `POST` | `/v1/estimate` | estimate demand before starting |
| `POST` | `/v1/assignments` | accept an assignment |
| `GET` | `/v1/assignments/{id}/events` | event stream (SSE, resumable) |
| `GET` | `/v1/assignments/{id}` | current state |
| `POST` | `/v1/assignments/{id}/stop` | request a stop at the next step boundary |
| `POST` | `/v1/assignments/{id}/messages` | send a message, received at the next step boundary (only with `supports.steering`) |
| `POST` | `/v1/assignments/{id}/handover` | hand the assignment over at the next step boundary (only with `supports.handover`) |
| `GET` | `/v1/assignments/{id}/artifacts` | list result artifacts |
| `GET` | `/v1/assignments/{id}/artifacts/{artifact_id}` | fetch one artifact's bytes |
| `GET` | `/v1/health` | readiness |

Errors are RFC 9457 problem details. A rejected assignment is not an error; see section 3.

A worker is reached at its endpoint, or it connects to the control plane and fetches the same
requests from there: the outbound binding of section 8.

---

## 2. Capabilities

Processes reference workers **by capability only**, never by product name. Mapping a capability to a
concrete adapter is configuration.

```json
{
  "contract": "worker/v1",
  "version": "2.3.0",
  "capabilities": [
    "code.edit", "code.test", "vcs.branch", "vcs.pullrequest",
    "workspace.isolated", "shell.sandboxed"
  ],
  "consumption": {
    "kinds": ["quota", "currency"],
    "window_seconds": 18000,
    "unit": "session-units",
    "currencies": ["eur"]
  },
  "supports": {
    "native_pause": false,
    "step_boundary_signal": true,
    "streaming_events": true,
    "estimate": true
  },
  "max_concurrent_assignments": 2
}
```

`version` is optional: the worker's own version, as it names it. Where a worker declares one,
the control plane records it in the provenance of every result the worker produces
(`contracts/shared/v1/Provenance.json`, ADR-0021), so that a result can later be traced to the
worker version that made it.

`consumption.kinds` is any of `currency`, `quota`, `compute`. Each kind brings its own detail:
`quota` needs `window_seconds` and `unit`, `compute` needs `resource_classes`, `currency` needs
`currencies`. A subscription-backed worker reports `quota` and describes its window; a training
worker reports `compute` with its resource classes. The control plane converts none of it into money
— it derives the normalised **Takt** (`docs/architecture/accounting.md`). An exhausted window is not
*more expensive*, it *blocks*, and that is a different state.

`max_concurrent_assignments` is how many assignments the worker holds at once. A worker that
holds that many answers a further `POST /v1/assignments` with `503` and a problem body, and
records nothing (`openapi.yaml`). The control plane relies on that answer: the step waits and
asks again later, and nothing on the control plane's side counts the worker's assignments
(ADR-0037). Check W-15 holds as many assignments as the worker declares and expects that answer
to one more.

Of the four required `supports` flags only `native_pause` varies. `step_boundary_signal`,
`streaming_events` and `estimate` are constant `true`: without them sections 4 to 6 cannot be
satisfied. They are declared so that a reader of the response sees the obligation. Two more are
optional: `steering` and `handover` say that the worker offers what section 6 describes under
those names. Absent, they mean `false` (ADR-0139).

---

## 3. Assignment

```json
{
  "assignment_id": "asg_01J8R3K5Q2N7VX9M4T6B0DPHWE",
  "task": { "goal": "…", "acceptance": ["…"], "inputs": {} },
  "context": {
    "workspace": { "kind": "git", "ref": "main", "location": "/workspace/repo" },
    "documents": [],
    "checkpoint_ref": "…"
  },
  "frame": {
    "autonomy_level": 3,
    "allowed_tools": ["code.edit", "code.test", "vcs.branch"],
    "allowed_hosts": ["repo.example"],
    "max_steps": 40,
    "deadline": "2026-09-16T04:00:00Z"
  },
  "limits": {
    "currency": { "eur": 4.0 },
    "quota": { "units": 120 },
    "compute": { "seconds": 7200, "resource_class": "gpu.small" },
    "tokens": { "in": 260000, "out": 8000 }
  },
  "credentials": [ { "name": "VCS_TOKEN", "injected_as": "env" } ],
  "callback": { "events": "sse" }
}
```

The control plane chooses the `assignment_id`. It records the id before it posts the
assignment, and may post the same id again when it does not know whether the first post arrived.
A worker therefore answers an id it already holds with `409` and takes nothing new, and the
state of an id it does not hold with `404` (`openapi.yaml`). Checks W-17 and W-16 hold a
worker to these two answers. An assignment the worker accepted keeps running when the client
that posted it goes away; whoever holds the id may read its
stream from any `seq` and stop it (ADR-0038). `context.checkpoint_ref` is present only when the
assignment resumes an earlier one; the worker continues after that checkpoint and produces no
artifact it produced before it. `context.handover` is present only when the assignment continues
one that was handed over (section 6); it never comes with `checkpoint_ref`.

**A command after the work.** `task.after` names a command the worker runs once the work is
done, as the assignment's last step, in its workspace: `command` is a program and its arguments,
run without a shell, and `artifact` the `artifact_id` under which its standard output is
published, byte for byte, as `text/plain`. The command is the task's: no model chooses or runs it,
and the worker gives it no credential. A command that exits with anything but 0 fails the
assignment, and the artifact is not produced. A resumed assignment whose checkpoint lies after
that artifact does not run it again. Check W-18 holds a worker to this (ADR-0053).

**A command before the work.** `task.before` names a command the worker runs in its prepared
workspace before the work starts, as the assignment's first step: what makes the workspace able
to run its own checks, such as installing a project's dependencies. `command` is a program and
its arguments, run without a shell and given no credential, and `artifact` the `artifact_id`
under which what it wrote to its standard output and its error output is published, as
`text/plain`, whether it succeeded or not. A command that exits with anything but 0 fails the
assignment, and the work does not start. What the command leaves in the workspace is part of
the workspace the work starts from, not part of the work's change. It reaches the network as
far as the frame's `allowed_hosts` reach and no further: the hosts it needs are hosts of the
frame. A resumed assignment that continues in the workspace it left does not run it again.
Check W-18 holds a worker to this as well (ADR-0100).

**Credentials travel as names.** The execution adapter injects the value into the worker's
environment at runtime; the value never passes through this contract, never appears in an event, an
artifact or a log, and is never stored by the worker. A worker that violates this fails conformance.

**Least privilege, in the affirmative:** the worker receives only the tools in `allowed_tools`
and reaches only the hosts in `allowed_hosts`. Both are explicit lists; there is no pattern and
no "everything but". An absent or empty `allowed_hosts` means no outbound access at all, which
is the right default for most work: an assignment that needs a host names it. The execution
environment enforces the same list at the network — a proxy that admits exactly these hosts —
and this field is what it is given. `frame` is a ceiling, not a suggestion.

**Limits are the worker's hard ceiling.** The control plane sets `limits` to what it reserved for
this assignment. Each kind is optional, and at least one is present. `currency` is a map by ISO
4217 code, `quota` is units of the declared window, `compute` is seconds in a resource class.
`tokens` bounds language-model tokens: `in` and `out` are the same quantities as `tokens_in` and
`tokens_out` in `consumption.reported`, and at least one of the two is present. A worker that
does not consume a kind it is given a limit for has nothing to hold against it.

The limits are held at two points. Before the first step, the estimate is held against them
(*Rejection*, below). While the assignment runs, the running total is held against them: section
6 says how.

**Rejection.** If the estimate does not fit `limits`, or the frame cannot be honoured, the worker
does not start. The response to `POST /v1/assignments` is the assignment state with `status:
"finished"` and `outcome: "rejected"`, and the stream carries exactly one event —
`assignment.finished` with the same outcome and a reason. Rejection is a state, not an HTTP error,
so that the ledger sees it through the same stream as everything else.

---

## 4. Events

Each event carries `assignment_id`, `seq`, `ts`, `type`. `seq` starts at 1 and increases by exactly
1. On the wire the SSE `id` field carries `seq`, the SSE `event` field carries `type`, and the SSE
`data` field carries the event as one line of JSON. A client resumes by sending the last `seq` it
has seen — in the standard `Last-Event-ID` header or as the `after` query parameter — and receives
everything after it. A worker honours both.

| Type | Required content |
|---|---|
| `reach.stated` | `tools` — every capability a call of this assignment can be made under; optionally `hosts` — every host a call can name. Optional, at most once, before the first `step.started` |
| `step.started` | `step_id`, `kind`, `summary` — `kind` names the class of work in one token: `plan`, `edit`, `test`, `shell`, `epoch` |
| `step.progress` | `step_id`, `message`; optionally `progress: {current, total, unit}` for work measured in units such as epochs |
| `tool.called` | `tool` (a capability), `arguments_digest` (**`sha256:` + hex, never in clear**); `host` when the call reaches a host over the network; `refused: true` with a `reason` when the tool or the host lies outside the frame; optionally `effect` — `local` or `outward` |
| `model.called` | `step_id` — one answer of a language model the worker received inside the step. Optional |
| `message.received` | `message_id`, optionally `step_id` — a steering message received at that step's boundary (section 6) |
| `decision.made` | `rationale` — why this path |
| `consumption.reported` | `step_id`, and any of `tokens_in` / `tokens_out` / `currency` / `quota_units` / `compute_seconds` with `resource_class` |
| `step.boundary` | `step_id`, `checkpoint_ref` — **a stop may take effect here** |
| `artifact.produced` | `artifact_id`, `kind`, `digest` |
| `assignment.finished` | `outcome`: `succeeded` · `failed` · `stopped` · `rejected`; `checkpoint_ref` when stopped, `reason` when failed or rejected; `limit` — one of `currency`, `quota`, `compute`, `tokens` — when a limit halted the assignment (section 6); `handover` — the `handover.state` artifact — when the assignment was handed over (section 6) |

`consumption.reported` comes **per step**, not at the end. A worker that only settles up at the end
makes admission control impossible. `currency` is a map by ISO 4217 code in lowercase,
`{"eur": 0.42}`, the same shape as in `limits`.

`step.boundary` is the most important event in the contract: it is the promise that at most one step
of work can be lost.

A tool outside `allowed_tools` is **refused, not ignored**: the worker emits `tool.called` with
`refused: true` and does not execute it. A host outside `allowed_hosts` is refused the same way:
`tool.called` names the `host`, carries `refused: true`, and the host is not reached. That is how
a refusal becomes visible to the ledger — and how a worker that ignores an empty list is caught,
because reaching a host without naming it is not an option the contract offers.

**A worker may state what it put within reach.** A worker that does not offer its work every
tool — a coding agent given only the frame's tools — cannot refuse a call that is never made.
It says so instead: once, before the first `step.started`, it emits `reach.stated`. `tools`
names every capability a call of this assignment can be made under, refused or not. `hosts`,
when present, names every host a call can name; when absent, the worker bounds the hosts only
at the moment of a call. A capability or a host the statement leaves out cannot be called or
reached at all, so no `tool.called` names one, not even a refused one. The statement is
optional: a worker that offers every tool and refuses at the call states nothing. A tool or a
host the frame does not allow, left out of the statement and called nowhere, is how checks
W-07 and W-13 see a frame enforced by not offering. The suite cannot see a statement that is
false about a call never made (ADR-0098).

**A call may say what it acts on.** `effect: "local"` says that the call changes nothing outside
the assignment's workspace: a read, an edit of the workspace's files, a test run. `effect:
"outward"` says that it changes something outside, such as a record written or a message
delivered. A call without `effect` says nothing about it. `model.called` reports each answer of a
language model the worker received inside a step. Both are optional, and both are the worker's
own statements. With them the control plane can count a worker's outward calls and its model
answers without a tool call between them, as it counts its own (ADR-0132, ADR-0139 §5).

---

## 5. Estimation

The request body is the assignment without `credentials` and `callback`; an estimate needs no secret.

```json
POST /v1/estimate
→ { "confidence": "low|medium|high",
    "tokens_in": 40000, "tokens_out": 12000,
    "currency": { "eur": 3.2 }, "quota_units": 90,
    "compute_seconds": 5400, "resource_class": "gpu.small",
    "wall_seconds": 600, "steps": 12 }
```

An estimate may be rough. It must exist. Without it there is no admission control and therefore no
limit guarantee. `confidence: "low"` is a valid answer; a missing endpoint is not. `confidence`,
`wall_seconds` and `steps` are always present; the quantities are those the worker's consumption
kinds cover. A shell script with no model and no tokens still answers.

**An estimator, declared.** A worker may also say in its capabilities how its estimate follows
from the request, as `estimator`, so that the control plane can estimate an assignment without
asking it (ADR-0115). There are two kinds:

- `fixed`: every assignment is estimated as the `estimate` it names;
- `per_item`: `each` once for every item of the list `task.inputs[input]`, and `otherwise` where
  the task carries no such list or an empty one. Every quantity, `wall_seconds` and `steps` are
  multiplied by the number of items.

```json
"estimator": { "kind": "per_item", "input": "commands",
               "each":      { "confidence": "low", "compute_seconds": 0.3,
                              "resource_class": "cpu.small", "wall_seconds": 1, "steps": 1 },
               "otherwise": { "confidence": "low", "compute_seconds": 1.2,
                              "resource_class": "cpu.small", "wall_seconds": 2, "steps": 4 } }
```

A worker the control plane starts per job is estimated by its estimator alone: asking it would
start a unit before admission has said yes. Such a worker that declares no estimator has its steps
refused for want of an estimate. A worker reached at an endpoint is still asked here. Whatever an
estimator yields for a request is never below what the worker answers here for the same request,
in any quantity it names (W-02): the worker holds its own estimate against its limits (W-10), and
an assignment admitted at a lower estimate would be rejected.

---

## 6. Stopping, steering and handing over

`POST /stop` requests a stop at the **next** step boundary. The running step may finish up to a hard
ceiling — `ceiling_seconds` in the request, or the worker's own. The worker emits `step.boundary`,
then `assignment.finished` with `outcome: "stopped"` and the same `checkpoint_ref` to resume from.

A worker that aborts immediately and discards the running step violates the contract.

**A limit stops the assignment the same way.** A *running total* is what the worker has reported
in `consumption.reported` so far in this assignment, per quantity. Before the worker starts a
step, it adds that step's own expected demand to the running total. If the sum would exceed a
limit, the step does not start. The worker ends the assignment at the boundary it is at:
`assignment.finished` with `outcome: "stopped"`, that boundary's `checkpoint_ref`, and `limit`
naming the kind whose ceiling halted it. A stop requested through `POST /stop` carries no
`limit`.

**A worker may also stop on its own before its unit's wall clock.** An execution adapter tells a
launched unit the wall clock it ends it at, in `TAKTUS_UNIT_WALL_SECONDS`. A worker that can stop
at a boundary may do so shortly before that clock: `stopped`, the boundary's `checkpoint_ref`, a
`reason` that says so, and no `limit`, since the clock is no ceiling of the assignment's limits.
The run continues the step from that checkpoint with a new assignment (ADR-0102). A worker that
ignores the variable is ended at the clock as before.

A step can use more than it was expected to, after it started. That step is not aborted: it
finishes, and the worker halts at the boundary right after it and starts nothing more. The limit
then yields by at most that one step's overrun. No work is lost: the checkpoint is kept, and an
assignment that resumes from it continues. Once the reported running total of a limited quantity
has reached its limit, no further step starts (W-14).

A worker that learns a quantity only at the end of an assignment — money, for some — cannot halt
on it while running. It holds what it learns per step and says in its own documentation which
quantity that is.

**Steering: a message received at a boundary.** A worker that declares `supports.steering`
accepts `POST /v1/assignments/{id}/messages` while the assignment runs:

```json
{ "message_id": "msg_01J8R6V2D9", "text": "Use the second endpoint; the first one is retired." }
```

It answers `202` with the assignment's state. A message whose `message_id` it holds already is
answered `202` again and received once: the control plane may post a message again when it does
not know whether the first post arrived. A finished assignment answers `409`, an unknown one
`404`, both with a problem body.

At the next step boundary the worker emits `message.received` with the `message_id`, once. The
running step finishes with the inputs it started with: a message is never received inside a
step. The steps after that boundary have the message as an input of their work. A message
accepted after the last step's boundary is received before `assignment.finished`, and no step
has it.

A message is an input like the task's inputs, and nothing more. It cannot widen
`allowed_tools` or `allowed_hosts`, raise a limit, add a step beyond `max_steps` or move the
deadline. A call it prompts outside the frame is refused as any other is (W-07, W-13). What a
person may send, and how the message is recorded, is the control plane's (ADR-0139 §3).

A worker that does not declare `steering` answers a message with a problem — any status of 400
or above — and changes nothing: no `message.received`, and the assignment runs on. Check W-19
holds a worker to both.

**Handover: a stop that leaves a document to continue from.** A worker that declares
`supports.handover` accepts `POST /v1/assignments/{id}/handover`, with a body of the shape
`HandoverRequest` — `reason` and `ceiling_seconds`, as for a stop. It answers `202` with the
state, `stopping`; an assignment that has finished already is answered `202` with its final
state, as for a stop, and is not handed over. At the next step boundary it stops as for a stop. After `step.boundary` it
produces one artifact of kind `handover.state`, as `application/json`, whose bytes are a
document of the shape `Handover`. Then it emits `assignment.finished` with `outcome: "stopped"`,
the boundary's `checkpoint_ref`, and `handover` naming the artifact.

```json
{
  "contract": "worker/v1",
  "assignment_id": "asg_01J8R3K5Q2N7VX9M4T6B0DPHWE",
  "checkpoint_ref": "ckpt/asg_01J8R3K5Q2N7VX9M4T6B0DPHWE/prepare",
  "task": { "goal": "…", "acceptance": ["…"] },
  "summary": "2 of 4 steps done: inspect, prepare. Remaining: run, report.",
  "steps": [ { "step_id": "inspect", "kind": "shell", "summary": "inspect the host" }, … ],
  "artifacts": [ { "id": "plan", "kind": "plan", "digest": "sha256:…" } ],
  "messages": [],
  "resume": { "plan": ["inspect", "prepare", "run", "report"], "next": 2 }
}
```

The document stands on its own. `summary`, `steps` and `artifacts` are for a person, who can
continue the work from them; what the work changed in its workspace is among the artifacts.
`resume` is the worker's own. A worker of the same kind continues from it without anything the
first instance kept: its state directory, its memory, its checkpoint store.

A new assignment whose `context.handover` carries the document continues the work, at the same
worker or at another instance of it. It repeats no step the document lists in `steps`, and it
produces no artifact the document lists in `artifacts`. A worker that cannot hand its workspace
over does not declare `handover`.

A worker that does not declare `handover` answers the request with a problem — any status of
400 or above — and the assignment runs on. Check W-20 holds a worker to all of this.

---

## 7. Conformance

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
```

| # | Check |
|---|---|
| W-01 | `capabilities` returns valid schema and declares at least one consumption kind |
| W-02 | `estimate` answers even at `confidence: low`; a declared estimator yields no less |
| W-03 | events carry a gapless `seq`; the stream resumes from `seq` |
| W-04 | `consumption.reported` appears per step, not only at the end |
| W-05 | `step.boundary` appears at least once per assignment |
| W-06 | `stop` takes effect at a step boundary with a checkpoint set |
| W-07 | a tool outside `allowed_tools` is refused, not ignored — or, where the worker states its reach, left out of `reach.stated` and never called; a call outside the statement fails |
| W-08 | no credential appears in an event, artifact or log |
| W-09 | `tool.called` transmits arguments hashed, never in clear |
| W-10 | exceeding `limits` yields `rejected` **before** starting, not an abort afterwards |
| W-11 | resuming from a checkpoint produces no duplicate artifact |
| W-12 | the adapter passes the removal test: removing it breaks no process |
| W-13 | a host outside `allowed_hosts` is refused, not ignored — or, where `reach.stated` names hosts, left out of them and never named by a call; a call that names another fails |
| W-14 | a running total that would cross `limits` halts the assignment at its next step boundary: no step starts once the reported running total of a limited kind has reached its limit, and the assignment ends `stopped` with a checkpoint and names the `limit` |
| W-15 | a worker holding `max_concurrent_assignments` answers one more `POST /v1/assignments` with `503` and a problem body, and records nothing of it |
| W-16 | `GET /v1/assignments/{id}` of an id the worker never received answers `404` with a problem body |
| W-17 | a `POST /v1/assignments` whose id the worker already holds, running or finished, answers `409` with a problem body and starts nothing: the assignment of that id stays the first |
| W-18 | a task's command after the work runs as the last step, after every step of the work; its standard output is the artifact the task names, byte for byte; a command that exits with anything but 0 fails the assignment without that artifact. A task's command before the work runs as the first step, before every step of the work; its output is the artifact the task names; a command that exits with anything but 0 fails the assignment, and no step of the work starts |
| W-19 | a worker that declares `steering` answers a message `202`, a repeat of it `202` again, and emits `message.received` for it exactly once, after it was accepted, at a step boundary and never inside a step; a worker that does not declare it refuses the message and emits nothing for it |
| W-20 | a worker that declares `handover` ends a handed-over assignment `stopped` at a boundary, with one `handover.state` artifact after that boundary whose bytes validate as `Handover` and name the assignment and the checkpoint, and `handover` naming it; an assignment that continues from the document repeats no step and no artifact it lists; a worker that does not declare it refuses the request and the assignment runs on |
| W-21 | over the outbound binding, every relayed request is answered exactly once, under its `request_id`, with a `Relay-Status` |

The suite runs W-01 to W-11 and W-13 to W-20 against a live worker and reports W-12 as *pending*: the removal test
takes the adapter out of running processes, which a suite talking to one endpoint cannot do, and
which needs processes to exist (DEC-0005). It runs W-21 when it serves the outbound binding itself
(`--listen`, section 8), and reports it *pending* when it calls an endpoint. W-14 can only be provoked in a worker whose actual
consumption exceeds its own estimate: a limit the estimate fits is otherwise never crossed, and
the suite reports W-14 *inconclusive* with the numbers. W-15 can only be provoked while
the assignments it holds still run, and the suite fills at most sixteen places; otherwise the
suite reports W-15 *inconclusive*, with what to do. A passed suite plus a passed removal test is maturity
*verified*. Production processes at autonomy level 3 and above may only use adapters at
*verified* or above.

How to run the suite against a worker of your own, what each check means in plain words and what
a failure tells you to fix: [CONFORMANCE.md](CONFORMANCE.md).

**Fixtures.** `examples/<definition>/valid/` holds what a conforming worker produces;
`examples/<definition>/invalid/W-NN-*.json` holds one violation per check. Checks that concern a
whole stream — W-03 to W-07, W-10, W-11, W-13, W-14, W-18 to W-20 — use the `Transcript` shape: the assignment, the estimate
the worker gave for it, every event in order, the messages posted and whether a handover was
requested. The stream rules that judge them live in the
suite (`src/taktus/conformance/rules.py`) and are applied to the fixtures by `tests/conformance`
and to a live worker by `uv run taktusctl conformance run`. W-15 concerns no stream: its fixtures
use the `CapacityProbe` shape — the places declared, the assignments held, the answer to one
more — and fail the capacity rule in the same file. W-16 and W-17 concern an assignment's id.
Their fixtures use the `UnknownIdProbe` shape — an id never posted and the answer to its state —
and the `RepeatedIdProbe` shape — the state held, the answer to the repeat, the state after it —
and fail the two id rules there. W-21 concerns the binding: its fixtures use the `RelayProbe`
shape — the requests relayed and every answer posted — and fail the binding rule.
`tools/validate_contracts.py` checks that every fixture is schema-valid and that every check has
one.

## 8. The outbound binding

A worker in a network that admits no inbound connection cannot be reached at an endpoint. It
connects to the control plane instead and fetches the same requests from there. The binding
carries the messages of sections 1 to 6 unchanged, the other way round (ADR-0139 §2).

The worker is given a *base*, an HTTP address of the control plane, and opens no port:

| Method | Path at the base | Purpose |
|---|---|---|
| `POST` | `/next` | the next request for this worker: `200` with a `RelayRequest`, or `204` when none arrived within the host's wait of at most 30 seconds |
| `POST` | `/answers/{request_id}` | the answer to one request: the header `Relay-Status` carries its status code, `Content-Type` its type, and the body is the answer's body. `204`; `404` for a request never relayed; `409` for one answered already |

```json
{ "request_id": "rly_7f3a9c21", "method": "GET",
  "path": "/v1/assignments/asg_01J8R3K5Q2N7VX9M4T6B0DPHWE/events?after=12",
  "headers": { "Accept": "text/event-stream" } }
```

The worker handles each request exactly as if it had arrived at its endpoint, and answers it
exactly once. Its answer to `GET /v1/assignments/{id}/events` is the stream itself: the worker
posts it in chunks while it lasts, and the host reads each event as it arrives. A worker asks
for the next request while it answers others, so that a stream does not hold the rest back.
Every rule of sections 1 to 6 holds across the binding, and the suite runs whole over it:

```
uv run taktusctl conformance run --contract worker/v1 --listen 127.0.0.1:9100
```

The suite then serves the binding at `http://127.0.0.1:9100/relay` and waits for the worker to
connect. Check W-21 holds the worker to the binding itself. The binding names no
authentication of its own yet: a host of the control plane decides it when it is built (#625).

## 9. Two proof cases

The contract must be fully satisfiable by two very different workers. If it is not, the contract is
what needs changing, not the worker.

**Proof case 1 — `script`:** a shell wrapper with no AI at all. Seconds of runtime, no model, no
tokens. If it cannot satisfy the contract, the contract was built around one specific coding agent.

**Proof case 2 — `mlbench`:** a training job. Hours of runtime, a GPU held, progress measured in
epochs rather than tool calls, the result a model artifact with metrics. If it cannot satisfy the
contract, the contract only serves coding — and method maturation
([ADR-0004](../../../docs/adr/ADR-0004-method-selection.md)) would have no path into execution.

Both are part of the conformance suite from `0.1.0`. Both appear in `examples/transcript/valid/`.
