# Decision register

The decisions of the Taktus project itself: what the owner was asked, what was answered, what
was raised as a decision and turned out not to be one, and what a session decided on its own
and gave notice of. The mechanism is ADR-0017. Which questions reach the owner is stated in
four modes: [anchors.md](anchors.md) is the shipped default any tenant inherits, and
[anchors.taktus.md](anchors.taktus.md) is the configuration of this tenant, the Taktus
project. The template for a request is [TEMPLATE.md](TEMPLATE.md); the template for a notice
is [TEMPLATE-NOTICE.md](TEMPLATE-NOTICE.md); the template for a needs request is
[TEMPLATE-NEED.md](TEMPLATE-NEED.md).

The category `DEFECT` is a *documentation defect*: a fault in what the repository says, corrected
and recorded, never asked. A wrong result produced by a run is a *result defect* (ADR-0021) and
never appears in this register.

`open/` holds requests that wait for an answer, and needs that wait to be provided. A request
leaves `open/` in the same commit that creates its record here. `make gate-decisions` checks
both, the notices, and the needs.

A **notice**, `NTC-NNNN`, is the record of a mode-2 decision (anchors.md §1): the session
decided, nobody approves, and the record states what was decided, on what evidence, what was
considered and which entry permits it. Every notice carries a **kind** — `restructuring`,
`test-strategy`, `gate-weakened`, `behaviour-change` — so that the register reads by kind and
a weakened gate is never buried among behaviour changes (DEC-0014). A notice that weakens a
gate carries the demonstration that the gate had no value, in the record itself.

A **needs request**, `NEED-NNNN`, is the record of something only the owner can provide — a
credential, an account, access to a system, a purchase, an action on a server, information about
an environment (ADR-0028). It is raised when it becomes foreseeable, not when it blocks; raising
it is mode 2 (entry M2.5), providing it is the owner's act. An open need is under `open/` with an
issue labelled `needs-owner`; a provided need is a record here with its outcome. What is open is
in [../status.md](../status.md), section 3.

## Needs

| NEED | Title | Kind | Outcome |
|---|---|---|---|
| [0001](NEED-0001-the-coding-agents-credential.md) | The coding agent's credential | `credential` | provided 2026-09-22 as an API key; confirmed 2026-09-23; renewed under NEED-0005 |
| [0002](NEED-0002-the-repository-connectors-token.md) | The repository connector's token | `credential` | provided 2026-09-22 as a fine-grained token for this repository; confirmed 2026-09-23; renewed under NEED-0006 |
| [0003](NEED-0003-the-model-endpoint-and-its-key.md) | The model endpoint and its key | `credential` | provided 2026-09-22 as the endpoint, the model and the key file of NEED-0001; confirmed 2026-09-23; the model chosen is DEC-0019 |
| [0004](NEED-0004-the-platforms-current-interface-note.md) | The platform's current interface note | `information` | superseded 2026-09-23: the owner decided the target (DEC-0023) and gave read-only access instead of a note; a session inspected the platform and answered all ten points, outside this repository. Replaced by NEED-0007 and NEED-0008 |

The open needs are listed in [../status.md](../status.md), section 3.

## Notices

| NTC | Title | Entry | Kind | What was decided |
|---|---|---|---|---|
| [0001](NTC-0001-anchors-split-into-two-files.md) | Anchors split into two files with four modes | M2.1 | `restructuring` | the anchor page is the shipped default plus the Taktus tenant's configuration, entries identified `M<mode>.<n>`, the old rows mapped |
| [0002](NTC-0002-a-missing-adapter-fails-the-step.md) | A missing adapter fails the step at the boundary | M2.4 | `behaviour-change` | a step whose worker, connector or operation is not configured ends failed and retryable with the reason, and the run escalates at that boundary instead of raising out of the engine |
| [0003](NTC-0003-the-first-runs-credential-variables-renamed.md) | The first run's credential variables renamed | M2.4 | `behaviour-change` | `tools/first_run.sh` reads the repository token and the coding agent's credential under `TAKTUS_CREDENTIAL_<NAME>_FILE`, the one pattern every credential follows; the same files hold the same values |
| [0004](NTC-0004-run-records-move-into-their-own-directory.md) | Run records move into their own directory | M2.1 | `restructuring` | `docs/runs/` holds one record per run worth keeping, with a `README.md` that says what belongs there; the record of 2026-09-19 keeps its content under its date |

## Decisions

