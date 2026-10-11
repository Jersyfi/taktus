# Blueprint `self-operation`

The processes Taktus runs for itself, on itself: the checks of its own claims, and its own
documentation beyond the repository. This is the first blueprint whose subject is Taktus, and its
first process is the check of the product's own central claim.

| Process | State | Bundle |
|---|---|---|
| **S-01 Removal test** — one integration is withheld, the processes that use it are exercised, the verdict is recorded | **runs** weekly | [`processes/S-01-removal-test.yaml`](processes/S-01-removal-test.yaml) |
| S-02 Takeover test — a person runs a process by hand from its instructions | `0.5.0` | — |
| S-03 Restore drill — an earlier version is restored without Taktus and the ledger chain verified | `1.0.0` | — |
| S-04 Load measurement — how many concurrent runs one instance carries | `1.0.0` | — |
| **S-05 Guides** — the administration guide and the guide for users, rendered from the repository and put into the knowledge system; a hand edit is kept and reported | **runs** daily | [`processes/S-05-guides.yaml`](processes/S-05-guides.yaml) |

## S-01 Removal test

Principle 13 and ADR-0003 promise that every integration can be removed: removing it changes
quality or cost, but breaks no process. Until this process existed, that promise had been
tested by nobody — the conformance suites report the removal test as *pending* (W-12, C-10;
DEC-0005), because a suite that talks to one adapter cannot remove it from processes. Now there
are processes, and this is the test. A test that runs once in its life proves nothing; one that
runs weekly is evidence.

**What one run does**, for one integration named as its input (`worker.endpoint`, or
`worker.<name>` for one of several workers, `connector.<label>`, `model.endpoint`, or
`persistence.database`):

1. **describe** — reads from the instance what the integration serves, which other configured
   adapter serves the same, and which registered processes use it.
2. **admit** — checks that the integration is configured and of a known family (`exact`).
3. **exercise** — withholds the integration, rehearses every registered process that uses
   it, and restores it. An instance's configuration is its environment and does not change
   while it runs, so the three are one operation: the instance builds the same engine over the
   same stores with the integration left out of the adapter pools, runs the process through
   it, and the unchanged configuration is the restored state. A process is run twice, with and
   without, and both runs are **rehearsals** (ADR-0030): a connector operation declared
   `write` or `delivery` is never sent, and answers with the recorded response of its most
   recent real call through the same adapter; reads are real. The two runs are compared by
   where each came to. A process is not run, and its verdict rests on *resolution* alone —
   which adapter would serve each step without the integration, and what the step's declared
   fallback is — when an outward operation it would call has never been called for real on
   this instance, when a worker step may reach hosts, or when an input has no example. The
   finding says which. Every rehearsal run is in the ledger, and every one of its entries
   carries `rehearsal: true`; a rehearsed outward step finishes `rehearsed` and writes no
   egress entry. The run *with* the integration puts it first in its pool, so an adapter
   configured behind another that serves the same capabilities — the second of two coding
   workers — is exercised on every step it can serve, and the one in front of it is its
   alternative (ADR-0078).
4. **describe-after** and **verify-restored** — read the configuration again and check that the
   integration is there and serves what it served (`exact`).
5. **verdict** — checks that the result carries exactly one of four verdicts (`exact`).
6. **record** — writes the result to the adapter's maturity and to the ledger as
   `removal.tested`, in one transaction.
7. **report** — one line a person reads.

