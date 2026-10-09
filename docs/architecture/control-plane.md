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

A verified delivery that is a handshake — a source system checking the address before it sends
events there — is no event. The connector refuses it and adds the answer the source system
expects; the webhook intake returns that answer with status `200`, as it is, and keeps nothing
(ADR-0024, amendment of 2026-10-09). The surface knows no source system's handshake.

The identity port (`src/taktus/ports/identity.py`) is what the core asks: place a sender —
tenant, identity, organisational path — or answer that the sender is unknown. The identity
component serves it (`src/taktus/components/identity`, ADR-0040), and replaced the
provisional operator identity of DEC-0013 in `0.2.0`:

- **A sender is placed by the link of their account, and by nothing else.** A link maps one
  account on one channel to one identity; its identifier is derived from the two, so a second
  link for the account is refused. It is made by the person — who creates a single-use link
  code in their Taktus account, proved by its account key, and writes it in the channel from
  the account — or by the organisation's identity source, a port of its own. A matching name or
  address links nothing.
- **An unknown sender is answered, not executed.** The event is kept nowhere; the sender is
  told in the channel how to link the account, through the reply operation the channel's
  connector declares (`contracts/connector/v1` §7), as Taktus itself (ADR-0033).
- **Every link and every revocation is a ledger entry** (`identity.linked`,
  `identity.unlinked`). An administrator sees every link of a tenant and revokes one with
  `taktusctl identity links` and `revoke`; the next event from that account is from an
  unknown sender.
- **The command line names an identity the component knows** (`--identity`); the component
  supplies its organisational path. **A scheduled run acts for the identity that registered
  the process's active version** (ADR-0035, amended).

---

## 3. Plan

Optional, but the norm for anything new. Operator and Taktus develop a plan iteratively: what, with
what, by when, at which autonomy level. **Commissioning is an explicit, recorded act** — no plan
slides into execution through approval fatigue.

The plan is also the authoring tool for processes: it ends either in a one-off run or in a new
process version.

---

## 4. Process

A process is a **directed graph of steps**, not a script and not a prompt. Beside the graph a
process carries its **autonomy statement** (ADR-0026): the level it runs at, why, and what is
missing to go one level higher — or what forbids it. The statement is shown wherever the
process is shown; a bundle with a bare level does not register.

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

- **No limit is ever breached — beyond the one inner step during which a running total
  crossed it.** Before each step its demand is estimated — a worker by its own estimate, an
  `llm` step by the input its model counts and the output limit it sets, a connector call by its
  operation's declared demand, a rule by nothing — and a step that cannot be estimated is
  refused, not admitted. The estimate, scaled by its adapter's measured error, is *reserved*
  against what remains of the line the run is held to — its budget, less a holdback where an
  operator sets one. A worker nothing has measured yet reserves twice its estimate (DEC-0034).
  A worker receives its reservation as its `limits`, and halts at its next
  boundary before crossing them (W-14). The overrun of the one inner step during which a total
  crossed the line is the residual; the reservation exists to absorb it (ADR-0005, third amendment;
  DEC-0035). For money reported only when an assignment ends — the coding worker's — the worker
  cannot halt on it and is held by the tokens it reports per step. When a budget is set, the run
  records what it can promise per kind — exactly per step, as an estimate, only as a share of a
  subscription's time window, or not at all — derived from what each model adapter declares it
  can compute (`contracts/model/v1`), as `budget.set`.
- **At most one step of work is lost.** A stop — by limit, emergency stop, user or anchor — takes
  effect at the next step boundary; the running step may finish up to a hard ceiling.
- **Resume and replay.** After approval or a limit change, work continues at the step boundary.
  Because every step is recorded, a run can be replayed afterwards.

Workers with native pause support refine the granularity but are not required: the guarantee is
worker-agnostic.

In code, `src/taktus/components/run/` does exactly this around every step, whatever its method:
estimate, reserve against what remains of the run's line, run, persist checkpoint, artifacts and
raw consumption, then honour a pending stop at the boundary. A step rejected by admission control
halts the run with cause `limit`, one without an estimate with cause `no_estimate`; a raised
budget on resume lets it continue. A worker step
stopped mid-way ends with the worker's checkpoint, and the resumed assignment starts from it.

Every state change is one transaction with the ledger entry that describes it: the run as it
now is and the entry land together or not at all. A worker's own step boundaries are persisted
as they arrive, so that the boundary a run resumes from can lie inside a worker step.

