# Worker contract v1

An execution unit — coding agent, agent runtime, script runner, training job — is connected through
this contract. **Workers execute. They do not decide.**

Transport: HTTP for control, Server-Sent Events for the event stream, JSON Schema as the definition.
Rationale: [ADR-0007](../../../docs/adr/ADR-0007-worker-contract.md).

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
| `GET` | `/v1/assignments/{id}/artifacts` | collect result artifacts |
| `GET` | `/v1/health` | readiness |

---

## 2. Capabilities

Processes reference workers **by capability only**, never by product name. Mapping a capability to a
concrete adapter is configuration.

```json
{
  "contract": "worker/v1",
  "capabilities": [
    "code.edit", "code.test", "vcs.branch", "vcs.pullrequest",
    "workspace.isolated", "shell.sandboxed"
  ],
  "consumption": {
    "kinds": ["quota"],
    "window_seconds": 18000,
    "unit": "session-units"
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

`consumption.kinds` is any of `currency`, `quota`, `compute`. A subscription-backed worker reports
`quota` and describes its window; a training worker reports `compute` with a resource class. The
control plane converts none of it into money — it derives the normalised **Takt**
(`docs/architecture/accounting.md`). An exhausted window is not *more expensive*, it *blocks*, and
that is a different state.

---

## 3. Assignment

```json
{
  "assignment_id": "asg_01J...",
  "task": { "goal": "…", "acceptance": ["…"], "inputs": {} },
  "context": { "workspace": { "kind": "git", "ref": "…" }, "documents": [] },
  "frame": {
    "autonomy_level": 3,
    "allowed_tools": ["code.edit", "code.test", "vcs.branch"],
    "forbidden": ["vcs.push:protected", "net.egress:*"],
    "max_steps": 40,
    "deadline": "2026-09-16T04:00:00Z"
  },
  "limits": { "currency": { "eur": 4.0 }, "quota": { "units": 120 }, "compute": { "gpu_seconds": 7200 } },
  "credentials": [ { "name": "GH_TOKEN", "injected_as": "env" } ],
  "callback": { "events": "sse" }
}
```

**Credentials are injected at runtime and never stored by the worker.** No credential appears in an
event, an artifact or a log. A worker that violates this fails conformance.

**Least privilege:** the worker receives only the tools in `allowed_tools`. `frame` is a ceiling, not
a suggestion.

---

## 4. Events

Each event carries `assignment_id`, `seq`, `ts`, `type`. The stream is resumable from `seq`.

| Type | Required content |
|---|---|
| `step.started` | `step_id`, `kind`, `summary` |
| `step.progress` | `step_id`, `message` |
| `tool.called` | `tool`, `arguments_digest` (**hashed, never in clear**) |
| `decision.made` | `rationale` — why this path |
| `consumption.reported` | `step_id`, and any of `tokens_in`/`tokens_out`/`cost_eur`/`quota_units`/`compute_seconds` with `resource_class` |
| `step.boundary` | `step_id`, `checkpoint_ref` — **a stop may take effect here** |
| `artifact.produced` | `artifact_id`, `kind`, `digest` |
| `assignment.finished` | `outcome`: `succeeded` · `failed` · `stopped` · `rejected` |

`consumption.reported` comes **per step**, not at the end. A worker that only settles up at the end
makes admission control impossible.

`step.boundary` is the most important event in the contract: it is the promise that at most one step
of work can be lost.

---

## 5. Estimation

```json
POST /v1/estimate
→ { "confidence": "low|medium|high",
    "tokens_in": 40000, "tokens_out": 12000,
    "cost_eur": 3.2, "quota_units": 90, "compute_seconds": 5400,
    "resource_class": "gpu.small",
    "wall_seconds": 600, "steps": 12 }
```

An estimate may be rough. It must exist. Without it there is no admission control and therefore no
limit guarantee. `confidence: "low"` is a valid answer; a missing endpoint is not.

---

## 6. Stopping

`POST /stop` requests a stop at the **next** step boundary. The running step may finish up to a hard
ceiling. The worker emits `step.boundary`, then `assignment.finished` with `outcome: "stopped"` and a
checkpoint to resume from.

A worker that aborts immediately and discards the running step violates the contract.

---

## 7. Conformance

```
taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
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

A passed suite plus a passed removal test is maturity *verified*. Production processes at autonomy
level 3 and above may only use adapters at *verified* or above.

---

## 8. Two proof cases

The contract must be fully satisfiable by two very different workers. If it is not, the contract is
what needs changing, not the worker.

**Proof case 1 — `script`:** a shell wrapper with no AI at all. Seconds of runtime, no model, no
tokens. If it cannot satisfy the contract, the contract was built around one specific coding agent.

**Proof case 2 — `mlbench`:** a training job. Hours of runtime, a GPU held, progress measured in
epochs rather than tool calls, the result a model artifact with metrics. If it cannot satisfy the
contract, the contract only serves coding — and method maturation
([ADR-0004](../../../docs/adr/ADR-0004-method-selection.md)) would have no path into execution.

Both are part of the conformance suite from `0.1.0`.
