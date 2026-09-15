# Control plane

The core of the product. Exactly this layer is missing from the agent runtimes and CLI orchestrators
available on the market, and it must not depend on any of them.

---

## 1. The one path

```
 Channel         Command          Plan          Process version     Run          Step run
 ───────         ───────          ────          ───────────────     ───          ────────
 CLI    ┐                     ┌ optional ┐
 Web    ├─ normalise ───────▶ │ dialogue │ ──▶ active version ──▶ Run ──▶ Step … Step
 Chat   │   (identity,        │ commission│                        │
 Repo   │    context,         └──────────┘                        ├──▶ Ledger (every step)
 Time   │    reply address)                                       ├──▶ OpenTelemetry
 Event  ┘                                                         ├──▶ Consumption
                                                                  └──▶ Checkpoint + artifacts
```

There is exactly **one** execution path. A chat message, a CLI invocation, a schedule and a webhook
all produce the same object.

---

## 2. Command

The normalised entry. No command is executed without an identity attached.

| Field | Meaning |
|---|---|
| `id` | |
| `channel` | origin channel (a connector reference, never a product name in the core) |
| `identity` | the single authenticated Taktus identity of the sender |
| `org_path` | tenant → department/group → team → project; drives visibility, sharing and cost attribution |
| `intent` | raw text plus recognised intent |
| `context` | channel context (issue, thread, file, previous run) |
| `reply_to` | replies and results go back to **the same channel** |
| `received_at` | |

An unknown sender gets no execution — a question or an offer to register. One channel account never
maps to several identities; one identity may hold many channels. The mapping is audited and
revocable by an administrator.

---

## 3. Plan

Optional, but the norm for anything new. Operator and Taktus develop a plan iteratively: what, with
what, by when, at which autonomy level. **Commissioning is an explicit, recorded act** — no plan
slides into execution through approval fatigue.

The plan is also the authoring tool for processes: it ends either in a one-off run or in a new
process version.

---

## 4. Process

A process is a **directed graph of steps**, not a script and not a prompt.

### 4.1 What a step carries

- **method** — one of `rule`, `statistics`, `ml`, `neural`, `llm`, `worker`, `human`, `wait`
- **reason** for the choice and the **alternatives rejected**
- a **fallback** for any method that can vary
- an **exactness class** — `exact`, `sourced`, `tolerant`, `free` — limiting which methods may
  produce the result; on every step that produces one, never on `wait` or `human` (ADR-0018)

See [methods.md](methods.md). The choice is measured continuously and Taktus proposes changes.

### 4.2 Versioning

Every change creates a new **process version** with author, reason, diff and evaluation result. The
database holds the pointer to the active version; the versions themselves are **bundles**:
definition, prompts, skills, connector *capabilities*, governance rules and value criteria in one
package.

Mirroring to Git is enabled per process. With it on, history, diff, review and rollback are the same
mechanics as for code. With it off, history lives in the database. The bundle is the truth either
way — Git is a projection, not a second source.

---

## 5. Run and step run

### 5.1 Step atomicity

Results are persisted **per step**: checkpoint, artifacts, consumption, events. Three guarantees
follow:

- **No limit is ever breached.** Before each step its demand is estimated (the worker supplies the
  estimate) and checked against what remains. A step starts only if it fits. The guarantee comes
  from *admission*, not from aborting.
- **At most one step of work is lost.** A stop — by limit, emergency stop, user or anchor — takes
  effect at the next step boundary; the running step may finish up to a hard ceiling.
- **Resume and replay.** After approval or a limit change, work continues at the step boundary.
  Because every step is recorded, a run can be replayed afterwards.

Workers with native pause support refine the granularity but are not required: the guarantee is
worker-agnostic.

### 5.2 States

```
planned → admitted → running → [waiting_human] → running → finished
                        │            │
                        │            └─ decision request open (anchor, approval)
                        ├─ halted (limit, emergency stop, user) → resumed
                        ├─ self-healed (retry or correction within frame) → running
                        └─ escalated (frame exceeded) → situation package to a person
```

There are no open loops. Every execution produces a measurable result that flows back into
monitoring and reports. Repeated self-healing of the same fault raises an improvement proposal or a
draft skill — a fault healed three times is a design fault.

---

## 6. Ledger

The complete activity record: what, when, why, with which method, which model, which worker, at what
consumption, with what result. Kept as a **hash chain**, so that tamper-evidence does not depend on
secrecy. Fed from the workers' event streams, exported as OpenTelemetry signals.

The ledger references content, it does not store it: no personal data and no secrets. What it holds
is the chain of actions.

**It is the single source for every metric.** No view and no value ledger computes from a second
source.

---

## 7. Consumption

Every step reports what it used. The raw quantities are measured — tokens, compute seconds, resource
class, step count, storage — and the normalised unit **Takt** is derived from them.

Admission control works against all applicable limits at once: budget in currency, a subscription
window, a provider rate limit, available compute. If the estimate does not fit, the step does not
start, and the block is recorded with cause and duration in the blocked-time account
([throughput.md](throughput.md)).

Whether a model purpose is served by a subscription, an API key or local hardware is tenant
configuration, not part of a process definition. See [accounting.md](accounting.md).

---

## 8. Telemetry from day one

Every control-plane event and every worker event stream is emitted as an OpenTelemetry signal. That
is the data basis for the ledger, the views, the value ledger and BI export — and the reason an
external observability platform stays optional and never becomes a prerequisite.
