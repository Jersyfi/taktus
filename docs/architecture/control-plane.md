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
(`complete_intake.py`), and the command is then commissioned like any other. That request reads
the caller's account key from `Authorization: Bearer`, answers `401` without one, and completes
only an event of the caller's identity's tenant.

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
- **A contribution on a public channel is triaged for its owner** (UC-1.9, ADR-0088). On a
  channel `TAKTUS_TRIAGE` names, an issue or pull request an unknown sender opens is kept as data
  of the channel's triage process, without the sender's account or text, and starts that
  process once, acting for whoever registered its active version. The sender is offered the
  link all the same, and never acts.
- **Every link and every revocation is a ledger entry** (`identity.linked`,
  `identity.unlinked`). An administrator sees every link of a tenant and revokes one with
  `taktusctl identity links` and `revoke`; the next event from that account is from an
  unknown sender.
- **A tenant is created by an administrator, never chosen by a customer** (ADR-0104). The
  identity component keeps the instance's registry of tenants. `taktusctl tenant create` or
  `POST /administration/tenants` adds one, Taktus generates its identifier, and its display
  name may change. Each creation is the first entry of the new tenant's chain,
  `tenant.created`; a rename is `tenant.renamed`. Every role reads the registry at every
  round, so the new tenant is served without a restart.
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
process is shown; a bundle with a bare level does not register. A registered version never changes: a bundle registered again with the same identifier, version and content is the stored version, and registering it switches the process on again where it was switched off (ADR-0066 §5); one with another content is refused until it names a new version, because every run, ledger entry and provenance record that names the version describes what it was (#377).

### 4.1 What a step carries

- **method** — one of `rule`, `statistics`, `ml`, `neural`, `llm`, `worker`, `human`, `wait`
- **reason** for the choice and the **alternatives rejected**
- a **fallback** for any method that can vary
- an **exactness class** — `exact`, `sourced`, `tolerant`, `free` — limiting which methods may
  produce the result; on every step that produces one, never on `wait` or `human` (ADR-0018)

See [methods.md](methods.md). The choice is measured continuously and Taktus proposes changes.
A step of method `ml` registers only with its model's evaluation on held-out cases, for the
file it pins (UC-8.4 §2, ADR-0114).

### 4.2 Versioning

Every change creates a new **process version** with author, reason, diff and evaluation result.
A step moved to a trained model on an accepted proposal is such a version, and rolling it back
registers the replaced version again as a new one (ADR-0114). The
database holds the pointer to the active version; the versions themselves are **bundles**:
definition, prompts, skills, connector *capabilities*, governance rules and value criteria in one
package.

Mirroring to Git is enabled per process. With it on, history, diff, review and rollback are the same
mechanics as for code. With it off, history lives in the database. The bundle is the truth either
way — Git is a projection, not a second source.

Until the bundle format exists (`0.3.0`), a bundle is this process version written as YAML, with
one addition per step — `work`, what the step does when it runs — carried as data and interpreted
by the run. `examples/README.md` is the reference for that shape.

`taktusctl bundle check` holds a bundle to the rules registration holds it to, with the same
code and without an instance, a database or a login, so that a repository holding bundles checks
them in its own CI (ADR-0113 §4, `examples/README.md`).

A **skill** in a bundle is a directory in the open `SKILL.md` format, under
`skills/<name>/SKILL.md`: YAML front matter with `name` and `description`, then the instructions.
A step names the skills it uses in its `work`, under `skills`, by name; it still reaches its
adapter by capability, and no skill names a product (ADR-0113 §1–2). Nothing reads `skills` yet:
loading and handing them over is the skill lifecycle of `0.6.0` (UC-14.2).

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
  DEC-0035). Money is the run's: a worker's currency ceiling is what is left of the run's
  money, and a worker step whose own estimate fits is admitted with its reservation cut to what
  is left. The coding worker prices its tokens per step and halts on that money; a worker that
  reports money only when an assignment ends cannot halt on it (ADR-0005, seventh amendment,
  DEC-0202). A currency budget holds the
  money of compute seconds at the run's price table, and gives a worker the compute ceiling that
  money buys; under it, compute the table does not price is refused, not admitted as free
  (ADR-0005, fourth amendment). When a budget is set, the run
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
budget on resume lets it continue. A person raises it with `taktusctl resume --run RUN --raise
AMOUNT --reason TEXT`: the run's own money limit grows by the amount, no bundle is read and no
version registered, and the `budget.set` statement names the limit before and the reason. The
raise is held to the ceiling the operator sets in `TAKTUS_RAISE_CEILING`, an amount and its
currency; without one no raise is admitted (#458, DEC-0202). `--raise-quota UNITS` raises its
quota the same way, held to `TAKTUS_RAISE_CEILING_QUOTA` (DEC-0208). A worker step
stopped mid-way ends with the worker's checkpoint, and the resumed assignment starts from it. A
worker that stopped on its own, before its unit's wall clock, with no limit reached and no stop
asked for, has its step continued at once in a new unit, at most three times (ADR-0102).

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
admitted from with no assignment open — the worker took none, so a resume hands one over again
rather than asking about it (#486) — the run halts there with cause `capacity`, and the runner
*defers* the job —
claimable again after a delay that doubles with every answer of the same wait, up to a minute,
and not counted as a failed attempt. The next runner to claim it asks the worker again. The
worker's own answer decides whether it has a free place; no runner counts a worker's
assignments, so runners that share one worker never place more on it than it declares. A wait
beyond the step's ceiling, one hour unless the step names one, escalates the run with cause
`capacity`. The ledger carries `step.waiting` for each answer and `step.waited` with the wait's
duration (ADR-0037; `tests/integration/test_capacity_wait.py`).

**A provider at its rate limit.** A model provider that answers `429` is treated the same way:
nothing was produced, the step goes back to its boundary, the run halts with cause `capacity`,
and the runner tries again later. Past the engine's ceiling the run escalates (ADR-0043).
Where another model of the purpose's chain fits the step, the step is admitted again at once on
that model instead, and the wait is booked all the same. A model that failed moves the step the
same way, with no block booked (ADR-0116).

**Blocked time.** Every block of a run — a stretch in which a step could not go on — is booked to
one of the seven accounts of [throughput.md](throughput.md) §1. The step run carries the block
while it lasts; when it ends, `step.waited` names its record with the account, the cause and the
duration (ADR-0043).

### 5.2 States

```
planned → admitted → running → [waiting_human] → running → finished
                        │            │
                        │            └─ a step waits for a person (approval, an act to perform, anchor)
                        ├─ halted (limit, emergency stop, user, worker at capacity, maturity) → resumed
                        ├─ self-healed (retry or correction within frame) → running
                        └─ escalated (frame exceeded) → situation package to a person
```

A run reaches `waiting_human` when every step it can still run waits for a person: a step at
autonomy level 2 for a confirmation, a step that acts at level 1 for the person to perform it
(ADR-0039), a step whose act an anchor names for the decision its request asks for, at every
level (ADR-0042). Such a step is in the step state `waiting_human`; the steps that do not depend
on it run on before the run waits. A person's answer continues the run; a stop halts it at once.
A declined anchored act halts the run with cause `declined`, and a resume asks again.

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

**Every run ends `ok`, `empty` or `error`, with its duration** (ADR-0107). `run.ended` is
written beside `run.finished` and `run.escalated`, in the same transaction, with the time from
the run's creation in `duration_seconds`. An escalated run ends `error`. A finished run ends
`empty` when a step that marks it so (`empty_when_skipped`) was skipped, and `ok` otherwise. A
schedule trigger whose `each` list was empty records `trigger.empty`.

**A run that was expected and did not happen raises an incident**, the first source of one
(ADR-0107, UC-4.16). A process version declares when a run is expected (`expect`), or inherits
its schedule triggers. While it leads, the scheduler looks once a minute
(`composition/expected_runs.py`). A rule over the expectation and the ledger finds a slot that
no run answered within the tenant's grace period, a gap that passed without a run, and a run
that did not end within its bound. It raises an incident in the governance component, recorded
as `incident.raised`. A further miss and a run that happened late are recorded on it, and a
person closes it (`taktusctl incident`). A process whose ends are mostly `empty` is reported as
`watch.empty_share`. Delivering the incident, its severity and its report are UC-6.8.

**A signal's red value raises an incident too** (ADR-0109, UC-6.13). A signal is the result of
one step of method `rule` or `statistics`, exact or sourced, with a provenance record. Its
corridor is the tenant's configuration: a yellow and a red threshold, as a multiple of the
median of the step's own earlier results or as fixed bounds. A person changes it, as a new
version (`taktusctl signal`); a run or a worker cannot. While it leads, the scheduler judges the
newest value of each signal once a minute (`composition/signals.py`). A red value raises an
incident of kind `signal.red` and reaches the owner's channel at once. From 06:00 UTC it raises
the daily report: every signal outside its corridor and every one not measured, each line with
its run, its step and its case. A reply that names an offered intervention is read back, and its
confirmation starts the process as a command for the person who confirmed it.

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

**A read costs what it returns** (ADR-0105). The entries of one run are read through the index
`ledger_entry_run`, and the entries of some kinds through `ledger_entry_kind`. Neither reads the
rest of the chain. A value over the whole history is a *projection*: a value computed from the
ledger entry by entry, stored in `ledger_projection` with the sequence number of the last entry
it read. A read brings it up to date from that number and stores it again. Two are defined, in
`components/run/domain/service/projections.py`. The calibration keeps the last twenty
observations of each adapter, method and step, which is all a run start reads. The activity
names the runs with an entry in each process and day, for the blocked-time sums. A projection is
derived, not a second source. It is rebuilt from the ledger at any time, and a test compares
the rebuild with the full computation. A projection whose rule changes takes a new name, and is
built again from the first entry. A write of a projection never waits: a second writer finds the
first holding the projection's claim and stores nothing.

The four readers that still walked the whole ledger name what they need too (ADR-0105 §9, #522).
The Takt rate is the projection `accounting.takt.v1`
(`components/accounting/domain/service/takt_window.py`): per day and run, what the run's steps
finished that day used, and per run the budget statement it names, for the last 33 days. A read
takes the whole days of its window from the projection and the two partial days at its ends from
the ledger through `ledger_entry_kind_ts` (`Ledger.of_kinds(..., since=, until=)`); a run the
projection no longer knows is read with `Ledger.of_runs`. The measures read `step.corrected`. The quality history of a raise is the
projection `process.quality.v1`, read by a proposal and by a registration; `autonomy.history` is
the full computation it equals. With 500 000 entries the history took 9 ms, the Takt rate over
30 days (7 200 finished steps) 30 ms and the measures 2 ms
(`tests/integration/test_ledger_at_scale.py`).

**A chain is verified from its last verified checkpoint.** The checkpoint is the sequence number
and hash of the newest entry a verification found intact, stored as a projection. A verification
walks the entries after it and moves it when it finds nothing. `GET /runs/{id}/ledger` answers
where its walk started, as `chain.checkpoint`. A full verification walks from the first entry
and trusts no checkpoint: `taktusctl ledger verify --full`. When it finds a fault, the checkpoint
goes back to the start, so every later verification finds the fault again. A change to an entry
before the checkpoint is found only by the full verification. With 500 000 entries in a tenant,
a run start's calibration took 7 to 22 ms and `GET /runs/{id}/ledger` 53 to 57 ms
(`tests/integration/test_ledger_at_scale.py`); reading the whole ledger instead took 6.9 s and
18.9 s on the same machine.

In the database the ledger is append-only by construction, not only by convention: the
application role may insert and read, and a trigger rejects every update, delete and truncate
for everyone but a superuser (`migrations/`). A hash chain whose rows can be edited proves
nothing.

**One chain per tenant, one claim on it.** Each entry carries the next sequence number and the
hash of the entry before it, so two transactions must not append to one chain at once. The
ledger store claims the tenant's chain when it reads the newest entry, and holds the claim until
the transaction ends: in the database a transaction advisory lock, in memory a lock released at
the transaction's end. A second transaction waits, then reads the first one's entries. The claim
is the only lock on the chain; no lock of the process is held beside it. A lock of the process
held while the store waits for the claim formed a cycle that neither side could see: two runs of
one tenant whose commits recorded two entries each hung for good (#309, NTC-0201;
`tests/integration/test_ledger_concurrency.py`). Every database connection also carries
`lock_timeout` and `idle_in_transaction_session_timeout`
(`TAKTUS_DATABASE_LOCK_TIMEOUT_SECONDS`, 30; `TAKTUS_DATABASE_IDLE_IN_TRANSACTION_SECONDS`, 120),
so a wait that should not happen fails with the server's reason instead of holding a runner's
place while its lease is still renewed.

**A change of state reaches its reader from the ledger** (ADR-0055). Every insert notifies the
tenant it wrote, from a trigger, when its transaction commits. The `api` role reads the
tenant's new entries on that signal, or every 2 seconds without one, and sends each entry that
records a change of state of a run, a step or a decision request to the streams that may see it
(`GET /changes`, `contracts/changes/v1`). Which state an entry's kind and outcome lead to is
published beside the state machine: `components/run/domain/model/recorded.py` for runs and
steps, `components/decision/domain/model/recorded.py` for decision requests.

**Whether a reader may see a run is one predicate** (ADR-0055 §5):
`components/reporting/domain/service/visibility.py`. The stream asks it for each change, and the
read API — `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/ledger` — for each run it would show.
Both read the account key from `Authorization: Bearer` and answer `401` without one; the tenant
is the reader's identity's. Every caller calls the predicate through its module, so that no
path holds a copy. Until the role-based views of UC-6.4, the predicate is the tenant boundary.

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
quota, compute, and money where a worker reports it per step, as the coding worker does — up to
one inner step's overrun, and only up to the estimate for currency reported per assignment
(ADR-0005, amendments).

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

A figure that must hold in operation is a histogram beside the spans (`ports/telemetry.py`,
`observe`). The first is `change.handover`: the seconds from a ledger entry's recorded moment to
its hand-over to a reader's stream, which ADR-0055 bounds at 5.

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

**What leaves an instance for the product.** One thing does, and only where the instance's
operator enabled it: product findings and reports written by hand, sent as issues to the Taktus
repository through a connector of the capability `repository` (UC-6.12, ADR-0046, ADR-0112).
The one setting is `TAKTUS_FINDINGS_CONNECTOR`, and each tenant's ledger records each change of
it as `finding.enabled` or `finding.disabled`. A finding names the run and the step it was met
in by pseudonym: an HMAC of the identifier under a key the tenant's instance draws and never
sends. It names its sender, one tenant of one instance, by a random identifier, never by a
person, an operator or a tenant. One lack is one issue across every instance that sends to it.
Before anything leaves, one rule checks every part that came from the instance — what was
lacking, the operator's form, a person's text — against the tenant's own values and the shapes
of personal data, and withholds what fails (`components/reporting/domain/service/leaving.py`).
A report by hand (`taktusctl findings report`) is shown exactly as it would be sent, and sent
only once the person confirms it.
