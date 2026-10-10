# Status

**Kept current by:** every pull request that changes the state of the project; `make
gate-status` fails when this file was not touched by one that did, when section 3 stores a list
instead of saying where it is (DEC-0026), and when the file carries a line every pull request
rewrites — a date, a running list of decisions (DEC-0027). How current it is: the date of its last
commit. What was decided when: the register's index, `docs/decisions/README.md`.

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
   four bundles that exist (`P-01`, `P-02`, `P-03` of dev-orchestration; `S-01` of self-operation)
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
   64 % of the run's wall clock; and an `llm` step passes admission with no estimate at all. The
   output figures may be undercounted: the coding worker counted a message's tokens once, on its
   first line (DEC-0038, corrected since).

   Two things that criterion does **not** say, and this run did not prove: the coding worker
   ran unisolated by endpoint, so `frame.allowed_hosts` was declared and not enforced
   (DEC-0022); and the state was a file snapshot, not a database.

**The three credentials the second half was waiting for**, and where each stands:

| What | What it is for | State |
|---|---|---|
| a model endpoint that speaks the chat-completions dialect, and its key where it needs one | P-02's step `refine` (`llm`, purpose `reasoning`) derives the acceptance criteria | provided 2026-09-22, confirmed 2026-09-23 (NEED-0003, issue #20 closed); the model is the smaller one of the family, by the owner's choice (DEC-0019) |
| a credential for the coding agent — an API key or a subscription token | P-03's step `implement` (`worker`) runs the coding worker against its real agent | provided 2026-09-22 as an API key, confirmed 2026-09-23 (NEED-0001, issue #18 closed); renewed under NEED-0005 on 2026-10-07, without expiry |
| a repository token issued for the identity Taktus acts as | every read and write of the reference connector; the first run used the developer's own login, which is not what the owner's run should use | provided 2026-09-22 as a fine-grained token for this repository, confirmed 2026-09-23 (NEED-0002, issue #19 closed); renewed under NEED-0006 on 2026-10-07, without expiry |

`tools/first_run.sh 11` is the one command that runs P-02 and then P-03 for issue #11 and
opens the pull request. On the first run it could not be run a second time, which is why the
seven repeats were started by hand; since the pull request that took up the first run's
findings it runs one bundle alone, resumes a stopped run, treats P-02's refusal of an issue
that has nothing to write for as done, and stops before anything starts when a branch of an earlier
attempt exists (issue #30).

**The first run's findings, taken up.** Every finding of `docs/runs/first-run.md` that was an
issue is closed by that pull request, each with what it cost the run: #28, a new executable
arriving plain — not met, nothing; #29, the flaky memory test — attempt 3, $0.833 and 166 s of
a correct change refused; #30 — seven attempts started by hand and seven branches deleted by
hand; #31, the resume that could not resume — the whole process run again after the pipeline
turned green; #34, a generated section asked of a model — part of DEC-0025's four refused
descriptions, $3.48 of coding-step money; #36, a removal verdict that said too little — a
misleading row every week. The four budget findings are the subject of the ADR-0005 amendment
below.

**Done in `0.1.0`**, checked against the tree: the Helm chart (`deploy/k8s/chart`), rendered and held to least privilege by a test, and the workflow that builds the release images on a tag (#64), the coding worker's among them with its agent pinned to one exact version that the live test installs too (#116, NTC-0072); the contracts for the worker and the connector
as executable schemas with conformance suites that a third party can run (`contracts/worker`,
`contracts/connector`, `src/taktus/conformance`); the process bundle contract and the shared
kernel (`contracts/process`, `contracts/shared`); command, plan, process version, run, ledger
and provenance in the control plane, in memory and in PostgreSQL, with restart at the last step
boundary proven for one instance; the daemon with four roles, claims with a lease, an elected
scheduler and a shutdown at the step boundary; the execution port with the `process` and
`container` adapters; two workers in their own images — the reference `script` worker and the
coding worker, the latter passing the suite in both authentication modes against a stand-in for
its agent; the reference repository connector in both directions, proven against the real
service, and acting as Taktus's own app when configured (ADR-0033); the loopback connector and the removal test as a process (`S-01`), run once by hand;
the model contract as a schema with a conformance suite (`contracts/model/v1`, M-01 to M-04):
what an adapter can compute before a call, the price table, and the model port with one adapter
over the chat-completions dialect; OpenTelemetry spans with the
trace identifier on every ledger entry; the architecture tests and seven `import-linter`
contracts; the command line `taktusctl`; self-hosting in two containers with `make up`, proven
from nothing; the decision register with four anchor modes, notices and their gates, the Python tools that run those gates type-checked by `make lint` as strictly as the product (NTC-0076), on the interpreter the image runs (NTC-0101); every ADR
bounded by *Where this promise ends*, with a gate. `make doctor` reports `git` as a required tool, and
`make gate-docs` checks for it before it runs (issue #11, the change Taktus itself opened as #38).
The identity component, in place of the provisional operator identity of DEC-0013 (#82,
ADR-0040): a sender is placed by the link of their account, made by the person with a link code
from their Taktus account or by the organisation's identity source behind a port; an unknown
sender is answered in the channel through the connector's reply operation and kept nowhere;
`taktusctl identity` adds identities and lists and revokes links, each a ledger entry; the
command line names an identity the tenant knows, and a schedule acts for whoever activated the
version (NTC-0080, NTC-0081). `TAKTUS_PROVISIONAL_IDENTITY` is gone.

**Not done in `0.1.0`**, from the milestone's own list:

| Item | State |
|---|---|
| `mlbench` worker | does not exist; its real work is `0.4.0` |
| the events contract | `contracts/events/v1` is a placeholder |
| the cluster execution adapter | built (#65): `TAKTUS_EXECUTION=cluster`, held to `deploy/k8s/README.md` §4 to §7 against a fake of the cluster's API. It has not run on a real cluster: those tests skip until NEED-0015 gives them a namespace of their own. Its Role is wider than §1 first said — Secrets and Services too (DEC-0061) — and the chart renders that Role |
| time triggers | built (#69, ADR-0035): the elected scheduler fires a bundle's schedule triggers once per slot, missed slots coalesce, every started run carries `run.triggered`; proven with two schedulers and a leader restart on a clock the test sets, and S-01 runs from its weekly trigger once per listed integration (`tests/integration/test_time_triggers.py`). No installed instance runs it yet, so the weekly removal test is still the CI workflow |
| event reactions | the automation role starts and waits; the outbox exists and nothing writes it; an intake event is completed into a command by hand |
| a live run of the coding worker against its real agent in CI | the gate runs the stand-in. The live test is written (`tests/workers/test_coding_worker_live.py`, #68): the job `coding` of the workflow `live` runs it monthly and by dispatch on `main`, never on a pull request (DEC-0048, DEC-0058), under the cap per run converted into tokens (NTC-0028). It has not run there yet: the first run is a dispatch on `main` after the merge, and its cost goes into #68 |
| governance and anchors in the product | built (#79, ADR-0042): a tenant's anchors are configuration never emptied, the shipped default where none is configured; an anchored act halts the run at the step boundary at every level with one decision request per anchor, answered on the control plane's surface by a holder of the anchor's role, its reading confirmed before it takes effect, every applied request an entry in the register. A request addressed to the owner reaches the owner's chat and is answered there (#85, ADR-0045). Not yet: the decider's page in the web app (`0.3.0`), the legal catalogue per domain and jurisdiction (UC-15.5), the egress predicate as the correction anchor's trigger (`0.5.0`) |

**How the owner is asked** changed on 2026-10-01 (DEC-0039): a situation that fits no entry of
the anchors is decided by a session in the direction of the vision and recorded as a notice; a
question is raised only where the vision gives no direction, and only after the vision, the
ADRs, the anchors and the register were checked. `make status` shows how often the owner took
the recommended option and how often a notice was overridden.

**On 2026-10-01 the audit of the register came back**, and the owner's answers DEC-0040 to
DEC-0043 were recorded first and then encoded. A decision under that rule states how it follows
its source, and between two options both consistent with the sources it takes the stricter in
substance and the one with less ceremony. Bringing a use case up to the owner's own definition
is the session's, with a notice (M2.7). After every twenty such notices the override rate goes
to the owner as a request, and the gate fails the register when it is due. The acceptance rate
now counts only what was asked before it was answered: **1 of 6 recommendations taken**, where
the naive count had shown 5 of 6. The audit found an owner action written as a note five times;
what can be checked exactly now is: every need named resolves to one that will be or was
provided, every `TODO(owner)` to an open record, and every credential variable has the one form.
Four needs were raised that had been deferred or never written — backups (NEED-0009), the
webhook secret (NEED-0010), the live connector test in CI (since superseded by Taktus's own app, NEED-0013), the coding agent in CI
(NEED-0012) — and the licence is tracked as the owner's own question, DEC-0044, due before
`1.0.0`.

**What was decided, and when**, is the register's index, `docs/decisions/README.md`, newest last,
each with the pull request that recorded it. Each record stands in the table of its kind, and the gate checks it
(DEC-0094). The ready rule reads an issue's form up to its footer (DEC-0116). **Open:** DEC-0044, the licence, which must be settled
by the release of `1.0.0` and is taken up only when that release is prepared, DEC-0069, the
same question as DEC-0030 for the seventeen use cases of the migration's second step, DEC-0082,
the same question for the twenty-seven of the third, and DEC-0087, the same question for the
seventeen of the fourth and the two blueprint descriptions. DEC-0028,
DEC-0029 and DEC-0030, raised by the pull request that brought in the vision layer, were answered on
2026-10-08, each with the recommended option: a floor for automatic skill approval set from data,
qualified reviewers for the legal-anchor catalogue before a finance or personnel blueprint, and
the thirteen use cases' added conditions stand. DEC-0053, the
budget of the next live run, was answered on 2026-10-08: USD 3 in total. DEC-0055, raised on
2026-10-08 from the owner's idea, was answered the same day: what Taktus does is seen as it
happens, as UC-6.10 requires for `0.3.0`. The same day the owner decided that the deployed
instance is production — Taktus manages itself there and steers the operation — and answered
how the deployment's needs are provided (DEC-0057, DEC-0058). DEC-0034 and DEC-0037, raised by the
pull request that took up the first run's findings, are answered: a worker with no calibration
history reserves twice its estimate, and where a run produces a generated text is the session's
to decide.

**On 2026-10-07 the owner answered five readings and replaced hand-written briefs.** Recorded
first, as DEC-0047 to DEC-0051. An operator's explicit margin below the 10 % floor holds,
because a limit is the operator's, and Taktus is to say so where it is set and in every report
relying on it (#72); the reason #52 gave — that tests would otherwise need editing — was a
misreading of the use-case rule, which protects what a use case requires and not the files that
test it. The model-reset reading stands. Live tests that need a credential run only on a
schedule or by dispatch, on `main`, never for a fork, under a spend cap, with their secrets in
the environment `live` (`.github/workflows/live.yml`); both live-test needs were rewritten
before they were provided. A session may spend up to USD 1 per task on the owner's credentials
to derive a fact instead of asking (M2.8). DEC-0037's Option A waits for event reactions. And
the work now comes from the backlog — the repository's issues — through a standing brief,
`docs/process/next-task.md`, until Taktus runs P-01, P-02 and P-03 on its own instance.
P-02 and P-03 already read the backlog's ready standard, by the same code `make backlog` runs:
P-03 admits only a ready issue and claims it with `in-progress`, and P-02 writes only the
sections an issue lacks, as a comment (issue #70, NTC-0040). P-01 Roadmap control runs as a
bundle too: it holds the roadmap against the open issues by the issue numbers each roadmap item
now names, and reports every item without an issue, every issue its milestone does not name and
every `ready` label on content that fails the standard, with the backlog's order computed by
the code `make backlog` runs (issue #71, NTC-0048, NTC-0049). Its daily trigger carries its inputs, and its reports go to #129, so an instance's scheduler can run it every day (NTC-0045). It changes nothing. Whether that
reconciliation stays a rule or becomes a model's, as the blueprint first described it, is the
owner's (DEC-0080).

**A budget is a budget, built** (ADR-0005, third amendment; DEC-0035). Every step is estimated
before it is admitted, or refused: a worker by its estimate, an `llm` step by the input its model
counts and the output limit it sets, a connector call by its operation's declared demand, a rule
by nothing. The estimate, scaled by its adapter's measured error — seeded from the first run for
the coding worker, and twice the estimate for a worker nothing has measured yet (DEC-0034) — is
reserved against the budget. A worker receives its reservation as its limits, and halts at its
next boundary before crossing
them (check W-14, in both reference workers, with a fault each). Tokens are recorded per model
and per price kind, a versioned price table prices them, and `taktusctl cost <run>` recomputes a
run's money from the ledger. Every model adapter declares what it can compute before a call;
when a budget is set the run records what it can promise, and where a provider bills per time
window it says that a currency budget cannot be enforced. The evidence is
`docs/research/2026-09-30-what-providers-allow.md`.

**The chat connector exists** (#84, `0.2.0`). The capability `chat.threads` and the channel
`channel.chat` are served by a connector for the chat service the owner uses, added to an
instance by one entry of `TAKTUS_CONNECTORS` with nothing under `src/taktus/components/`
changed. A message becomes an intake event and then a command equal to the same instruction from
the repository channel in every field but the channel and the identity of the message
(NTC-0082); a reply lands in the thread the command arrived in, once across a restart. It passes
the conformance suite, fault for fault, against a fake of its service. The service signs the
moment of sending with the body, so the connector contract gained a second signature scheme that
bounds a replay to 300 seconds (ADR-0024, amendment; NTC-0083). Against the real service it waits
for Taktus's app in the owner's workspace (NEED-0018). The webhook intake answers the URL check
the service makes before it sends events to an instance (#145): the connector verifies it,
refuses it as no event and says what to answer, and the surface returns that answer as it is —
a refusal may now carry an answer (ADR-0024, amendment; NTC-0084, NTC-0085).

**What is needed from the owner reaches the owner's chat** (#85, `0.2.0`, ADR-0045). A
decision request addressed to the owner, a need, a date or a failure Taktus noticed about
itself becomes one report: what is needed, the steps, the work that stands still and the date,
or it is not sent. Its repository text, its message and its view are composed from that one
record and carry the same identifier, items and date. The message is said through the chat
channel's reply operation, in the language the tenant configured — Taktus ships German and
English phrasebooks, and no component names a language — and links everything the report
concerns. Where a ticket system is configured the report is a task there too. The owner
answers in the message's thread: the answer is read by a rule, reflected without being quoted,
and filed only once the same person confirmed it, and only from the owner or someone the owner
named; a decision is filed in the register and its run continues. A delivery that fails stays
with the report and is shown. No message carries a secret value the instance holds. Proven
against the fake chat service; on the installed instance it waits for NEED-0018 and NEED-0020
(NTC-0095, NTC-0096). Nothing raises a need or a date from a step yet; the owner's own questions
in the chat are UC-6.4.

**A broken interface reaches the owner** (#100, `0.2.0`, ADR-0047). Taktus notices from its own
calls when an interface it depends on stops behaving as its adapter expects (DEC-0058). The
connector contract names the answer a connector does not foresee (`unexpected`), and the run
writes `interface.failed` for every call that failed as unforeseen — a contract broken, an
authentication refused, a status or a shape not foreseen — or transiently. A rule makes one broken
interface per interface and cause; a transient failure counts only once a retry of the same step
failed too. While the scheduler leads it reports each once through the owner-facing channel, with
the first and the last failed call and their runs and steps (NTC-0099, NTC-0100). Without a channel
it stays recorded, and `taktusctl interfaces` shows it as not delivered. Proven against the fake
repository service; on the installed instance it reaches the owner once the channel is configured
there (NEED-0020).

**Every block is booked to an account** (#80, `0.2.0`, ADR-0043). A stretch in which a step of a
run could not go on is recorded when it ends, with one of the seven accounts of ADR-0015, its
cause, the run, the step and the process version it held up, and its duration. Blocked time and
the share of the runs held up sum per account, per process and per period from the ledger alone,
and a wait on a person names no one except to the person who answered it. A model provider at its
rate limit now makes a step wait instead of failing it (NTC-0089). What is a block and where each
is booked is NTC-0090. The analysis over the accounts is `0.5.0`.

**The conformance half of maturity is recorded** (#93, `0.2.0`, ADR-0044). The instance runs an
adapter's contract suite itself, against the endpoint its configuration resolves for the
identifier, and one transaction records the outcome in the adapter's maturity and as
`conformance.tested` in the ledger, with the configuration it was taken under. A person starts it
with `taktusctl conformance record`, a process through the loopback (NTC-0091); nothing takes a
report, a verdict or a date. A pass counts only for the configuration it names: once the model,
the version or what the adapter declares changes, the adapter reads *experimental* again, and a
level-3 step on it is refused. Proven for the three families against the reference adapters and
their fakes, every fault recorded as not passed (NTC-0092), and through the run engine. No
integration of Taktus's own instance has been recorded yet: that run belongs to #87, and the
connector's suite there needs a sandbox it may write to (NEED-0019).

**What an instance meets that the product lacks becomes an issue** (#86, `0.2.0`, ADR-0046). A step
that fails because no configured worker, connector or operation offers what it needs now carries a
block until it can start, booked to `wait.dependency` (NTC-0098). A rule makes one finding per lack
of the blocks, ended and open, in the new `reporting` component. Where an operator sets
`TAKTUS_FINDINGS_CONNECTOR`, the scheduler sends it to the Taktus repository as a task issue with
the run, the step, the cause and the time waited; the same lack met again is a comment on the same
issue, the waiting summed (NTC-0097). Elsewhere `taktusctl findings` shows it, ready to send by
hand. A finding holds identifiers, causes, durations and counts, and no person. Proven against the
fake repository service; the Taktus project's own instance sends nothing until its operator sets
the connector.

**Taktus watches its platform** (ADR-0031). The *Observe* stage is built: free CPU, memory and
storage, growth per run extrapolated to a date, `taktusctl capacity` and a report by the
scheduler, admission against free capacity, every job's memory limit enforced or the job
refused. *Propose* (`0.5.0`) and *Manage* (`0.7.0`) are specified in
`docs/architecture/platform.md`.

**`make gates` is green locally in one command again** (DEC-0036). On 2026-09-29 it ended with
seven errors after 26 minutes on the owner's machine: two `docker build` runs hung silently for
600 and 900 s, reported seven times. A test image is now built only when its content changed,
and a hung build names where it stopped. Measured on the owner's machine: a healthy run costs
the same, about 3½ minutes; a hang costs 120 s instead of 600 or 900.

**The vision layer and the use cases.** Since the pull request that brought in `docs/vision/`,
the repository says why Taktus exists — fourteen principles, each with its reason and what it
forbids — and holds what it must do as use cases with a state that is derived, not claimed. That
answers, for the first time, how much of the vision stands:

- **Every one of the fourteen principles is served by at least one use case**; `make gate-vision`
  fails when one is not.
- **Seventy-five use cases exist in the new format. None is verified; three are built**: UC-1.7
  every command belongs to one identity (#82), UC-7.4 the decision request (#79), and UC-6.12
  the product finding (#86). Fifteen
  are *building* — part of what they require is built and named tests prove that part, which
  each states in its section 5, *What is proven so far*, outside the requirement (DEC-0106): UC-1.1
  commands from any channel, UC-4.5 halt or escalate at the boundary, UC-6.1 the complete activity
  log, UC-8.9 changing a vendor breaks nothing, UC-7.1 the autonomy range, UC-7.2 the emergency
  stop, UC-7.3 least privilege down to the worker, UC-8.5 cost control; and from the third step
  UC-1.2 planning in dialogue, UC-5.8 observability
  platforms, UC-8.1 any model connected, UC-8.4 repeatability, UC-8.10 limits that do no harm,
  UC-14.1 the worker interface; and from the fourth step UC-9.5 bottleneck and waiting analysis,
  whose blocked-time accounts are built (#80). Fifty-eight are *specified* and nothing of them is
  built. UC-6.10
  was added on 2026-10-08 and accepted by the owner (DEC-0055); seventeen came with the migration's
  second step on the same day, twenty-seven with the third on 2026-10-09, and seventeen with the
  fourth the same day.
- **Principles served only by specified use cases**, so that nothing of them stands yet beyond the
  text: P5 coupled or decoupled control, P9 efficiency over verbosity. The others have a use case
  in *building*.
- The requirements of the thirteen are the owner's decision, asked as DEC-0030 and answered on
  2026-10-08: they stand. Four of them fell short of what the definition asks; they were brought up to it
  on 2026-10-01 under M2.7 (NTC-0014 to NTC-0017), and DEC-0030 asked only about what the
  session added beyond the definition. `make usecases` prints the list with states; `make gate-vision` prints which use
  case serves which principle.
- **The second step of the migration is done** (2026-10-08): the process engine (E4), governance
  and autonomy (E7), and UC-15.3 to UC-15.5 of the virtual agent business, with UC-7.4 filed under
  `decision` (DEC-0070) and UC-8.5 under `accounting`. The seven cases still in their first files
  are in the format (NTC-0029). What the definition said that accepted decisions moved past is marked
  as superseded in the use case it concerns, never deleted: escalation and self-healing (ADR-0021,
  ADR-0022), level 4 (ADR-0008, ADR-0022), cost control (ADR-0005, ADR-0010). What the seventeen add
  beyond the definition is asked as DEC-0069, in force provisionally; one gap the split of failures
  from wrong results left was restored without asking (NTC-0030).
- **The third step of the migration is done** (2026-10-09): `command`, `identity`, `catalog` and
  `accounting` — the rest of E1, E8, E12 and E13 that is filed there, UC-5.8, UC-10.3, the whole of
  E14 (the worker interface, the skill lifecycle, the skill hub) and UC-15.1 domain blueprints.
  What accepted decisions moved past is marked as superseded in seven of them, never deleted. What
  the twenty-seven add beyond the definition is asked as DEC-0082, in force provisionally. UC-1.1 and
  UC-7.1 were brought up to the definition without asking (NTC-0050, NTC-0051). The skill format
  still needs an ADR before UC-14.2 is built.
- **The fourth step of the migration is done** (2026-10-09), and with it the migration: `knowledge`,
  `value` and `reporting` — the rest of E5, E6 and E9, UC-13.4, and UC-9.5 in `accounting` — and
  UC-10.1 in `governance` and UC-10.2 in `identity` (NTC-0064). The three requirements the owner
  stated outside the definition are use cases: the owner-facing channel (UC-6.11), the product
  finding (UC-6.12), readable documentation beyond the repository (UC-13.6). The finance reference
  domain (UC-15.2) and the IT service chat (UC-12.2) are described as deployments in `blueprints/`,
  and the definition's example domains are `blueprints/README.md`. What accepted decisions moved past
  is marked as superseded in three of them, never deleted. What the fourth step adds beyond the
  definition and the owner's stated text is asked as DEC-0087, in force provisionally. UC-6.1 and
  UC-6.4 were brought up to the definition without asking (NTC-0062, NTC-0063). The working file of
  the migration is deleted, as it said; `docs/usecases/NUMBERING.md` keeps where every number of the
  definition went.

**The migration of the project definition** into `docs/vision/` and `docs/usecases/` ran in four
pull requests and is complete:

1. **`vision/`, the use case format, the two gates, the rules, the three findings** — done in the
   pull request that brought in the vision layer. The findings: reporting is a component and
   enablement is not (ADR-0029); use case numbers are reconciled, the repository's winning, in
   `docs/usecases/NUMBERING.md`.
2. **The use cases of `process`, `run` and `governance`** — done on 2026-10-08, with UC-15.3,
   UC-15.4 and UC-15.5 of E15; what they add beyond the definition is DEC-0069.
3. **`command`, `identity`, `catalog`, `accounting`**, with E14 and UC-15.1 — done on
   2026-10-09; what they add beyond the definition is DEC-0082.
4. **`knowledge`, `value`, `ledger`, `reporting`, and what moves into `blueprints/`**, with the
   finance domain of UC-15.2 and three requirements the owner stated outside the definition — the
   owner-facing channel, documentation beyond the repository, and the product finding — done on
   2026-10-09; what they add beyond the definition is DEC-0087. The migration's working file is
   deleted.

**The weekly removal test** (`.github/workflows/removal-test.yml`, Mondays 06:00 UTC) ran on
its schedule for the first time on 2026-09-28, green, in 25 seconds — started by the host at
12:51 UTC, not 06:00, which is the host's scheduling and not the workflow's.

## 2. The next pull requests

**The order of work is the backlog's** (DEC-0051): the repository's open issues, in milestones
named as in the roadmap, taken earliest milestone first, then by priority, then by number.
`make backlog` prints it, with every task that is not ready and why; `make backlog NEXT=1` names
the next one. A session told only "continue with the next task" follows
`docs/process/next-task.md`. The list is not kept here, for the reason section 3 gives.

The backlog was built by hand on 2026-10-07, as P-01 would build it: the remainder of `0.1.0`
and `0.2.0`, the use-case migration's steps 2 to 4, the deployment, the owner-facing channel,
documentation beyond the repository, the product finding, DEC-0037's Option A, the live run
that proves budget, rehearsal and capacity, and every open item of this file with a milestone.
At that moment the first tasks are the chart and the image build, and the cluster execution
adapter (`0.1.0`), because installing the deployment waits for them and for three needs due
2026-10-20.

## 3. Needed from the owner

Every open needs request and decision request, the most urgent first. A needs request is
something only the owner can provide — a credential, an account, access, a purchase, an action,
information. A decision request is a question only the owner can answer. Each has an issue
assigned to the owner with the steps.

**The list is not kept in this file.** It is generated from the open records of the register
and carried in three places, none of which two pull requests can edit at once (DEC-0026):

- the last section of every pull request description, `## Needed from the owner`, checked by
  CI against the branch's register;
- [the open issues labelled `needs-owner` or `decision-request`](https://github.com/Jersyfi/taktus/issues?q=is%3Aopen+label%3Aneeds-owner%2Cdecision-request);
- `make status` in a checkout, which prints it.

## 4. Blocked

| What | On what | Since |
|---|---|---|
| a removal-test verdict of *changed* through an alternative adapter | a second adapter for a capability a process uses; nothing today has one | #14. The *broke* verdict on a real process is no longer missing: the run of 2026-09-23 produced it for `connector.channel.repo`, naming eight steps across P-02 and P-03 |

The first live end-to-end run is no longer blocked and has happened. It was blocked from #8,
#10 and #13 — where each need was foreseeable and stated only as a note — until #22 raised the
needs and #23 wired them: seventeen days from the first foreseeable moment to the credential,
of which two were between the request and the answer. That is the cost the timing rule of
ADR-0028 exists to prevent, measured.

**Writing** the deployment is not blocked: the plan is `deploy/k8s/README.md`, built against a
platform that was read in full on 2026-09-23. Nothing the owner provides blocks installing it
any more: since 2026-10-08 the deployment's access to the cluster, the public name with its
certificate, the webhook secret, the backup store and Taktus's own app on the repository
service exist (NEED-0007 to NEED-0010, NEED-0013); the connector acts as the app since #108
(ADR-0033), and placing the app in the live environment and retiring the personal token is
NEED-0016. The instance holds real work once its backup and restore exist (#67), and is treated as production
(DEC-0057).

Nothing else is blocked. Everything not listed here can be built by a session without the
owner.

## 5. Promises not yet kept

What the repository says will hold and does not hold yet: tests pending, limits documented
rather than enforced, anything marked provisional.

| Promise | Where it is made | State |
|---|---|---|
| the removal test is a conformance check, W-12 and C-10 | `contracts/worker/v1`, `contracts/connector/v1` | reported *pending* by both suites (DEC-0005); the test runs as the process S-01 instead. The conformance half is recorded since #93 (ADR-0044); no integration of Taktus's own instance has both halves yet, so none is *verified* there |
| the removal test *exercises* the processes that use an integration | `blueprints/self-operation/`, S-01, ADR-0030 | it rehearses them: outward operations answer from the recording of their last real call. A process is rehearsed only once it has been called for real on that instance, so the weekly job, on fresh state, still resolves P-02 and P-03 statically; a worker step that may reach hosts — P-03's — is never rehearsed; the rehearsal has never run against a real recording (`docs/runs/README.md`) |
| a budget is a budget | ADR-0005, third amendment | built, with three limits stated there: the overrun of the one inner step during which a total crossed the line is spent; money a worker reports only when an assignment ends cannot halt it, and it is held by its tokens. The margin has a floor of 10 % and resets with the model version (DEC-0043); an operator's explicit value below the floor holds and is said: a warning in the startup log, a line in the run's `budget.set` statement and in `taktusctl cost` (DEC-0047, NTC-0025). Never run live: what the next live run must measure — estimate against actual, a halt on a real reservation — is in `docs/runs/README.md` |
| a budget says what the provider permits | `contracts/model/v1`, `docs/research/2026-09-30-what-providers-allow.md` | this tenant's endpoint holds its output limit: the research says so ([A4]) and M-03 passed against it on 2026-10-01; `tools/first_run.sh` derives the declaration with M-03 on every run, and the deployment sets it (`deploy/k8s/README.md`). The adapter's default for an endpoint nobody has checked stays `soft`; the research is dated and expires |
| Taktus watches its platform | ADR-0031 | *Observe* built; *Propose* `0.5.0`, *Manage* `0.7.0`. On macOS memory is neither observed nor limited, and the process adapter refuses a job there unless an unenforced limit is accepted; the cluster's own quota is not seen until a cluster platform adapter exists; admission against free capacity has never run on the platform it is for — the next live run's list is `docs/runs/README.md` |
| an automatically started P-03 opens a pull request whose checks pass | DEC-0037 | decided: the worker runs the generator after its change and the run appends what it printed; built with event reactions in `0.2.0` (DEC-0050, #77), until when the manual command supplies the section |
| a process that would give an instance credentials for its own infrastructure is refused at planning time | ADR-0025 | applied by the person who configures an instance; refusal in code is `0.2.0` |
| an anchor halts the run at a step boundary and raises a decision request in the product | ADR-0008, ADR-0042, `docs/architecture/governance.md` | built (#79): anchors per tenant, evaluated before every step at every level, a request in one shape answered and confirmed on the control plane's surface, an entry in the register (`tests/governance/test_anchors.py`). The correction anchor triggers on its selectors; the egress predicate as its trigger arrives with remediation (`0.5.0`). An anchor's halt is a block booked to `wait.human` (ADR-0043) |
| every command belongs to one identity | UC-1.7, ADR-0040 | built: links, link codes, revocation and the answer to an unknown sender, proven by tests. Not yet: an adapter for an organisation's identity source (the port exists); authorisation of who may administer (UC-7.3) — whoever runs the command line against the database can; the account key is a bearer secret that does not expire; the reply reaches a channel only where its connector declares the reply operation, and on the installed instance no person is linked yet (NEED-0017) |
| a process runs only what its autonomy level permits | UC-7.1, ADR-0026, ADR-0039 | levels 1 to 3 built (#78): per process and per tool action, the lowest holding, applied before every step starts — level 2 waits for a person's confirmation, level 1 runs analysis and proposes every act for a person to perform, level 3 runs only on a *verified* adapter. A raise needs a person's approval and the replaced version's quality history, at registration; a refusal is in the ledger. Not yet: level 4 (`0.6.0`), levels per risk class, who may confirm (rights per role, UC-7.3), result defects in the history (`0.5.0`). The conformance half is recorded since #93 (ADR-0044), and a pass counts only for the configuration it names. No integration of the instance has both halves yet, so a real run of the project's P-01, P-02 or P-03 still halts at its first step on an integration; S-01 reaches only the loopback and runs (NTC-0079). The way to *verified* is in `0.2.0` since 2026-10-09: the conformance half, recorded but not yet for an integration of the instance (#87, NEED-0019); and the removal half, built for P-01 to P-03 — every step on an integration falls back to a person when it is unavailable, so S-01 says *changed* for the repository connector, the coding worker and the model (#90). A person standing by counts for that half (DEC-0111, answered 2026-10-10) |
| several instances with load spread across them, a restart without data loss | ADR-0013 A | proven for two runner processes on one database: twenty runs shared, one runner killed mid-step, its runs recovered by the other at their last boundary after the lease — a worker step it had handed over adopted from the worker, not handed over again (ADR-0038, NTC-0074), one it had only admitted started once (NTC-0046) — both chains verifying (`tests/integration/test_runner_failover.py`, #73); the election of a scheduler is proven with two. A runner alive but cut off for longer than the lease writes nothing more to the run once another runner has claimed it: the claim is a fence, checked in the transaction of every write (`tests/integration/test_runner_fence.py`, #107, NTC-0044). Runners whose concurrency together exceeds a shared worker's capacity no longer escalate runs: a step the worker turns away waits at its boundary, its job deferred, and escalates only past its ceiling (`tests/integration/test_capacity_wait.py`, #122, NTC-0060). An assignment a runner handed over is named in the ledger before the worker sees it, and a runner that dies or is cut off after the worker accepted it leaves no assignment running unrecorded or beside another: the next runner asks the worker and adopts it (`tests/integration/test_handover.py`, #130, NTC-0073). The two answers that adoption trusts are conformance checks: W-16 fails a worker that does not answer `404` for an id it never received, and W-17 one that does not answer `409` for an id it holds or starts it again (#138, NTC-0077). Not yet: how many runs one instance carries is a `1.0.0` condition |
| runners that share a worker never place more on it than it declares | ADR-0037 | holds as long as the worker answers `503` when it is full, which the engine trusts and does not count. Conformance check W-15 holds as many assignments as a worker declares and fails it when it accepts one more (#133); a worker whose assignments end before the suite fills its places, or that declares more than sixteen, leaves W-15 inconclusive, and the engine still trusts it |
| the coding worker's boundaries lie between tool calls; a stop inside a tool call waits up to the ceiling; money is known only at the end | `workers/claudecode/README.md` | documented limits of the agent, not enforced by Taktus; admission control on a currency limit works against the estimate only |
| `frame.allowed_hosts` names the hosts a unit may reach | DEC-0008, `contracts/worker/v1` | enforced by the `container` adapter through a per-job egress proxy, and by the `cluster` adapter through a per-job proxy Job where the cluster enforces network policies. With the `process` and `endpoint` kinds it is declared and not enforced, and `tools/first_run.sh` uses `endpoint` — so the first live run's worker reached whatever the machine could (DEC-0022) |
| the weekly removal test runs weekly | `blueprints/self-operation/README.md` | ran by hand on 2026-09-21 and 2026-09-23, and on its schedule for the first time on 2026-09-28, against the example process and the reference worker; every verdict now names the adapter it was taken under, and an integration no process uses reads `untested` (#36); the scheduler starts it from the bundle's weekly trigger in a daemon with the `scheduler` role (#69), proven in a test, and no installed instance runs one yet, so the CI workflow stays |
| exactness is a result, not a switch: the exactness statement | UC-4.13, UC-6.9 | specified; `0.5.0` |
| result defects are detected and remediated under the correction anchor | ADR-0021 to ADR-0023 | the terms and the anchor exist; detection and repair are `0.5.0` |
| `contracts/events/v1`, `blueprints/it-operations` | their README files | placeholders |
| `deploy/k8s` renders a chart | `deploy/k8s/README.md` | **rendered, never installed.** The chart renders one deployment per role, the database on 20 Gi, the migrations, Taktus's Role in the execution namespace as `deploy/k8s/README.md` §1 states it (DEC-0061), a jobs' account without a token and the units' state claim, default-deny both ways in both namespaces with their exceptions, and the ingress; every secret is a mounted file. `tests/governance/test_chart.py` reads the rendered manifests back in CI. Not yet: the install (#66); the namespaces' admission labels are set outside the chart (DEC-0060); the cluster adapter is wired (`execution.kind: cluster`) and not the default until the install has run it; the release images go nowhere until the registry is set (NEED-0014) |
| the cluster execution adapter | ADR-0002's execution table, `deploy/k8s/README.md` | built, and proven against a fake of the cluster's API only: the real-cluster tests skip until NEED-0015 is provided. It isolates a pod's network only where the cluster enforces network policies, and refuses hosts and every job from level 3 where the operator says it does not |
| a live run of the coding worker in CI | `docs/roadmap.md` | the gate runs the stand-in. The live test exists (#68) and runs in the workflow `live`, monthly and by dispatch on `main`, under the cap of USD 0.50 per run (NEED-0012), held as tokens because the worker learns the money only at the end (NTC-0028); not yet dispatched. The worker has run live eight times outside CI (`docs/runs/first-run.md`) |
| the components `accounting`, `decision`, `knowledge`, `value` | `docs/architecture/project-structure.md` | packages with an `__init__.py` and nothing else; `reporting` (ADR-0029) exists since #85 with the owner-facing channel (ADR-0045) |
| principle 14 is enforced in the data model, not in a policy | `CLAUDE.md` §5, `docs/architecture/governance.md` §6, ADR-0015 | for waits on a person: a block and a sum have no field that can hold a person, and only the person who answered reads a wait under their name (ADR-0043, `tests/components/run/test_blocked_time.py`). The ledger entry of an answer still names who answered and when, as the audit requires, so a reader of the ledger can compute it by hand. A wait on an anchor's decision carries the role it is addressed to, and the decision component aggregates response times by role and department (ADR-0042); the blocked-time sums are not split by role yet. UC-13.5 and UC-6.4 require the test for everything else measured about a person |
| every block is analysable by cause and duration | ADR-0015, ADR-0043, `docs/roadmap.md` `0.2.0` | built: every block is recorded with its account, cause, run, step and duration, and summed per account, process and period. Not booked: a connector's provider at its rate limit, which the connector contract reports as `unavailable` and which fails the step; a wait inside a worker's assignment; a block that has not ended. An anchor's halt is booked to `wait.human` with its role. Never run on an installed instance |
| the legal-anchor catalogue holds | `docs/architecture/governance.md` §2, `docs/decisions/anchors.md` M4.4 | not legally reviewed for any jurisdiction; qualified reviewers of the jurisdiction review it before the first finance or personnel blueprint is used, and at every change (DEC-0029) |
| every principle is served by a use case, and a use case's state says how much of it stands | `docs/vision/README.md`, `docs/usecases/README.md` | the gates check that each principle is served and that a `verified` use case's tests pass; they cannot check that a use case *covers* its principle, or that a `building` use case's tests prove the part it says they prove |
| a pull request description can be acted on without the diff | ADR-0017 §7 | the gate checks that the four sections are there, filled and in order; not that they are readable without the diff |
| Taktus is repairable without Taktus: a restore, documented and exercised | ADR-0013 C | not for a deployed instance: there is no backup yet. Its destination exists (NEED-0009); Taktus keeps backups for a configurable time, 30 days by default, encrypted only if chosen (DEC-0058); the backup and its restore, exercised once, are #67 |
| the repository connector keeps its promise against the real service | `tests/adapters/connectors/test_repository_live.py` | runs only where an identity is set. Since DEC-0048 it runs in the workflow `live` — monthly and by dispatch, on `main`, never on a pull request — as Taktus's own app, minting its token in the run (ADR-0033), and as the app it also holds the pull request it opens to the app's name. It has not run as the app yet: the environment needs the app's identifier and key (NEED-0016); until then the job says in a notice that nothing ran |
| what is needed from the owner reaches them and their answer is filed | UC-6.11, ADR-0045, #85 | built and proven against the fake chat service and the fake repository service as the ticket system (`tests/adapters/connectors/test_owner_channel_chat.py`); provisional under DEC-0087. Not yet: a run against the real chat service (NEED-0018) and the channel configured on the installed instance (NEED-0020); a failed delivery tried again on a schedule; a closed task reported by the repository connector as an event; a need or a date raised by a step; the owner's questions (UC-6.4); the web app's page (#105). Answers are read as whole words of the phrasebook, so "ja, passt" is asked back |
| the chat connector keeps its promise against the real service | `tests/adapters/connectors/test_chat_live.py`, #84 | runs only where a scratch conversation and the app's token are set: in the workflow `live`, monthly and by dispatch on `main`, never on a pull request (DEC-0048). It has not run: the app in the owner's workspace is NEED-0018, and until it is provided the job says in a notice that nothing ran. Proven against the fake of the service only. The webhook intake answers the service's check of the request URL (#145), proven with recorded checks; the event subscription is set at the service under NEED-0018 |
| what Taktus writes on the repository service appears under its own app's name | ADR-0033, DEC-0058, issue #50 | built: the connector acts as the app when configured, shown against the fake service and in the conformance suite. Not yet shown on the installed instance — a pull request opened there by P-03 — which waits for the install (#66); where that check lives is DEC-0063. Runs on the owner's workstation still use the personal token until NEED-0016 |
| a licence | ADR-0012 | open: all rights reserved, no outside contribution accepted. The owner's own question, DEC-0044, settled by the release of `1.0.0` and taken up only when that release is prepared, as the owner confirmed on 2026-10-08; before the first outside contribution too |
