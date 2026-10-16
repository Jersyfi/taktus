# How the project is run

Part of `docs/status.md`: how the owner is asked, the register, the gates, the vision layer
and the reviews that set how work is done here. Kept current by the pull request that changes it.

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

**What was decided, and when**, is the register's index, which `make register` prints from the
records, newest last, each in the table of its kind (DEC-0094); each record names the pull request
that recorded it. Since #316 the index is stored nowhere and every number is reserved before its
record is written (`make reserve`), so two pull requests that each add a record never conflict
(DEC-0189 rule 6). Since #315 a behaviour change (M2.4) is a line of the pull request's
section *Behaviour changes* instead of a notice file, and `make status` counts those lines of
merged pull requests beside the notices (DEC-0189 rule 2). Since #382 a P-03 run reserves the numbers of the records its change adds,
through the repository connector, before it writes the branch (ADR-0095). The ready rule reads an issue's form up to its footer (DEC-0116). **Open:** DEC-0044, the licence, which must be settled
by the release of `1.0.0` and is taken up only when that release is prepared. On 2026-10-11 the owner answered DEC-0124 (UC-4.14 stands), DEC-0127 (four kinds of link, with a direction on outside contributors carried by #245), DEC-0131 (the candidate weighting table, version 0, uncalibrated), DEC-0132 (UC-8.5 gains the Takt's condition) and DEC-0133 (planning refuses a credential administering the instance's platform, undeclared ones too), each with Option A; UC-8.5 carries the Takt's condition since, and #81 builds it. The same evening the owner answered DEC-0174 (the session merges its own green pull requests and tags the release candidate, for the push through `0.1.0` to `0.3.0`), DEC-0175 (people Taktus does not know are handled by a triage process for its owner; UC-1.9 carries it since, and #245 builds it) and DEC-0176 (the guides go to a self-hosted BookStack), each with Option A. The owner's idea of the same evening, that Taktus rents execution capacity at a provider within a budget, is DEC-0177 (#253), open. DEC-0179 lets the session act on the instance with the deployment identity (Option A). DEC-0184, on 2026-10-12, lets it tag further release candidates until the milestones close. DEC-0185, the same day, approves the web app's design direction *one body that works* and makes the look of a representation the session's (M1.20). DEC-0186, raised the same day, asks whether UC-4.15 states what changing a process from the web app and chat must do; it is in force provisionally as Option A, and ADR-0091 says how it is built. Since #294 to #299 a process is changed in dialogue and rolled back from the web app and the owner's chat: a proposal, a rehearsal, commissioning, a rollback as a new version. NEED-0017, NEED-0019 and NEED-0020 were provided that evening: the owner's repository and chat accounts are linked to `idn_owner`, which holds `owner`, the owner-facing channel is configured, and the connector suite's sandbox has the app. DEC-0161, which library the ML bench trains with (M3.8), in force provisionally as Option A. DEC-0173, how a step whose value a fixed rule computes from its inputs stays `exact` (M3.15), in force provisionally as Option A, a sixth check, recomputation, which fifteen of the repository's sixteen `exact` steps declare (#91, ADR-0082). DEC-0164, what method maturation must achieve (M3.15), a use case of its own on Option A, on which #217 and #218 are written. On 2026-10-10 the
owner answered DEC-0069, DEC-0082 and DEC-0087 with Option A — what the seventeen, twenty-seven
and seventeen use cases of the migration's second to fourth steps add beyond the definition
stands — and DEC-0123: no figure compares the working time of named persons; processes are
analysed in detail by step, role and department. DEC-0028,
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
sections an issue lacks, as a comment (issue #70, NTC-0040). Since stage 0 of DEC-0197, P-03
takes only an issue handed to Taktus with the label `to-taktus`, which sessions skip, and refuses
one whose "Blocked by" names an open decision or an ADR; it says on the issue which run took
it, and a run that escalates after its claim gives the claim back, saying why (ADR-0097). P-01 Roadmap control runs as a
bundle too: it holds the roadmap against the open issues by the issue numbers each roadmap item
now names, and reports every item without an issue, every issue its milestone does not name and
every `ready` label on content that fails the standard, with the backlog's order computed by
the code `make backlog` runs (issue #71, NTC-0048, NTC-0049). Its daily trigger carries its inputs, and its reports go to #129, so an instance's scheduler can run it every day (NTC-0045). It changes nothing. Its first real run on the instance, on 2026-10-13, halted at `read-issues`: the step's uncalibrated reserve alone is its whole quota of 40 units; the owner raised it to 60 units (DEC-0192). The owner chose the
rule for that reconciliation over a model's matching, as the blueprint first described it
(DEC-0080).

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
- **Seventy-seven use cases exist in the new format. None is verified; four are built**: UC-1.7
  every command belongs to one identity (#82), UC-7.4 the decision request (#79), UC-6.12
  the product finding (#86), and UC-4.14 a process starts on what happens in a tool (#76). Twenty-two
  are *building* — part of what they require is built and named tests prove that part, which
  each states in its section 5, *What is proven so far*, outside the requirement (DEC-0106): UC-1.1
  commands from any channel, UC-4.5 halt or escalate at the boundary, UC-6.1 the complete activity
  log, UC-6.10 seen as it happens, whose visual vocabulary, web app and four levels — overview,
  process, run, origin of a result — are built (#104, #105, #190, #191, #192), UC-6.11 the owner-facing
  channel, UC-8.9 changing a vendor breaks nothing, UC-7.1 the autonomy range, UC-7.2 the emergency
  stop, UC-7.3 least privilege down to the worker, UC-8.5 cost control; and from the third step
  UC-1.2 planning in dialogue, UC-5.8 observability
  platforms, UC-8.1 any model connected, UC-8.4 repeatability, UC-8.10 limits that do no harm,
  UC-14.1 the worker interface; and from the fourth step UC-9.5 bottleneck and waiting analysis,
  whose blocked-time accounts are built (#80); UC-4.13 working out how a step becomes exact and
  UC-6.9 the exactness statement (#91), UC-13.5 a person's own contribution made visible (#94),
  UC-13.6 readable documentation beyond the repository (#198, #197), and UC-1.9 a contribution
  from a person Taktus does not know (#245, DEC-0175). Fifty-one are *specified* and nothing of
  them is built. UC-6.10
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
  beyond the definition stands, by DEC-0069; one gap the split of failures
  from wrong results left was restored without asking (NTC-0030).
- **The third step of the migration is done** (2026-10-09): `command`, `identity`, `catalog` and
  `accounting` — the rest of E1, E8, E12 and E13 that is filed there, UC-5.8, UC-10.3, the whole of
  E14 (the worker interface, the skill lifecycle, the skill hub) and UC-15.1 domain blueprints.
  What accepted decisions moved past is marked as superseded in seven of them, never deleted. What
  the twenty-seven add beyond the definition stands, by DEC-0082. UC-1.1 and
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
  definition and the owner's stated text stands, by DEC-0087. UC-6.1 and
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
