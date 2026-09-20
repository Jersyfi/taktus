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

A connector's intake (`contracts/connector/v1` §7) supplies the channel's half of this object:
the sender as the source system names them, the intent, the context and the reply address — and
only after the event's signature verified. The identity component maps the sender to `identity`
and `org_path` and completes the command; the connector never holds that mapping. What the
webhook intake of the HTTP surface accepts is kept as an **intake event** (`command`
component, `awaiting_identity`) under the source system's delivery identifier — a redelivery
replaces, never doubles — in the tenant the identity port places the sender in, and nothing is
executed from it. `POST /intake-events/{id}/complete` completes it into a command
(`complete_intake.py`), and the command is then commissioned like any other.

The identity port (`src/taktus/ports/identity.py`) is what the core asks: place a sender —
tenant, identity, organisational path — or answer that the sender is unknown. **Until the
identity component exists (`0.2.0`) the port is served by a provisional adapter:** one
configured operator identity per tenant, `TAKTUS_PROVISIONAL_IDENTITY=<tenant>=<identity>`,
which every command of that tenant acts as — from the command line, where `taktusctl run`
takes it when `--identity` is not given and refuses to run with neither, and from a webhook,
where every sender of the one configured tenant resolves to its operator. Every resolution it
answers carries `provisional: true`, every command it completes carries
`identity_provisional: true` in its context, and DEC-0013 states what it does not do and what
replaces it.

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

- **No limit is ever breached — for what is reported per step.** Before each step its demand is
  estimated (the worker supplies the estimate) and checked against what remains. A step starts
  only if it fits. The guarantee comes from *admission*, not from aborting, and admission needs
  a running total: for tokens, quota and compute seconds, which workers report per step, the
  total is exact at every boundary and the guarantee holds. For currency it degrades to an
  estimate where a worker learns its cost only when an assignment ends — the coding worker
  does — so that the budget can be exceeded by the difference between one assignment's estimate
  and its actual cost, visible in the ledger at the boundary where it was reported (ADR-0005,
  amendment; DEC-0012). The owner's position is that a limit is a limit: the second amendment
  of ADR-0005 records the design that closes the gap as far as a provider allows — the
  estimate reserved at admission, a currency budget converted into tokens and enforced there,
  a named safety margin, estimate quality measured per worker, and the residual stated in
  every report. It is designed, not yet implemented.
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
run asserts that no instance is executing it. In the daemon that assertion is the runner's
claim: a submitted run is a job on the queue (`ports/queue.py`), a runner claims it with
`SELECT … FOR UPDATE SKIP LOCKED` and holds the claim as a lease it renews while the run
executes; a runner that dies stops renewing, the lease expires, and the next runner claims the
job and recovers the run — two runners never execute one run
(`components/run/application/service/runner.py`, `tests/integration/test_daemon_scaling.py`).
A shutdown on SIGTERM asks every running run to stop at its next boundary, waits up to the
ceiling, releases the claims and exits; the next runner resumes at that boundary
(`tests/integration/test_daemon_shutdown.py`). From the command line, `uv run taktusctl run
--resume` is the operator's explicit act of the same assertion.

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

### 5.3 Failure, result defect, incident

Three words, kept apart (ADR-0021):

| Term | Meaning | Where it shows |
|---|---|---|
| **failure** | a run or a step did not complete | the states above: `halted`, `escalated`, a step `failed`, `rejected` or `stopped`; the cause is a token in the ledger |
| **result defect** | a run completed and reported success, but its result is wrong | nowhere in the states; only a check of the result finds it (UC-4.10, `0.5.0`) |
| **incident** | the tracked object above either: severity, timeline, affected scope, remediation plan, addressees, closure | raised and delivered into the organisation's own tracking system (UC-6.8, `0.5.0`) |

The model above handles failures. Result defects need a record that this version writes and a
detection that `0.5.0` adds; the record is the provenance chain of §6.1.

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

### 6.1 Provenance

The ledger says *what happened*. The **provenance record** says *what a result is made of*
(ADR-0021). One record per completed step run, written in the same transaction as the
`step.finished` entry and bound to it by sequence number:

| The record names | Taken from |
|---|---|
| the process version; the step, its method and exactness class; the model version where the step pins one | the run and its step |
| the adapter that executed and the version the worker declares for itself | the worker pool (`Capabilities.version` of the worker contract) |
| the inputs: every result or artifact of an earlier step the step read — by run, step, artifact identifier and digest — and every external source, each with the moment it was read | the run engine, as it resolves `$from` and as a rule reads an artifact |
| the outputs: the artifact identifiers the step run produced across its attempts; the digest of the value it produced | the step run |

It references and never copies: identifiers, tokens and digests, no content. Its shape is the
shared kernel's `Provenance.json`; the run component builds and verifies it
(`domain/service/provenance.py`), the persistence port stores it (`ProvenanceStore`), and the
database keeps it immutable the way it keeps the ledger — insert and read for the application
role, a trigger against everything else, one record per step run by unique key
(`migrations/versions/0002_provenance.py`).

Following inputs from the record that produced an artifact leads back through every step run
that contributed to it, across runs. That walk is one query (`ProvenanceQuery.chain`), and
`ProvenanceQuery.verify` holds a run's records against the run and against the ledger: every
completed step has exactly one record, every input names a record that lists what was read,
every record agrees with the entry it names. Growth is bounded and measured: one record per
completed step, never more than a third of the run's ledger entries, at most 1 KiB plus 384
bytes per input and 80 bytes per output (ADR-0021 §4).

The chain is what makes "since when has this been wrong?" answerable once detection exists
(UC-4.10 to UC-4.12, `0.5.0`), and it is why the chain arrives before the detection.

---

## 7. Consumption

Every step reports what it used. The raw quantities are measured — tokens, compute seconds, resource
class, step count, storage — and the normalised unit **Takt** is derived from them.

Admission control works against all applicable limits at once: budget in currency, a subscription
window, a provider rate limit, available compute. If the estimate does not fit, the step does not
start, and the block is recorded with cause and duration in the blocked-time account
([throughput.md](throughput.md)). The line holds exactly for the kinds reported per step —
tokens, quota, compute — and only up to the estimate for currency reported per assignment
(ADR-0005, amendment). That is why the Takt derives from tokens and compute and not from money:
it is the quantity admission control can actually hold a run against.

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
