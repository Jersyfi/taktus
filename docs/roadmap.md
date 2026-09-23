# Roadmap

No dates — completion criteria. Every version ends in a state that can be used in production.

**Ordering rule:** nothing from a later version is built while the architecture tests and the removal
test of the previous one are not automated. The architecture tests belong to `0.1.0`, not to rework.

---

## The handover path

Taktus develops itself. That only works in this order.

| Stage | Driven by | Complete when |
|---|---|---|
| **S0 — bootstrap** | a local coding session, issue-driven | the contracts exist as schema plus conformance suite |
| **S1 — first run** | the same session builds `taktusd` | Taktus turns one of its own issues into a pull request that passes CI |
| **S2 — self-maintenance** | Taktus, supervised | **14 days** with no human intervention in execution |
| **S3 — second tenant** | Taktus orchestrates a second project | a milestone there is reached without intervention except at anchors |
| **S4 — level 4** | Taktus unattended | a release happens end to end |

**S3 starts at `0.4.0`, not at `1.0.0`.** The reason is deliberate: versions `0.5` to `0.7` — value
ledger, role-based views, level 4, the second blueprint — need operating data from a second tenant to
be designed correctly. Taktus's own repository is an atypical subject: small, documentation-heavy,
one contributor. Building the later versions on that alone means building them blind.

The second tenant starts at autonomy level 1–2 (advise and propose only) for the first weeks, and
rises only on evidence.

---

## Milestones

### `0.1.0` — control-plane minimum
Contracts and conformance suite · command, plan, process, run, ledger · **method kinds and exactness
classes in the data model** · workers `script` and `mlbench` · execution adapters `process` and
`container` · connector `github` · CLI channel · OpenTelemetry · architecture tests and
`import-linter` contracts

**Complete when** Taktus turns one of its own issues into a pull request that passes CI, and every
step carries method, exactness class and consumption.

