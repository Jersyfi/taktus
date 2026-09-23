# Status

**As of:** 2026-09-23
**Accounts for:** `main` after #22, and the pull requests that write this version (#23, #26, #39, #40)
**Kept current by:** every pull request that changes the state of the project; `make
gate-status` fails when this file was not touched by one that did, and when section 3 differs
from the register

This is the one file that says where the project stands and what is needed from the owner.
It states facts. Where something is not known, it says so. The roadmap (`docs/roadmap.md`)
says what each milestone must reach; this file says how far the current one has got, checked
against the code and the tests, not against what earlier descriptions claimed.

## 1. Where the project is

**Current milestone: `0.1.0` — control-plane minimum. Its completion criterion is met; the
milestone's own list of items is not finished.**

The milestone is complete when two things hold. **Both now do**, since 2026-09-23. What is
left of the milestone's own list of items is below, and none of it is part of the criterion.

1. *Every step carries method, exactness class and consumption.* **Holds.** Every step of the
   three bundles that exist (`P-02`, `P-03` of dev-orchestration; `S-01` of self-operation)
   carries its method, the reason, the alternatives rejected, a fallback where the method
   varies, and an exactness class; `tests/exactness` holds the bundles to the rules, and every
   step run records what it consumed.
2. *Taktus turns one of its own issues into a pull request that passes CI.* **Holds, since
   2026-09-23.** Issue #11 became pull request
   [#38](https://github.com/Jersyfi/taktus/pull/38), opened by Taktus through P-03
   Implementation, with every check of that pull request green and the merge left to a person.
   The record is `docs/runs/first-run.md`.

   **How it got there.** The owner provided the coding agent's key, the repository token and
   the model endpoint on 2026-09-22; #23 wired them into `.env` under one naming pattern
   (DEC-0018), confirmed each with its own section 7, recorded the model chosen for the purpose
   `reasoning` (DEC-0019) and raised the two renewals the validities make foreseeable
   (NEED-0005, NEED-0006). `tools/first_run.sh 11` then ran.

   **P-02 ran once, in six seconds**: it read the issue, derived seven acceptance criteria with
   the model and wrote them as a comment — the first outward effect a Taktus process has
   produced. **P-03 needed eight attempts and about $6.10.** Seven failed: four on defects in
   Taktus (DEC-0020, DEC-0021, DEC-0025, the last of them over four attempts) and one on a
   flaky test in this repository's own pipeline (issue #29). **None failed on the change**,
   which the coding worker got right on the first attempt and on every attempt after. The
   ledger chain and the provenance chain verify across 369 entries and all eight runs.

   **The first numbers.** The report carries consumption per step, estimate against actual,
   and they are the calibration point ADR-0005's budget and ADR-0010's Takt have been waiting
   for: the worker's estimate is a configured constant that under-states input tokens by up to
   4.3×, over-states output by up to 70×, and was exceeded on money once; across eight runs of
   the *same* brief the cost varied by 2.4× and the duration by 2.7×; `wait-for-pipeline` was
   64 % of the run's wall clock; and an `llm` step passes admission with no estimate at all.

   Two things that criterion does **not** say, and this run did not prove: the coding worker
   ran unisolated by endpoint, so `frame.allowed_hosts` was declared and not enforced
   (DEC-0022); and the state was a file snapshot, not a database.

**The three credentials the second half was waiting for**, and where each stands:

| What | What it is for | State |
|---|---|---|
| a model endpoint that speaks the chat-completions dialect, and its key where it needs one | P-02's step `refine` (`llm`, purpose `reasoning`) derives the acceptance criteria | provided 2026-09-22, confirmed 2026-09-23 (NEED-0003, issue #20 closed); the model is the smaller one of the family, by the owner's choice (DEC-0019) |
| a credential for the coding agent — an API key or a subscription token | P-03's step `implement` (`worker`) runs the coding worker against its real agent | provided 2026-09-22 as an API key, confirmed 2026-09-23 (NEED-0001, issue #18 closed); valid 30 days, renewed under NEED-0005 |
| a repository token issued for the identity Taktus acts as | every read and write of the reference connector; the first run used the developer's own login, which is not what the owner's run should use | provided 2026-09-22 as a fine-grained token for this repository, confirmed 2026-09-23 (NEED-0002, issue #19 closed); valid 90 days, renewed under NEED-0006 |

`tools/first_run.sh 11` is the one command that runs P-02 and then P-03 for issue #11 and
opens the pull request. It cannot be run a second time — P-02 refuses an issue whose criteria
it has already written, correctly, and the script stops with it (issue #30) — which is why the
seven repeats were started by hand.

**Done in `0.1.0`**, checked against the tree: the contracts for the worker and the connector
as executable schemas with conformance suites that a third party can run (`contracts/worker`,
`contracts/connector`, `src/taktus/conformance`); the process bundle contract and the shared
kernel (`contracts/process`, `contracts/shared`); command, plan, process version, run, ledger
and provenance in the control plane, in memory and in PostgreSQL, with restart at the last step
boundary proven for one instance; the daemon with four roles, claims with a lease, an elected
scheduler and a shutdown at the step boundary; the execution port with the `process` and
`container` adapters; two workers in their own images — the reference `script` worker and the
coding worker, the latter passing the suite in both authentication modes against a stand-in for
its agent; the reference repository connector in both directions, proven against the real
service; the loopback connector and the removal test as a process (`S-01`), run once by hand;
the model port with one adapter over the chat-completions dialect; OpenTelemetry spans with the
trace identifier on every ledger entry; the architecture tests and seven `import-linter`
contracts; the command line `taktusctl`; self-hosting in two containers with `make up`, proven
from nothing; the decision register with four anchor modes, notices and their gates; every ADR
bounded by *Where this promise ends*, with a gate.

**Not done in `0.1.0`**, from the milestone's own list:

| Item | State |
|---|---|
| `mlbench` worker | does not exist; its real work is `0.4.0` |
| the model contract as a schema with a conformance suite | `contracts/model/v1` is a README that says the schema is not yet written; the port and one adapter exist |
| the events contract | `contracts/events/v1` is a placeholder |
| the cluster execution adapter | does not exist; the port and two adapters do |
| the container registry build and the Helm chart | `deploy/k8s` is a placeholder; images are built locally by `make up` and by the tests |
| the identity component | a provisional identity per tenant stands in (`TAKTUS_PROVISIONAL_IDENTITY`, DEC-0013) |
| time triggers | the scheduler leads and ticks; nothing is scheduled; the weekly removal test is a CI workflow instead |
| event reactions | the automation role starts and waits; the outbox exists and nothing writes it; an intake event is completed into a command by hand |
| a live run of the coding worker against its real agent in CI | the gate runs the stand-in; a live run needs a credential CI does not have |
| governance and anchors in the product | the anchors exist for this repository as documents; nothing in the product evaluates an anchor at a step boundary yet |

**Decided since the last version:** DEC-0023 (#40): Taktus runs on the owner's integration
server, control plane and execution in namespaces of one cluster — a kernel boundary between
them protects nothing that is at risk while both the code and the data are the owner's, and
the record names the three situations that would change that. DEC-0024 (#40): ADR-0025's
permission names any administrator that is not this instance, including a person, and its
conditions are about the boundary rather than a count of clusters. DEC-0020 (#26): a branch the connector writes keeps the
mode each file has in the base, so that an executable a change touches stays executable.
DEC-0022 (#26): the `endpoint` execution kind isolates nothing of its own, `tools/first_run.sh`
gives it none, and ADR-0002's isolation rule reaches only the adapters that start a unit.
DEC-0025 (#26): the description P-03 writes carries the sections this repository's checks
require, and the worker's summary is the description.
DEC-0018 (#23): one pattern for every
credential file variable, `TAKTUS_CREDENTIAL_<NAME>_FILE`, whoever reads it — a documentation
defect, corrected, with the operator-visible half recorded as the notice NTC-0003. DEC-0019 (#23):
the purpose `reasoning` is served by the smaller model of the family, the cheapest that does
the job, revisited on the evidence of the runs. **Open:** DEC-0021 (#26, issue #27) — must a
pull request Taktus opens carry a status update like any other? Provisionally yes; the work
continues on that answer.

**The weekly removal test** (`.github/workflows/removal-test.yml`, Mondays 06:00 UTC) was
merged on 2026-09-21 after that day's hour had passed. It has not run yet. Its first scheduled
run is 2026-09-28.

## 2. The next pull requests

1. **#23**, which wires the three provided credentials into `.env` under one naming pattern,
   each confirmed by its own section 7, records the model choice, and raises the two renewals.
   Without it the credentials sit in files nothing reads.
2. **#26.** The four findings of the first live run: the branch write that dropped
   a file's mode and killed the pipeline (DEC-0020, corrected with a test), the question of
   whether a pull request Taktus opens must carry a status update (DEC-0021, open, provisional
   answer in force), and the isolation the endpoint worker does not provide and nobody said so
   (DEC-0022, corrected), and the description P-03 wrote that this repository's own checks
   refused (DEC-0025, corrected). Without the first and the last, no pull request Taktus opens
   can pass its own pipeline.
3. **This one (#39).** The first live run's report, `docs/runs/first-run.md`: what happened,
   what each step consumed against what was estimated, every point where a person had to step
   in, what was slow or surprising, and what the removal test shows now that real processes
   stand behind it. Run records move into `docs/runs/` (NTC-0004). Without it the only record
   of the day is eight closed pull requests and a ledger.
4. **This one (#40).** Where Taktus runs and what separates it from what it builds, recorded
   with what would change it (DEC-0023); ADR-0025 corrected to say that the rule is about who
   administers what runs and not about how many clusters there are (DEC-0024); and
   `deploy/k8s/README.md` as the specification for the pull request that builds the chart, the
   registry build and the cluster execution adapter. NEED-0004 is closed as superseded, and the
   two things the inspection showed are needed are raised as NEED-0007 and NEED-0008.
5. **The deployment itself**: the chart, the registry build and the cluster execution
   adapter, against the plan of #4 and the platform as the read-only inspection of 2026-09-23
   found it.
6. **`0.2.0` starts with the budget** (ADR-0005, second amendment: the estimate reserved at
   admission, a currency budget converted into tokens and enforced there) and **the scheduler
   starting runs from a bundle's trigger**, so that the removal test runs weekly without a
   workflow. The budget now has measurements to be built against, and §1 says what they are.

## 3. Needed from the owner

Every open needs request and decision request, the most urgent first. A needs request is
something only the owner can provide — a credential, an account, access, a purchase, an action,
information. A decision request is a question only the owner can answer. Each has an issue
assigned to the owner with the steps.

<!-- generated by tools/check_status.py from docs/decisions/open/; `make generate` writes it -->
| Record | What | Needed by | Kind | Issue |
|---|---|---|---|---|
| NEED-0005 | Renew the coding agent's key | 2026-10-15 | credential | #24 |
| NEED-0007 | A kubeconfig for the deployment identity | 2026-10-20 | access | #41 |
| NEED-0008 | A public name for the Taktus instance | 2026-10-20 | information | #42 |
| DEC-0021 | Must a pull request Taktus opens update the status report? | 2026-10-21 | NON-BLOCKING | #27 |
| NEED-0006 | Renew the repository connector's token | 2026-12-14 | credential | #25 |
<!-- end generated -->

The three credentials (NEED-0001 to NEED-0003) are one set: the first live run needs all of
them, and one without the others changes nothing. Each names the file to create and the line
to add to `.env`; none asks for a value anywhere a session can read it. NEED-0004 is
information, not a secret, and goes into a private place, not this repository. No decision
request is open.

## 4. Blocked

| What | On what | Since |
|---|---|---|
| installing the deployment, once its pull request has written it | NEED-0007: a kubeconfig for a deployment identity, so that the install needs no shell on the machine | the platform was inspected on 2026-09-23 and its interface is reachable from outside, which makes the narrow credential both possible and the better arrangement; needed by 2026-10-20 |
| the instance's ingress, its certificate and the webhook | NEED-0008: a public name for the instance | the same inspection; needed by 2026-10-20. Without it the chart renders with the ingress switched off and the instance keeps polling instead of reacting to events |
| a removal-test verdict of *changed* through an alternative adapter | a second adapter for a capability a process uses; nothing today has one | #14. The *broke* verdict on a real process is no longer missing: the run of 2026-09-23 produced it for `connector.channel.repo`, naming eight steps across P-02 and P-03 |

The first live end-to-end run is no longer blocked and has happened. It was blocked from #8,
#10 and #13 — where each need was foreseeable and stated only as a note — until #22 raised the
needs and #23 wired them: seventeen days from the first foreseeable moment to the credential,
of which two were between the request and the answer. That is the cost the timing rule of
ADR-0028 exists to prevent, measured.

**Writing** the deployment is not blocked: the plan is `deploy/k8s/README.md`, built against a
platform that was read in full on 2026-09-23. Only installing it is.

Nothing else is blocked. Everything not listed here can be built by a session without the
owner.

## 5. Promises not yet kept

What the repository says will hold and does not hold yet: tests pending, limits documented
rather than enforced, anything marked provisional.

| Promise | Where it is made | State |
|---|---|---|
| the removal test is a conformance check, W-12 and C-10 | `contracts/worker/v1`, `contracts/connector/v1` | reported *pending* by both suites (DEC-0005); the test runs as the process S-01 instead, and no adapter has reached maturity *verified* because nothing records the conformance half |
| the removal test *exercises* the processes that use an integration | `blueprints/self-operation/`, S-01 | it **resolves** them statically. Every real process of this repository writes outward, so none was rehearsed on 2026-09-23 (`not run: step(s) would leave the system`). The rehearsal half has never run against a real process, and on this repository cannot |
| a removal verdict says what it was taken under | `blueprints/self-operation/` | it does not: `worker.endpoint` reported "no registered process uses this integration" because the instance happened to be configured with the reference worker, and neither the ledger entry nor the maturity record says which adapter stood behind the name (issue #36) |
| a budget is a budget: the estimate reserved at admission, a currency budget enforced in tokens, a named safety margin | ADR-0005, second amendment | designed, not implemented; `0.2.0`. Today admission control checks the estimate against the limit and money is reported at the end of an assignment. Measured on 2026-09-23: an `llm` step is admitted with **no estimate at all**; the worker's estimate is a configured constant, wrong by 1.8×–4.3× on input tokens and 30×–70× on output, and exceeded once on money; and money is not a function of the tokens reported, so a currency budget cannot be converted back into tokens from what is recorded (`docs/runs/first-run.md` §2) |
| a process that would give an instance credentials for its own infrastructure is refused at planning time | ADR-0025 | applied by the person who configures an instance; refusal in code is `0.2.0` |
| an anchor halts the run at a step boundary and raises a decision request in the product | ADR-0008, `docs/architecture/governance.md` | the register exists for this repository; the product's governance component holds the "has it left the system" predicate of the correction anchor and nothing else (`src/taktus/components/governance`); anchors at step boundaries are `0.2.0` |
| the identity component | `docs/architecture/control-plane.md` §2 | a provisional identity per tenant, marked on every line it touches (DEC-0013); `0.2.0` removes the variable |
| several instances with load spread across them, a restart without data loss | ADR-0013 A | proven for one instance; the election of a scheduler is proven with two; runners on several instances are `0.2.0` |
| the coding worker's boundaries lie between tool calls; a stop inside a tool call waits up to the ceiling; money is known only at the end | `workers/claudecode/README.md` | documented limits of the agent, not enforced by Taktus; admission control on a currency limit works against the estimate only |
| `frame.allowed_hosts` names the hosts a unit may reach | DEC-0008, `contracts/worker/v1` | enforced by the `container` adapter through a per-job egress proxy. With the `process` and `endpoint` kinds it is declared and not enforced, and `tools/first_run.sh` uses `endpoint` — so the first live run's worker reached whatever the machine could (DEC-0022) |
| the weekly removal test runs weekly | `blueprints/self-operation/README.md` | has run twice, both times by hand — 2026-09-21 with one example process, 2026-09-23 with P-02 and P-03 registered; the workflow's first scheduled run is 2026-09-28 |
| exactness is a result, not a switch: the exactness statement | UC-4.13, UC-6.9 | specified; `0.5.0` |
| result defects are detected and remediated under the correction anchor | ADR-0021 to ADR-0023 | the terms and the anchor exist; detection and repair are `0.5.0` |
| the model contract has a schema and a conformance suite | `contracts/model/v1/README.md` | not written; the port is held to nothing but its tests |
| `contracts/events/v1`, `blueprints/it-operations` | their README files | placeholders |
| `deploy/k8s` renders a chart | `deploy/k8s/README.md` | **a specification, not a chart.** The file is the plan the next pull request builds: the values keys, two namespaces with a restricted admission policy, default-deny network policies both ways, no service-account token in a job, a limit and a deadline on every job, and the egress proxy that makes a host list mean something. Nothing under `deploy/k8s/` renders yet |
| the cluster execution adapter | ADR-0002's execution table, `deploy/k8s/README.md` | does not exist; the port and two adapters do. The plan says what it must refuse: a job it cannot give limits to, and a frame whose hosts it cannot enforce |
| a live run of the coding worker in CI | `docs/roadmap.md` | the gate runs the stand-in; unchanged until CI has a credential, which is a decision not yet raised. The worker has now run live eight times outside CI (`docs/runs/first-run.md`) |
| the components `accounting`, `decision`, `identity`, `knowledge`, `value` | `docs/architecture/project-structure.md` | packages with an `__init__.py` and nothing else |
| every credential's file variable follows `TAKTUS_CREDENTIAL_<NAME>_FILE` | `CREDENTIALS.md`, DEC-0018 | true in the tree, enforced by reading. The coverage gate fails a variable the register does not describe; it does not check the *shape* of the name, so a seventh variable could break the pattern again without a red gate |