| DEC | Title | Category | Outcome |
|---|---|---|---|
| [0001](DEC-0001-contract-identity.md) | Contract identity | NON-BLOCKING | answered: `https://taktus.eu/contracts/<family>/v1/<Concept>.json` (ADR-0019) |
| [0002](DEC-0002-exactness-and-non-producing-steps.md) | Exactness and non-producing steps | DEFECT | corrected: exactness applies to result-producing steps only (ADR-0018) |
| [0003](DEC-0003-where-the-stream-rules-live.md) | Where the stream rules live | NOTE | reclassified: a placement, not a decision |
| [0004](DEC-0004-ci-red-on-empty-targets.md) | CI red on empty targets | BLOCKING | answered: every gate is made meaningful on an empty target |
| [0005](DEC-0005-w12-is-not-a-suite-check.md) | W-12 is not a check the suite can run | DEFECT | corrected: the suite runs W-01 to W-11 and reports the removal test as pending |
| [0006](DEC-0006-gates-assumed-an-installed-environment.md) | The gates assumed an installed environment | DEFECT | corrected: every gate target ensures its environment; `make doctor` checks what the gates invoke |
| [0007](DEC-0007-the-shared-kernel-is-a-checked-binding.md) | The shared kernel is a checked binding, not generated code | DEFECT | corrected: hand-written bindings held to the schemas by `tests/contract` |
| [0008](DEC-0008-the-frame-names-allowed-hosts.md) | The execution frame names allowed hosts, not forbidden ones | DEFECT | corrected: `frame.allowed_hosts` replaces `frame.forbidden`; check W-13 |
| [0009](DEC-0009-credentials-are-parameters.md) | The credential register lists parameters, not deployment names | DEFECT | corrected: every row of `CREDENTIALS.md` is a parameter with purpose, permissions, rotation and its configuration key |
| [0010](DEC-0010-commands-show-the-invocation-that-works.md) | Every command shows the invocation that works | DEFECT | corrected: `uv run` wherever the project environment is involved; the rule is in the conventions |
| [0011](DEC-0011-no-worker-code-in-the-control-plane-image.md) | No worker code in the control plane image | DEFECT | corrected: the reference worker has its own image; `compose.yml` is Taktus and PostgreSQL; `compose.reference-worker.yml` is the development layer; a check fails on worker code in the control plane image |
| [0012](DEC-0012-the-limit-guarantee-holds-per-consumption-kind.md) | The limit guarantee holds per consumption kind | DEFECT | corrected: ADR-0005 names the kinds — tokens, quota, compute per step — for which no limit is breached, and states that a currency limit degrades to an estimate where money is reported per assignment |
| [0013](DEC-0013-a-provisional-operator-identity.md) | A provisional operator identity until the identity component exists | NOTE | recorded: one configured identity per tenant (`TAKTUS_PROVISIONAL_IDENTITY`), marked provisional everywhere it appears; the identity component (`0.2.0`) replaces it and removes the variable |
| [0014](DEC-0014-behaviour-changes-inside-an-agreed-scope.md) | Behaviour changes inside an agreed scope | NON-BLOCKING | answered: Option B — entry M2.4, a notice per behaviour change; and every notice carries a kind, so that a weakened gate stays distinguishable |
| [0015](DEC-0015-the-owner-facing-section-in-german.md) | The owner-facing section in German | NON-BLOCKING | answered: Option A — English, as the rule stands; the section is generated and checked |
| [0016](DEC-0016-the-first-runs-variables-are-not-in-env-example.md) | The first run's variables are not in `.env.example` | DEFECT | corrected: `REPOSITORY_TOKEN_FILE`, `CODING_AGENT_API_KEY_FILE` and `CODING_AGENT_SESSION_FILE` are listed in `.env.example`; the front page no longer counts the ADRs by hand |
| [0017](DEC-0017-ci-had-no-base-on-the-first-push-of-a-branch.md) | CI had no base on the first push of a branch | DEFECT | corrected: the documentation gate and the status gate compare with `main` on the first push of a `taktus/**` branch, where the push's "before" is the null sha |
| [0018](DEC-0018-one-pattern-for-every-credential-variable.md) | One pattern for every credential variable | DEFECT | corrected: every credential's file is named `TAKTUS_CREDENTIAL_<NAME>_FILE`, the same variable whoever reads it; the pattern is stated once in `CREDENTIALS.md` |
| [0019](DEC-0019-the-model-for-the-reasoning-purpose.md) | The model for the purpose `reasoning` | NON-BLOCKING | answered: Option A — the smaller model of the family, the cheapest that does the job; method selection applied within the method, revisited on the evidence of the runs |
| [0020](DEC-0020-a-branch-the-connector-writes-loses-the-file-mode.md) | A branch the connector writes loses the file mode | DEFECT | corrected: a file keeps the mode it has in the base, read from the base tree before the new tree is written; a new file is a plain file, and issue #28 carries what that still costs |
| [0022](DEC-0022-the-endpoint-worker-isolates-nothing-and-said-so-nowhere.md) | The endpoint worker isolates nothing, and the operator was not told | DEFECT | corrected: `endpoint` carries whatever isolation the person who started the worker gave it, `tools/first_run.sh` gives it none, and ADR-0002's rule reaches only the adapters that start a unit |
| [0023](DEC-0023-where-taktus-runs-and-what-separates-it.md) | Where Taktus runs, and what separates it from what it builds | NON-BLOCKING | answered: Option A — one cluster on the owner's integration server, control plane and execution in namespaces of their own; a kernel boundary protects nothing that is at risk while both the code and the data are the owner's, and the record names the three situations that would change that |
| [0024](DEC-0024-adr-0025-asked-how-many-instances.md) | ADR-0025 asked how many instances, not who owns what runs | DEFECT | corrected: the permission is to run on infrastructure administered by anyone that is not this instance — a person, an organisation or another instance — and its conditions are about the boundary, not about a count of clusters |
| [0025](DEC-0025-the-pull-request-taktus-opens-cannot-pass-the-description-checks.md) | The pull request Taktus opens could not pass the description checks | DEFECT | corrected: the body is `Closes`, Taktus's own statement and then the worker's summary, with nothing after it, and the summary is asked to be the description in the shape the repository prescribes |