**Restart.** An instance that stops without a chance to halt its runs — killed, crashed,
powered off — leaves each of them marked as running, with one step in flight. Resuming such a
run *recovers* it: the step in flight goes back to its last persisted boundary (the worker's
checkpoint if one arrived, its start otherwise), is admitted again — or, for a worker step
whose assignment the worker still holds, adopted — and the run continues;
the steps before it are kept as they are. That is ADR-0013 A made true, and
`tests/integration/test_restart.py` proves it by killing the process. Whoever resumes a running
run asserts that no instance is executing it. In the daemon that assertion is the runner's
claim: a submitted run is a job on the queue (`ports/queue.py`), a runner claims it with
`SELECT … FOR UPDATE SKIP LOCKED` and holds the claim as a lease it renews while the run
executes; a runner that dies stops renewing, the lease expires, and the next runner claims the
job and recovers the run at its last boundary (`components/run/application/service/runner.py`,
`tests/integration/test_daemon_scaling.py`; `tests/integration/test_runner_failover.py` kills
one of two runner processes mid-step). A runner that dies after its run ended and before it
completed the job leaves a job whose run is over; the next runner completes it and executes
nothing (NTC-0026). A runner that is alive but cannot renew for longer than the lease loses
the job as well. The claim is therefore also a *fence*: a check that refuses a write from a
holder who has lost the claim. Every transaction that writes a run executed under a claim first
asks the queue whether the claim is still the runner's (`Queue.fence`). The queue compares the
claimant and the claim's attempt — a later claim of the same job, even by the same runner, is
another claim — and keeps the job's row locked until the transaction ends, so that no claim can
take the job between the check and the commit. Once another runner has claimed the job, the
write is refused, nothing of it lands, and the first runner gives the run up without touching
the job. Two runners never both commit to one run (#107, NTC-0044;
`tests/integration/test_runner_fence.py` pauses a runner inside a step past its lease).
**An assignment a dead runner handed over.** A worker keeps an assignment it accepted when the
runner that posted it dies. The engine therefore commits the assignment's id with `step.assigned`
before it posts it, and keeps it *open* until it reads the assignment's end. Whoever recovers the
run asks the worker about an open assignment before handing over another. One the worker holds
is adopted (`step.adopted`) and its stream read on after the last event the step run holds; one
it does not know is posted again under the same id, so that a cut-off runner's late post meets
the worker's `409`; a worker that cannot be asked fails the step. No work the worker does is
unnamed in the ledger, and one step is never executed by two assignments at once. A runner that
loses its claim leaves the assignment to the runner that holds it now (ADR-0038, NTC-0073;
`tests/integration/test_handover.py` stops a runner after the worker accepted, after the first
inner boundary, and before its post arrives).
A shutdown on SIGTERM asks every running run to stop at its next boundary, waits up to the
ceiling, releases the claims and exits; the next runner resumes at that boundary
(`tests/integration/test_daemon_shutdown.py`). From the command line, `uv run taktusctl run
--resume` is the operator's explicit act of the same assertion.

**A worker at capacity.** A worker answers a new assignment with `503` when it holds as many as
it declares. That is no failure: nothing started. The step goes back to the boundary it was
admitted from, the run halts there with cause `capacity`, and the runner *defers* the job —
claimable again after a delay that doubles with every answer of the same wait, up to a minute,
and not counted as a failed attempt. The next runner to claim it asks the worker again. The
worker's own answer decides whether it has a free place; no runner counts a worker's
assignments, so runners that share one worker never place more on it than it declares. A wait
beyond the step's ceiling, one hour unless the step names one, escalates the run with cause
`capacity`. The ledger carries `step.waiting` for each answer and `step.waited` with the wait's
duration (ADR-0037; `tests/integration/test_capacity_wait.py`).

### 5.2 States

```
planned → admitted → running → [waiting_human] → running → finished
                        │            │
                        │            └─ decision request open (anchor, approval)
                        ├─ halted (limit, emergency stop, user, worker at capacity) → resumed
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
([throughput.md](throughput.md)). The line holds for the kinds reported per step — tokens,
quota, compute — up to one inner step's overrun, and only up to the estimate for currency
reported per assignment (ADR-0005, amendments).

What a step used is recorded raw, with language-model tokens **per model and per price kind** —
uncached input, output, cache read, cache write. Money is that record at a versioned price
table, which the run's budget statement names by digest, so that `taktusctl cost <run>`
recomputes it from the ledger (`components/accounting`); the Takt will be the same record at a
weighting table (ADR-0010, amendment).

*Available compute* is the platform's: what the machine or container the instance runs on has
left of memory, processor and storage. Taktus observes it, reports the date a person must act by
before it is tight, and refuses a job the platform cannot hold (`uv run taktusctl capacity`;
[platform.md](platform.md)).

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
