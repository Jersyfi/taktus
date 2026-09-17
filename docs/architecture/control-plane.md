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

Until the bundle format exists (`0.3.0`), a bundle is this process version written as YAML, with
one addition per step — `work`, what the step does when it runs — carried as data and interpreted
by the run. `examples/README.md` is the reference for that shape.

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

In code, `src/taktus/components/run/` does exactly this around every step, whatever its method:
estimate, admit against what remains of the run's budget, run, persist checkpoint, artifacts and
raw consumption, then honour a pending stop at the boundary. A step rejected by admission control
halts the run with cause `limit`; a raised budget on resume lets it continue. A worker step
stopped mid-way ends with the worker's checkpoint, and the resumed assignment starts from it.

Every state change is one transaction with the ledger entry that describes it: the run as it
now is and the entry land together or not at all. A worker's own step boundaries are persisted
as they arrive, so that the boundary a run resumes from can lie inside a worker step.

**Restart.** An instance that stops without a chance to halt its runs — killed, crashed,
powered off — leaves each of them marked as running, with one step in flight. Resuming such a
run *recovers* it: the step in flight goes back to its last persisted boundary (the worker's
checkpoint if one arrived, its start otherwise), is admitted again, and the run continues;
the steps before it are kept as they are. That is ADR-0013 A made true, and
`tests/integration/test_restart.py` proves it by killing the process. Whoever resumes a running
run asserts that no instance is executing it; today that is the operator's explicit act
(`taktusctl run --resume`), and the daemon's lease on a run will make the check automatic.

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
is the chain of actions. The hash rule — what is hashed, in which form — is stated in one place,
`src/taktus/components/ledger/__init__.py`, so that anyone can recompute a chain from its entries.
What a component may tell the ledger is a *fact* (`src/taktus/ports/ledger.py`): identifiers,
method, adapter, measured consumption, an outcome token, a content digest. Never text. A reason
for a halt stays on the run; the ledger carries the cause as a token.

**It is the single source for every metric.** No view and no value ledger computes from a second
source.

In the database the ledger is append-only by construction, not only by convention: the
application role may insert and read, and a trigger rejects every update, delete and truncate
for everyone but a superuser (`migrations/`). A hash chain whose rows can be edited proves
nothing.

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

---

## 9. Tenants and instances

Two boundaries that are easy to confuse, kept apart by ADR-0020.

A **tenant** separates organisational units *inside one running instance* — departments,
teams, projects, a family. It governs visibility, sharing, cost attribution and permissions. It
is the first element of a command's `org_path` (§2). Every row in the database carries its
tenant, every repository call names its tenant as an explicit parameter, and row-level security
in the database keeps tenants apart even when a query forgets the filter. Until the identity
component exists there is one tenant, `default`, created by the first migration.

An **instance** separates *deployments* with a different cadence and a different blast radius:
its own database, its own secret store, its own configuration. Two instances share nothing and
never call each other. The Taktus project runs two — a development instance on `main`, a
project instance on a tagged release — so that a faulty version under development cannot take
down productive work (ADR-0013 D).