**The four verdicts.** *Broke*: a step loses its only adapter and nobody takes it over — no
alternative adapter, and no fallback to a person. *Changed*: every process still reaches its
point — another adapter served the step, or the step falls back to a person, who does it at a
person's cost; quality and cost changed, nothing broke. *Untested*: no registered process uses
the integration, so nothing was exercised and nothing learned; it does not count towards
*verified*, and the maturity record says so (issue #36). *Exception*: the integration cannot
be removed by design; the database is the one (ADR-0002), and its removal test is the restore
drill. The verdict is a rule over what was observed (`components/catalog`,
`domain/service/removal.py`), never a judgement, which is why the `verdict` step is `exact`.

**What a verdict was taken under.** Every result carries `configuration`: the adapter that
served the identifier, the capabilities, purposes or operations it declared, and its version
where it declares one. The same identifier can name another adapter next week — a worker that
serves other capabilities gives another verdict — so the report prints it, and the digest in
`removal.tested` covers it.

**Where it reaches the instance.** Every step is a call of a capability — `orchestrator.
integrations`, `orchestrator.removal`, `orchestrator.maturity` — served by the *loopback
connector*, through which Taktus reaches itself (`src/taktus/adapters/driven/connectors/
loopback/`, `docs/architecture/contracts.md` §4). Its operations stay inside Taktus and write
no egress entry. The removal test never lists the loopback as an integration: Taktus is not an
integration of Taktus.

### Its autonomy, with the reason

Level 3: every step is a read of the instance's own state or a rule over what was read, nothing
leaves the system, and the verdict is reproducible from the ledger; a person watches the weekly
report and samples the rehearsals. Toward level 4: a month of weekly runs whose verdicts a
person checked against the rehearsal runs and found right, started by the scheduler from the
bundle's trigger; then Taktus proposes the raise with that evidence (M3.9).

### Running it

```bash
tools/removal_test.sh --with-example
```

runs S-01 once for every integration this instance is configured with, against the reference
worker with the shipped example registered, and prints every run with its ledger. It is what
the weekly job runs (`.github/workflows/removal-test.yml`). One integration by hand:

```bash
uv run taktusctl run --process blueprints/self-operation/processes/S-01-removal-test.yaml --input integration=worker.endpoint
```

**From its trigger.** The bundle's trigger says `weekly` — Mondays 00:00 UTC — with `each`
over `orchestrator.integrations.list`. On an instance that runs `taktusd` with the `scheduler`
role and has S-01 registered, the elected scheduler starts one run per integration the instance
lists, once per week, whichever scheduler leads (ADR-0035). The runs act for the identity
that registered the bundle — it must be one the tenant knows (ADR-0040) — and each carries
`run.triggered` in the ledger. A week missed while no scheduler ran is caught up once, not
once per week missed. `tests/integration/test_time_triggers.py` runs it that way on a clock the
test moves. Register the bundle once, through the daemon's database:

```bash
uv run taktusctl submit --process blueprints/self-operation/processes/S-01-removal-test.yaml \
    --input integration=persistence.database
```

registers it and runs it once for the database. Until an installed instance runs S-01 on its
own, the weekly job of the repository's CI stays the schedule of record (issue #69).

### By hand — the takeover test of this process

A person runs the same test without Taktus (ADR-0013 B). It needs the instance's configuration
(`.env` or the environment), `taktusctl`, and write access to nothing outside the instance.

1. **Describe.** Note which capabilities the integration serves — for a worker, the
   capabilities it declares (`GET <worker>/v1/capabilities`); for a connector, its declaration
   resource; for the model, `TAKTUS_MODEL_PURPOSES`. List the registered process bundles whose
   steps require one of them (`requires:` on worker steps, the `operation:` of connector steps,
   the `purpose:` of llm steps).
2. **Remove.** Take the integration out of the configuration: unset `TAKTUS_WORKER` (or point
   it nowhere), remove the entry from `TAKTUS_CONNECTORS`, unset `TAKTUS_MODEL_ENDPOINT`.
3. **Run.** For every process from step 1 whose steps would not leave the system, run it once
   with the original configuration and once with the reduced one (`uv run taktusctl run
   --process <bundle> --input <declared examples>`). Note for each run its final state, the
   step it ended at, and the consumption line. A process that writes outward is not run by
   hand: running it would write twice. Its verdict rests on step 4, as it does in Taktus when
   no recorded response exists.
4. **Measure.** For every step the integration served: does another configured adapter serve
   it? If not, does the step's `fallback:` name `human`? If neither, the process *broke*. If the
   reduced run reached the same point as the original, or stopped exactly at a step a person
   takes over, the process *changed*. The integration's verdict is *broke* if any process broke,
   and *untested* if step 1 found no process that uses it.
5. **Restore.** Put the configuration back and run step 1 again: the integration serves what
   it served.
6. **Record.** Write the verdict, the date, what the integration served and its version from
   step 1, the processes and the run identifiers into the register of adapter maturity —
   today the `adapter_maturity` table, or the notes of the operating documentation — and keep
   the two runs' output as the evidence.

### The first run

Run on 2026-09-21 on a development machine, in memory, against the reference worker with the
shipped example `six-times-seven` registered — the only worker, the only process. The result:

```
removal_test: worker.endpoint
run run_ee31538cab2bf62ed6d3  process s01-removal-test@1  state finished
   1 describe             rule       sourced   succeeded  quota 1.0 artifacts: result
   2 admit                rule       exact     succeeded  artifacts: result
   3 exercise             rule       sourced   succeeded  quota 1.0 artifacts: result
   4 describe-after       rule       sourced   succeeded  quota 1.0 artifacts: result
   5 verify-restored      rule       exact     succeeded  artifacts: result
   6 verdict              rule       exact     succeeded  artifacts: result
   7 record               rule       sourced   succeeded  quota 1.0 artifacts: result
   8 report               rule       sourced   succeeded  artifacts: result
ledger  28 entries of this run, chain of 57: verifies
    52 23:00:22 removal.tested                      changed                 288741afc49d
provenance  8 records of this run, one per completed step: chain verifies

removal_test: persistence.database
    98 23:00:13 removal.tested                      exception               75a9ccc8ef50
```

Entries 17 to 39 of the chain are the two rehearsals of `six-times-seven@1` inside the
`exercise` step: with the worker, the example halts at `overreach` by design; without it, the
example escalates at `compute`, where no other worker offers `shell.script` and the step falls
back to a person. Verdict *changed*: the process continues with a person at that step. The
maturity of `worker.endpoint` records the passed removal half and names what is still missing
for *verified* — the conformance suite has not been recorded as passed, because nothing records
it yet. `persistence.database` is recorded as the known exception, with its reason.

What this first run does not show, stated plainly: a *broke* verdict on a real process, because
no registered process of that run had a connector step; and a *changed* verdict through an
alternative adapter, because one worker was configured. Both are what weekly runs in an
installation with more than one adapter per capability will show, and the roadmap's 1.0.0
section asks for the test green for every adapter, not one.

`tests/integration/test_removal_test.py` runs the same, every time CI runs, and holds the
verdicts to the reasons above. `tests/integration/test_dev_orchestration.py` runs S-01 with
P-01 to P-03 registered, for the repository connector, the coding worker and the model they
use: each ends *changed*, every step through a person, because every step those integrations
serve names a person as its fallback (issue #90, `blueprints/dev-orchestration/README.md`).

## S-05 Guides

UC-13.6 asks for two guides beyond the repository — one for the people who administer Taktus,
one for the people who use it — in the organisation's own knowledge system, current every day.
They are generated from the repository and never written: a page says what the repository says
at one commit, and names the files and the commit (ADR-0065). This process makes that daily
(ADR-0066).

**What one run does:**

1. **read-manifest** — reads `docs/guides/guides.yaml` at the configured ref through
   `repository.files.read`; the answer names the commit the ref resolved to.
2. **sources** — lists the files the manifest's pages take parts from (`exact`).
3. **read-sources** — reads every one of them at that commit, in one call of
   `repository.files.read_many`, so that the pages say what the repository said at one moment
   even when the branch moves while the run reads.
4. **render** — renders every page of both guides by rule (`exact`): the same commit always
   gives the same page.
5. **read-held** — reads once what the knowledge system holds at the guides' place, through
   `knowledge.pages.list`.
6. **measure** — measures every page against that reading by rule (`exact`): absent, current,
   changed, edited, out of date, foreign or retired (ADR-0065 §5).
7. **publish** — writes the pages measured absent or changed, against the same reading, each
   write naming the text it replaces. A page a person edited is kept, and so is a page a person
   edits while the run writes. Every page written is an egress record in the ledger.
8. **report-edits** — raises a report of every page kept because a person's text stands, with
   its difference from the repository, to the person responsible for the documentation: whoever
   the tenant's owner-facing channel reaches with the role `documentation` (ADR-0045). One edit
   is reported once, however many daily runs find it. A tenant whose channel carries no such
   role cannot be told: the step fails and names the role, and the page stays as the person
   left it.
9. **report** — one line: how many pages were created, updated, kept and withheld.

Steps 2, 4, 6, 7 and 8 are calls of `orchestrator.guides`, served by the loopback connector:
rendering, measuring and publishing are the knowledge component's, raising a report the
reporting component's (`composition/guides.py`). The knowledge system is a wiki's connector
(issue #197) or, where the organisation keeps none, the directory the instance serves when
`TAKTUS_KNOWLEDGE_DIRECTORY` names one.

**From its trigger.** The bundle's trigger says `daily`: on an instance that runs `taktusd`
with the `scheduler` role and has S-05 registered, the elected scheduler starts one run every
day at 00:00 UTC, with the trigger's inputs (ADR-0035). The runs act for the identity that
registered the bundle. Register it once:

```bash
uv run taktusctl submit --process blueprints/self-operation/processes/S-05-guides.yaml \
    --input manifest_path=docs/guides/guides.yaml --input ref=main \
    --input responsible=documentation --input within_days=7
```

and let the owner-facing channel carry the role `documentation` (`taktusctl owner-channel set`,
with `documentation` among the `roles` of the file it reads). `tests/integration/test_time_triggers.py` runs it from
its trigger on a clock the test moves; `tests/adapters/connectors/test_guides_process.py` runs it
end to end against a fake repository service and a fake knowledge system.

**Switching it off** — `uv run taktusctl deactivate --process s05-guides` — stops the trigger.
Nothing in the repository changes: the process never writes there, and the repository's
documentation under `docs/` is complete without it. The guides stay as they were last
published, until a person removes them.

### Its autonomy, with the reason

Level 3: every value is the repository's text, rendered and measured by rule; the one outward
write replaces only a page that holds exactly what Taktus last wrote there; a person's edit is
kept and reported, never overwritten. Toward level 4: a month of daily runs whose pages a person
sampled against the repository and found to say what it says, and whose reported edits reached
the person responsible; then Taktus proposes the raise with that evidence (M3.9).

### By hand — the takeover test of this process

A person does the same without Taktus (ADR-0013 B). It needs a checkout of the repository and
`taktusctl`; for a wiki, write access to it.

1. **Update the checkout** to the commit the guides are to say: `git fetch` and
   `git switch --detach origin/main`.
2. **Check** that every page renders: `uv run taktusctl guides check`. A page whose file or
   section is gone, or that would carry an address or a key, is named with the reason; fix the
   repository first.
3. **Publish** into a directory: `uv run taktusctl guides publish --to <directory>`. It reads every
   file at that one commit through `git`, never from the working tree, and writes only a page
   that holds exactly what was written there last.
4. **Read what was kept.** Exit code `1` means a page was edited by hand and kept; its
   difference is printed. Send it to the person responsible for the documentation, who decides
   whether the edit becomes a change to the repository or the page goes back to the
   repository's text.
5. **For a wiki**, until its connector exists (issue #197): copy each page that the command
   printed as `created` or `updated` from the directory into the wiki, at the same place.

