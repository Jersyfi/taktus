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

### `0.2.0` — governance, limits, availability
Autonomy levels 1–3 per process **and per action class** · anchors, configurable per tenant ·
decision requests and the register · budgets and admission control · **blocked-time accounts** ·
**Takt measurement, not yet charged** · multi-instance operation with restart at step boundaries ·
chat connector

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
Value ledger with revert analysis · role-based views · takeover test and removal test automated ·
marginal-value recommendations · BI export

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

**Complete when** a stranger builds an adapter without asking.

---

## After `1.0.0`

Federation between instances · a governed process marketplace · anonymous value benchmarks (opt-in) ·
run replay for audit and training · founding a business from blueprints · the worker contract
published as an open specification.

Each of these needs its own decision. None is pulled forward.
