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
| `GET` | `/v1/assignments/{id}/artifacts` | list result artifacts |
| `GET` | `/v1/assignments/{id}/artifacts/{artifact_id}` | fetch one artifact's bytes |
| `GET` | `/v1/health` | readiness |

Errors are RFC 9457 problem details. A rejected assignment is not an error; see section 3.

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

Of the four `supports` flags only `native_pause` varies. `step_boundary_signal`, `streaming_events`
and `estimate` are constant `true`: without them sections 4 to 6 cannot be satisfied. They are
declared so that a reader of the response sees the obligation.

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
artifact it produced before it.

**A command after the work.** `task.after` names a command the worker runs once the work is
done, as the assignment's last step, in its workspace: `command` is a program and its arguments,
run without a shell, and `artifact` the `artifact_id` under which its standard output is
published, byte for byte, as `text/plain`. The command is the task's: no model chooses or runs it,
and the worker gives it no credential. A command that exits with anything but 0 fails the
assignment, and the artifact is not produced. A resumed assignment whose checkpoint lies after
that artifact does not run it again. Check W-18 holds a worker to this (ADR-0053).

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
| `step.started` | `step_id`, `kind`, `summary` — `kind` names the class of work in one token: `plan`, `edit`, `test`, `shell`, `epoch` |
| `step.progress` | `step_id`, `message`; optionally `progress: {current, total, unit}` for work measured in units such as epochs |
| `tool.called` | `tool` (a capability), `arguments_digest` (**`sha256:` + hex, never in clear**); `host` when the call reaches a host over the network; `refused: true` with a `reason` when the tool or the host lies outside the frame |
| `decision.made` | `rationale` — why this path |
| `consumption.reported` | `step_id`, and any of `tokens_in` / `tokens_out` / `currency` / `quota_units` / `compute_seconds` with `resource_class` |
| `step.boundary` | `step_id`, `checkpoint_ref` — **a stop may take effect here** |
| `artifact.produced` | `artifact_id`, `kind`, `digest` |
| `assignment.finished` | `outcome`: `succeeded` · `failed` · `stopped` · `rejected`; `checkpoint_ref` when stopped, `reason` when failed or rejected; `limit` — one of `currency`, `quota`, `compute`, `tokens` — when a limit halted the assignment (section 6) |

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

---

## 6. Stopping

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

A step can use more than it was expected to, after it started. That step is not aborted: it
finishes, and the worker halts at the boundary right after it and starts nothing more. The limit
then yields by at most that one step's overrun. No work is lost: the checkpoint is kept, and an
assignment that resumes from it continues. Once the reported running total of a limited quantity
has reached its limit, no further step starts (W-14).

A worker that learns a quantity only at the end of an assignment — money, for some — cannot halt
on it while running. It holds what it learns per step and says in its own documentation which
quantity that is.

---

## 7. Conformance

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
```

| # | Check |
|---|---|
| W-01 | `capabilities` returns valid schema and declares at least one consumption kind |
| W-02 | `estimate` answers even at `confidence: low` |
| W-03 | events carry a gapless `seq`; the stream resumes from `seq` |
| W-04 | `consumption.reported` appears per step, not only at the end |
| W-05 | `step.boundary` appears at least once per assignment |
| W-06 | `stop` takes effect at a step boundary with a checkpoint set |
| W-07 | a tool outside `allowed_tools` is refused, not ignored |
| W-08 | no credential appears in an event, artifact or log |
| W-09 | `tool.called` transmits arguments hashed, never in clear |
| W-10 | exceeding `limits` yields `rejected` **before** starting, not an abort afterwards |
| W-11 | resuming from a checkpoint produces no duplicate artifact |
| W-12 | the adapter passes the removal test: removing it breaks no process |
| W-13 | a host outside `allowed_hosts` is refused, not ignored |
| W-14 | a running total that would cross `limits` halts the assignment at its next step boundary: no step starts once the reported running total of a limited kind has reached its limit, and the assignment ends `stopped` with a checkpoint and names the `limit` |
| W-15 | a worker holding `max_concurrent_assignments` answers one more `POST /v1/assignments` with `503` and a problem body, and records nothing of it |
| W-16 | `GET /v1/assignments/{id}` of an id the worker never received answers `404` with a problem body |
| W-17 | a `POST /v1/assignments` whose id the worker already holds, running or finished, answers `409` with a problem body and starts nothing: the assignment of that id stays the first |
| W-18 | a task's command after the work runs as the last step, after every step of the work; its standard output is the artifact the task names, byte for byte; a command that exits with anything but 0 fails the assignment without that artifact |

The suite runs W-01 to W-11 and W-13 to W-18 against a live worker and reports W-12 as *pending*: the removal test
takes the adapter out of running processes, which a suite talking to one endpoint cannot do, and
which needs processes to exist (DEC-0005). W-14 can only be provoked in a worker whose actual
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
whole stream — W-03 to W-07, W-10, W-11, W-13, W-14, W-18 — use the `Transcript` shape: the assignment, the estimate
the worker gave for it, and every event in order. The stream rules that judge them live in the
suite (`src/taktus/conformance/rules.py`) and are applied to the fixtures by `tests/conformance`
and to a live worker by `uv run taktusctl conformance run`. W-15 concerns no stream: its fixtures
use the `CapacityProbe` shape — the places declared, the assignments held, the answer to one
more — and fail the capacity rule in the same file. W-16 and W-17 concern an assignment's id.
Their fixtures use the `UnknownIdProbe` shape — an id never posted and the answer to its state —
and the `RepeatedIdProbe` shape — the state held, the answer to the repeat, the state after it —
and fail the two id rules there. `tools/validate_contracts.py` checks that
every fixture is schema-valid and that every check has one.

## 8. Two proof cases

The contract must be fully satisfiable by two very different workers. If it is not, the contract is
what needs changing, not the worker.

**Proof case 1 — `script`:** a shell wrapper with no AI at all. Seconds of runtime, no model, no
tokens. If it cannot satisfy the contract, the contract was built around one specific coding agent.

**Proof case 2 — `mlbench`:** a training job. Hours of runtime, a GPU held, progress measured in
epochs rather than tool calls, the result a model artifact with metrics. If it cannot satisfy the
contract, the contract only serves coding — and method maturation
([ADR-0004](../../../docs/adr/ADR-0004-method-selection.md)) would have no path into execution.

Both are part of the conformance suite from `0.1.0`. Both appear in `examples/transcript/valid/`.
