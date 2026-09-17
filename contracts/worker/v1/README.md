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
    "forbidden": ["vcs.push:protected", "net.egress:*"],
    "max_steps": 40,
    "deadline": "2026-09-16T04:00:00Z"
  },
  "limits": {
    "currency": { "eur": 4.0 },
    "quota": { "units": 120 },
    "compute": { "seconds": 7200, "resource_class": "gpu.small" }
  },
  "credentials": [ { "name": "VCS_TOKEN", "injected_as": "env" } ],
  "callback": { "events": "sse" }
}
```

The control plane chooses the `assignment_id`. `context.checkpoint_ref` is present only when the
assignment resumes an earlier one; the worker continues after that checkpoint and produces no
artifact it produced before it.

**Credentials travel as names.** The execution adapter injects the value into the worker's
environment at runtime; the value never passes through this contract, never appears in an event, an
artifact or a log, and is never stored by the worker. A worker that violates this fails conformance.

**Least privilege:** the worker receives only the tools in `allowed_tools`; `forbidden` narrows
further by pattern. `frame` is a ceiling, not a suggestion.

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
| `tool.called` | `tool` (a capability), `arguments_digest` (**`sha256:` + hex, never in clear**); `refused: true` with a `reason` when the tool lies outside the frame |
| `decision.made` | `rationale` — why this path |
| `consumption.reported` | `step_id`, and any of `tokens_in` / `tokens_out` / `currency` / `quota_units` / `compute_seconds` with `resource_class` |
| `step.boundary` | `step_id`, `checkpoint_ref` — **a stop may take effect here** |
| `artifact.produced` | `artifact_id`, `kind`, `digest` |
| `assignment.finished` | `outcome`: `succeeded` · `failed` · `stopped` · `rejected`; `checkpoint_ref` when stopped, `reason` when failed or rejected |

`consumption.reported` comes **per step**, not at the end. A worker that only settles up at the end
makes admission control impossible. `currency` is a map by ISO 4217 code in lowercase,
`{"eur": 0.42}`, the same shape as in `limits`.

`step.boundary` is the most important event in the contract: it is the promise that at most one step
of work can be lost.

A tool outside `allowed_tools`, or matching `forbidden`, is **refused, not ignored**: the worker emits
`tool.called` with `refused: true` and does not execute it. That is how the refusal becomes visible
to the ledger.

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

The suite runs W-01 to W-11 against a live worker and reports W-12 as *pending*: the removal test
takes the adapter out of running processes, which a suite talking to one endpoint cannot do, and
which needs processes to exist (DEC-0005). A passed suite plus a passed removal test is maturity
*verified*. Production processes at autonomy level 3 and above may only use adapters at
*verified* or above.

How to run the suite against a worker of your own, what each check means in plain words and what
a failure tells you to fix: [CONFORMANCE.md](CONFORMANCE.md).

**Fixtures.** `examples/<definition>/valid/` holds what a conforming worker produces;
`examples/<definition>/invalid/W-NN-*.json` holds one violation per check. Checks that concern a
whole stream — W-03 to W-07, W-10, W-11 — use the `Transcript` shape: the assignment, the estimate
the worker gave for it, and every event in order. The stream rules that judge them live in the
suite (`src/taktus/conformance/rules.py`) and are applied to the fixtures by `tests/conformance`
and to a live worker by `uv run taktusctl conformance run`. `tools/validate_contracts.py` checks that
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