**Done so far:** the contracts as executable JSON Schema with the shared kernel (#1) · the
decision register and the owner's anchors (#3) · the conformance suite for the worker contract,
runnable by a third party against a live worker, proven to fail on every injected fault, the
`script` worker in both profiles and `taktusctl conformance run` (#4) · the first vertical slice
of the control plane: command, plan, process version as a validated graph, run with step
atomicity and admission control, the content-free ledger with verification, the worker port and
its HTTP adapter, `taktusctl run` against the reference worker, in memory; the architecture
tests, `tests/exactness` real, the shared kernel bound to Python and checked (#5) ·
persistence in PostgreSQL: every table tenant-scoped under row-level security, the ledger
append-only in the database, one repository suite that the memory and the database
implementation both pass, and a restart proven — a killed `taktusctl run` resumes at its last
step boundary with an unbroken ledger (ADR-0013 A, for one instance; ADR-0020 for the tenant
and instance boundaries) (#6) · the provenance chain: one immutable record per completed step
naming process version, method, exactness, model, adapter and version, inputs with the
moment each was read, outputs and the ledger entry, walkable back from any artifact in one
query and proven across a restart; the three terms failure, result defect and incident; the
correction anchor with a checkable "has left the system"; the rule-based automatic
emergency stop (ADR-0021 to ADR-0023; detection and repair themselves are `0.5.0`) · the
connector contract on MCP as executable schema, the conformance suite for it — runnable by a
third party against a live connector, proven to fail on every injected fault — and the
reference repository connector in both directions: actions with a declared effect and a
recognised repeat, proven to open one pull request for a step across a restart, and webhook
intake refused unless signed (ADR-0024) · the daemon `taktusd` (#9): four roles in one image
selected by `TAKTUS_ROLES`, runners that claim runs through the database with a lease and never
claim the same run, a scheduler elected by an advisory lock that a survivor takes over, a
shutdown on SIGTERM that lands on a step boundary and releases the run, health and readiness as
two different questions, a refusal to start against a schema that does not match the binary,
configuration through validated `TAKTUS_*` variables with secrets read from files and logged
masked, the HTTP surface under a configurable prefix — health, readiness, webhook intake
through the connector port (the intake half), a read API for runs and ledger entries,
`api/openapi.yaml` — and self-hosting in two containers with `make up`, proven from nothing
by killing and restarting the container; the frame names allowed hosts (W-13), credentials
are parameters (ADR-0025 says where an instance may run) · the execution layer (#10): the
execution port with the `process` adapter (refused from autonomy level 3 upwards and when the
level is unknown, enforced in code) and the `container` adapter — one container per job with
CPU, memory and wall-clock limits enforced by killing, credentials in memory only, a per-job
network with an egress proxy that admits exactly `frame.allowed_hosts`, no engine socket —
proven from inside a job and end to end with a stop and a resume in a new container; the
coding worker, passing the suite in both authentication modes with every fault, boundaries
per tool call, tokens per step, money at the end; OpenTelemetry spans for run, step, worker
and connector calls with the trace identifier on every ledger entry and log line, exported
where `TAKTUS_OTLP_*` says; each worker in its own image and none in the control plane image
(DEC-0011) · the action half of the connector and the first end-to-end (#13): the connector
port in both directions, connector steps in the run with an idempotency key derived from run,
step and attempt — a crash after the target acted is replayed, never repeated — and an egress
entry for every outward effect (ADR-0022 made checkable at the source); branches, labels and
the pipeline's verdict in the reference connector, proven against the real service across a
restart; the model port with its adapter over the chat-completions dialect and `llm` steps
whose answer leaves only when it passes the step's check; a provisional operator identity per
tenant, marked as such (DEC-0013), and intake events completed into commands by it; P-02
Refinement and P-03 Implementation of the dev-orchestration blueprint as bundles that run —
proven end to end with the outside faked and everything inside real, and then **run for real
against this repository all the way to a pull request that passes CI**
(`docs/runs/first-run.md`; the attempt before the credentials existed is
`docs/runs/2026-09-19-the-run-that-stopped.md`); ADR-0005
now says for which consumption kinds the limit guarantee holds (DEC-0012) · the decision model
rebuilt from the owner's answers (#14): four modes in two anchor files — the shipped default
and the Taktus tenant's own — a notice record for mode-2 decisions with its gate, every ADR
stating where its promise ends with a gate that fails one that does not; **the removal test as
a process** (`blueprints/self-operation/`, S-01): the loopback connector through which Taktus
reaches itself, the catalog's maturity record and the verdict rules, one run per configured
integration, weekly, with the verdict in the ledger as `removal.tested` — run once for real,
recorded in the blueprint's README; every process carrying its autonomy level with its reason
and what is missing to go higher (ADR-0026); the design of a budget that is a budget (ADR-0005,
second amendment); the exactness statement specified for `0.5.0` (UC-4.13, UC-6.9).

**Is `0.1.0` complete?** No. The completion criterion has two halves. *Every step carries
method, exactness class and consumption* holds: every step of every bundle carries its method,
its reason, its alternatives, a fallback where the method varies and an exactness class, and
every step run records what it used. *Taktus turns one of its own issues into a pull request
that passes CI* **holds since 2026-09-23**: issue #11 became pull request #38, opened by
Taktus through P-03 Implementation, with every check of that pull request green and the merge
left to a person. It took P-02 one attempt and P-03 eight, of which seven failed on four
defects in Taktus and one flaky test and none on the change itself; what each step consumed
against what was estimated is in `docs/runs/first-run.md`, and those figures are the first
calibration point for the budget of `0.2.0`.
Also not yet, from the list above: `mlbench` (its real work is `0.4.0`; no proof-case worker
of that shape exists yet), the model contract as a schema with a conformance suite (the port
and one adapter exist), governance and anchors, the cluster execution adapter, the container
registry build and the Helm chart, the identity component (a provisional identity stands in
for it), time triggers (the scheduler leads and ticks; nothing is scheduled), event reactions
(the automation role starts and waits; the outbox exists, nothing writes it; an intake event is
completed into a command by hand), and a live run of the coding worker against its real agent
in CI (it needs a credential; the gate runs the stand-in).

### `0.2.0` — governance, limits, availability
Autonomy levels 1–3 per process **and per action class** · anchors, configurable per tenant ·
decision requests and the register · budgets and admission control — **a budget is a budget**:
the estimate reserved at admission, a currency budget converted into tokens and enforced there,
a named safety margin, estimate quality measured per worker, the residual in every report
(ADR-0005, second amendment) · **blocked-time accounts** · **Takt measurement, not yet
charged** · multi-instance operation with restart at step boundaries · the scheduler starting
runs from a bundle's trigger, so that the removal test runs weekly without a script · chat
connector

**Complete when** Taktus maintains its own repository for **14 days** with no intervention in
execution, and every block is analysable by cause and duration.

### `0.3.0` — visibility
Web app: dashboard, process diagram, run history, ledger, consumption, bottleneck overview · process
bundle format · pair editing with rollback · sessions with project knowledge

**Complete when** a process can be created, viewed, changed and rolled back entirely from the web app
and chat, and you can see your own share of the waiting time.

### `0.4.0` — the ML bench and the second tenant
`mlbench` worker doing real work: training, evaluation, embeddings, classical ML · method maturation
with change proposals · model hub for in-house models · second coding worker · model routing ·
`dev-orchestration` blueprint · **second tenant onboarded at level 1–2**

**Complete when** a step moves from a language model to a trained model on Taktus's own proposal —
measurably cheaper and reproducible — and the second tenant produces its first milestone.

### `0.5.0` — value and dependency measurable
Value ledger with revert analysis · role-based views · takeover test automated (the removal
test runs since `0.1.0`; the conformance half of *verified* recorded, so that an adapter can
reach it) · marginal-value recommendations · BI export · **exactness is a result, not a
switch**: Taktus works out with the user how a step becomes exact, and every process carries
an exactness statement — what was checked against what, what was not, what would slip
through — in the dashboard and in every report (UC-4.13, UC-6.9) · **result defects handled**: deviation detection,
error window and impact analysis over the provenance chain, remediation plans under the
correction anchor, incidents delivered into the organisation's own tracking (UC-4.10 to
UC-4.12, UC-6.8; ADR-0021 to ADR-0023)

**Complete when** principles 6 and 13 are measured rather than asserted, and limit recommendations
come with numbers.

### `0.6.0` — level 4
Autonomy level 4 · skill lifecycle · the catalogue · role-based agents · recurring decisions become
rules on proposal

**Complete when** a release happens end to end without intervention.

### `0.7.0` — second domain
`it-operations` blueprint · connectors for operations and monitoring · autonomy per action class in
production use

**Complete when** the second use case runs in production.

### `1.0.0` — contracts, licence, opening
Contracts frozen and versioned · **licence decided, contributions opened** · accounting formula
calibrated from real data across both use cases · community adapters in their own repositories ·
GDPR tooling and generated compliance evidence

**Complete when** a stranger builds an adapter without asking, and every condition of *The road
to 1.0.0* below holds.

---

## The road to 1.0.0

What `1.0.0` needs beyond features. Each is a condition with a check, not a date that passes.
None is pulled forward into a feature milestone, and none is dropped without a decision
(anchors.taktus.md M3.6: preparing a release is the owner's).

**Freezing the contracts is a milestone with its own check.** `v1` has moved twice since the
first pull request, each time rightly. The moment it stops moving must be a deliberate act, not
the absence of a change: a record under `contracts/` names every `v1` schema with its digest
and the date, `make gate-contracts` fails on any change to a frozen schema, and a change after
the freeze is `v2` under a new `$id` (ADR-0019). Freezing is proposed as a decision request
(M3.5) with the evidence that no open use case needs a change, and the freeze holds through
the stabilisation phase before the tag.

| Condition | Checked by |
|---|---|
| **Contracts frozen, verified** | the freeze record exists; the gate fails on a frozen schema's change; both conformance suites pass against every reference adapter at the frozen version |
| **A stabilisation phase with no new features** | a stated span before the tag in which every merged change is a fix or documentation; the register shows no accepted feature in it |
| **The removal test green for every adapter, not one** | the last weekly S-01 run of every configured integration ended *changed* or *exception*, in an installation with an alternative for every capability a reference adapter serves |
| **An upgrade path from `0.7.0` that loses no runs** | a migration test upgrades a database with runs in every state from `0.7.0` to `1.0.0` and back, and every run resumes at its boundary afterwards |
| **Data export proven by re-import** | an export of a tenant — processes, runs, ledger, provenance, artifacts — is imported into a fresh instance, and the ledger chain and every provenance chain verify there |
| **An external security review of the execution isolation** | a review by someone outside the project of the container and cluster adapters, its findings recorded and closed |
| **GDPR tooling and generated compliance evidence** | a data-subject request answered from the ledger and the provenance chain without a query written by hand; the evidence generated, not written |
| **Measured load behaviour** | a number: how many concurrent runs one instance carries at which latency, measured by S-04 on stated hardware, so that someone can answer the question instead of guessing |
| **A restore drill that verifies the ledger chain** | S-03: an earlier version restored without Taktus (ADR-0013 C), and the check is that every tenant's chain verifies against a digest taken before, not that the database starts |
| **Versioning and deprecation rules** | written: what a minor and a major change to the product and to a contract mean, how long a deprecated `v1` is served, and how an installation learns of it |
| **Documentation a stranger can follow** | a person who has never seen the repository installs Taktus, registers a process and runs it from the documentation alone, and the places they stopped are fixed |
| **The licence and a contributor agreement** | ADR-0012 decided (M4.1), the agreement in the repository, before the first outside contribution |
| **The Takt calibrated from real data** | ADR-0010 accepted with weights derived from the ledgers of both reference use cases, the derivation recomputable |

Two obligations hold on this road and after it, and are enforced rather than hoped for
(CLAUDE.md §11): tests and documentation stay true over time — a gate whose coverage develops a
hole is a finding, and a suite too slow to be useful is a finding reported with its cost before
and after; and a retroactive correction stays executable by hand (UC-4.12).

---

## After `1.0.0`

Federation between instances · a governed process marketplace · anonymous value benchmarks (opt-in) ·
run replay for audit and training · founding a business from blueprints · the worker contract
published as an open specification.

Each of these needs its own decision. None is pulled forward.
