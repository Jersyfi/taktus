# Status

**As of:** 2026-09-23
**Accounts for:** `main` after #22, and the pull requests that write this version (#23, #26)
**Kept current by:** every pull request that changes the state of the project; `make
gate-status` fails when this file was not touched by one that did, and when section 3 differs
from the register

This is the one file that says where the project stands and what is needed from the owner.
It states facts. Where something is not known, it says so. The roadmap (`docs/roadmap.md`)
says what each milestone must reach; this file says how far the current one has got, checked
against the code and the tests, not against what earlier descriptions claimed.

## 1. Where the project is

**Current milestone: `0.1.0` — control-plane minimum. Not complete.**

The milestone is complete when two things hold. The first holds. The second does not.

1. *Every step carries method, exactness class and consumption.* **Holds.** Every step of the
   three bundles that exist (`P-02`, `P-03` of dev-orchestration; `S-01` of self-operation)
   carries its method, the reason, the alternatives rejected, a fallback where the method
   varies, and an exactness class; `tests/exactness` holds the bundles to the rules, and every
   step run records what it consumed.
2. *Taktus turns one of its own issues into a pull request that passes CI.* **Has not
   happened yet; nothing is missing for it any more.** No issue of this repository has ever
   been turned into a pull request by Taktus end to end. The closest so far, on 2026-09-19
   (`docs/runs/2026-09-19-the-run-that-stopped.md`): P-02 ran against the real repository through the
   reference connector
   up to its language-model step and stopped there, because no model endpoint was configured;
   P-03 ran up to its admission check and stopped there, correctly, because P-02 had not
   written the criteria. Pull request #12 was opened by the connector's live idempotency test,
   not by a process, and was closed by the test. The coding worker has never run against its
   real agent inside a run.

   What has changed with #23 is that the three things the run was waiting for are in place. The owner provided the coding agent's key, the repository token and the model
   endpoint on 2026-09-22; #23 wires them into `.env` under one naming pattern (DEC-0018),
   confirms each with its own section 7 (all three answered `200` on 2026-09-23), records the
   model chosen for the purpose `reasoning` (DEC-0019), and raises the two renewals the
   validities make foreseeable (NEED-0005, NEED-0006).

   `tools/first_run.sh 11` then ran, on 2026-09-23. **P-02 completed**: it read the issue,
   derived the acceptance criteria with the model and wrote them as a comment on issue #11 —
   the first outward effect Taktus has produced from a process. **P-03 did not**: the coding
   worker implemented the issue correctly, the run put the change on the branch
   `taktus/issue-11`, and every job of the pipeline failed on its first line, because the
   branch the connector wrote had dropped the executable bit of a file the change touched.
   The step `verify` refused the change on that verdict, correctly, and no pull request was
   opened. That defect is DEC-0020 and is corrected in this pull request (#26), with a test
   that fails without the fix; two further findings of the same run are DEC-0021 and DEC-0022.
   The run's own report, with what every step consumed against what was estimated, is
   `docs/runs/first-run.md`, written by the pull request that follows this one.

**What the second half was waiting for**, in the order a run meets it, and where each stands:

| What | What it is for | State |
|---|---|---|
| a model endpoint that speaks the chat-completions dialect, and its key where it needs one | P-02's step `refine` (`llm`, purpose `reasoning`) derives the acceptance criteria | provided 2026-09-22, confirmed 2026-09-23 (NEED-0003, issue #20 closed); the model is the smaller one of the family, by the owner's choice (DEC-0019) |
| a credential for the coding agent — an API key or a subscription token | P-03's step `implement` (`worker`) runs the coding worker against its real agent | provided 2026-09-22 as an API key, confirmed 2026-09-23 (NEED-0001, issue #18 closed); valid 30 days, renewed under NEED-0005 |
| a repository token issued for the identity Taktus acts as | every read and write of the reference connector; the first run used the developer's own login, which is not what the owner's run should use | provided 2026-09-22 as a fine-grained token for this repository, confirmed 2026-09-23 (NEED-0002, issue #19 closed); valid 90 days, renewed under NEED-0006 |

With those three in place, `tools/first_run.sh 11` is the one command that runs P-02 and
then P-03 for issue #11 and opens the pull request; CI runs on the branch P-03 creates since
#13 was merged. Whether that run passes CI is unknown until it has happened: the pipeline's
verdict on a branch the coding worker produced has never been read for real, and the first
push of such a branch would have failed the documentation gate for lack of a comparison base
until DEC-0017 corrected it in #22 — found by reading, not by a run.

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

**Decided since the last version:** DEC-0020 (#26): a branch the connector writes keeps the
mode each file has in the base, so that an executable a change touches stays executable.
DEC-0022 (#26): the `endpoint` execution kind isolates nothing of its own, `tools/first_run.sh`
gives it none, and ADR-0002's isolation rule reaches only the adapters that start a unit.
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
2. **This one (#26).** The three findings of the first live run: the branch write that dropped
   a file's mode and killed the pipeline (DEC-0020, corrected with a test), the question of
   whether a pull request Taktus opens must carry a status update (DEC-0021, open, provisional
   answer in force), and the isolation the endpoint worker does not provide and nobody said so
   (DEC-0022, corrected). Without the first, no pull request Taktus opens can ever pass its
   own pipeline.
3. **The first live run's report**, `docs/runs/first-run.md`: what happened, what each step
   consumed against what was estimated, every point where a person had to step in, and what
   the real agent and the real pipeline verdict revealed about the bundles. It is written
   once the repeated run has finished, and it says whether `0.1.0`'s completion criterion is
   met.
4. **Deployment on the target platform**: the cluster execution adapter, the image build and
   the chart under `deploy/k8s`, built against the platform's current interface. It comes
   after the live run because a deployment of something that has never completed a run proves
   nothing about the deployment.
5. **`0.2.0` starts with the budget** (ADR-0005, second amendment: the estimate reserved at
   admission, a currency budget converted into tokens and enforced there) and **the scheduler
   starting runs from a bundle's trigger**, so that the removal test runs weekly without a
   workflow. In that order because the budget is designed and the design is what the first live
   run will spend against.

## 3. Needed from the owner

Every open needs request and decision request, the most urgent first. A needs request is
something only the owner can provide — a credential, an account, access, a purchase, an action,
information. A decision request is a question only the owner can answer. Each has an issue
assigned to the owner with the steps.

<!-- generated by tools/check_status.py from docs/decisions/open/; `make generate` writes it -->
| Record | What | Needed by | Kind | Issue |
|---|---|---|---|---|
| NEED-0004 | The platform's current interface note | 2026-10-12 | information | #21 |
| NEED-0005 | Renew the coding agent's key | 2026-10-15 | credential | #24 |
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
| deployment against the target platform | NEED-0004: the platform's current interface — the values keys, the names of the secret parameters, the namespaces, the egress mechanism, the webhook path — shape only | the platform changed since it was last described; the repository never held that description; needed by 2026-10-12 |
| a removal-test verdict of *broke* on a real process, and *changed* through an alternative adapter | a second adapter for a capability a process uses; nothing today has one | #14 |

The first live end-to-end run is no longer blocked: NEED-0001, NEED-0002 and NEED-0003 were
provided on 2026-09-22 and confirmed on 2026-09-23. It was blocked from #8, #10 and #13 — where
each need was foreseeable and stated only as a note — until #22 raised the needs and #23 wired
them: seventeen days from the first foreseeable moment to the credential, of which two were
between the request and the answer.

Nothing else is blocked. Everything not listed here can be built by a session without the
owner.

## 5. Promises not yet kept

What the repository says will hold and does not hold yet: tests pending, limits documented
rather than enforced, anything marked provisional.

| Promise | Where it is made | State |
|---|---|---|
| the removal test is a conformance check, W-12 and C-10 | `contracts/worker/v1`, `contracts/connector/v1` | reported *pending* by both suites (DEC-0005); the test runs as the process S-01 instead, and no adapter has reached maturity *verified* because nothing records the conformance half |
| a budget is a budget: the estimate reserved at admission, a currency budget enforced in tokens, a named safety margin | ADR-0005, second amendment | designed, not implemented; `0.2.0`. Today admission control checks the estimate against the limit and money is reported at the end of an assignment |
| a process that would give an instance credentials for its own infrastructure is refused at planning time | ADR-0025 | applied by the person who configures an instance; refusal in code is `0.2.0` |
| an anchor halts the run at a step boundary and raises a decision request in the product | ADR-0008, `docs/architecture/governance.md` | the register exists for this repository; the product's governance component holds the "has it left the system" predicate of the correction anchor and nothing else (`src/taktus/components/governance`); anchors at step boundaries are `0.2.0` |
| the identity component | `docs/architecture/control-plane.md` §2 | a provisional identity per tenant, marked on every line it touches (DEC-0013); `0.2.0` removes the variable |
| several instances with load spread across them, a restart without data loss | ADR-0013 A | proven for one instance; the election of a scheduler is proven with two; runners on several instances are `0.2.0` |
| the coding worker's boundaries lie between tool calls; a stop inside a tool call waits up to the ceiling; money is known only at the end | `workers/claudecode/README.md` | documented limits of the agent, not enforced by Taktus; admission control on a currency limit works against the estimate only |
| the weekly removal test runs weekly | `blueprints/self-operation/README.md` | has run once, by hand; the workflow's first scheduled run is 2026-09-28 |
| exactness is a result, not a switch: the exactness statement | UC-4.13, UC-6.9 | specified; `0.5.0` |
| result defects are detected and remediated under the correction anchor | ADR-0021 to ADR-0023 | the terms and the anchor exist; detection and repair are `0.5.0` |
| the model contract has a schema and a conformance suite | `contracts/model/v1/README.md` | not written; the port is held to nothing but its tests |
| `deploy/k8s`, `contracts/events/v1`, `blueprints/it-operations` | their README files | placeholders |
| a live run of the coding worker in CI | `docs/roadmap.md` | the gate runs the stand-in; unchanged until CI has a credential, which is a decision not yet raised |
| the components `accounting`, `decision`, `identity`, `knowledge`, `value` | `docs/architecture/project-structure.md` | packages with an `__init__.py` and nothing else |
| every credential's file variable follows `TAKTUS_CREDENTIAL_<NAME>_FILE` | `CREDENTIALS.md`, DEC-0018 | true in the tree, enforced by reading. The coverage gate fails a variable the register does not describe; it does not check the *shape* of the name, so a seventh variable could break the pattern again without a red gate |
