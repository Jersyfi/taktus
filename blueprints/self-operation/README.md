# Blueprint `self-operation`

The processes Taktus runs for itself, on itself: the checks of its own claims. This is the
first blueprint whose subject is Taktus, and its first process is the check of the product's
own central claim.

| Process | State | Bundle |
|---|---|---|
| **S-01 Removal test** — one integration is withheld, the processes that use it are exercised, the verdict is recorded | **runs** weekly | [`processes/S-01-removal-test.yaml`](processes/S-01-removal-test.yaml) |
| S-02 Takeover test — a person runs a process by hand from its instructions | `0.5.0` | — |
| S-03 Restore drill — an earlier version is restored without Taktus and the ledger chain verified | `1.0.0` | — |
| S-04 Load measurement — how many concurrent runs one instance carries | `1.0.0` | — |

## S-01 Removal test

Principle 13 and ADR-0003 promise that every integration can be removed: removing it changes
quality or cost, but breaks no process. Until this process existed, that promise had been
tested by nobody — the conformance suites report the removal test as *pending* (W-12, C-10;
DEC-0005), because a suite that talks to one adapter cannot remove it from processes. Now there
are processes, and this is the test. A test that runs once in its life proves nothing; one that
runs weekly is evidence.

**What one run does**, for one integration named as its input (`worker.endpoint`,
`connector.<label>`, `model.endpoint`, or `persistence.database`):

1. **describe** — reads from the instance what the integration serves, which other configured
   adapter serves the same, and which registered processes use it.
2. **admit** — checks that the integration is configured and of a known family (`exact`).
3. **exercise** — withholds the integration, runs every registered process that uses it, and
   restores it. An instance's configuration is its environment and does not change while it
   runs, so the three are one operation: the instance builds the same engine over the same
   stores with the integration left out of the adapter pools, runs the process through it, and
   the unchanged configuration is the restored state. A process is *run* only when running it
   cannot leave the system — no connector operation declared `write` or `delivery`, no worker
   with hosts it may reach — and every input it declares has an example; otherwise its verdict
   rests on *resolution* alone: which adapter would serve each step without the integration,
   and what the step's declared fallback is. A process that is run is run twice, with and
   without, and the two are compared by where each came to. Every rehearsal run is a real run
   in the ledger.
4. **describe-after** and **verify-restored** — read the configuration again and check that the
   integration is there and serves what it served (`exact`).
5. **verdict** — checks that the result carries exactly one of three verdicts (`exact`).
6. **record** — writes the result to the adapter's maturity and to the ledger as
   `removal.tested`, in one transaction.
7. **report** — one line a person reads.

**The three verdicts.** *Broke*: a step loses its only adapter and nobody takes it over — no
alternative adapter, and no fallback to a person. *Changed*: every process still reaches its
point — another adapter served the step, or the step falls back to a person, who does it at a
person's cost; quality and cost changed, nothing broke. *Exception*: the integration cannot be
removed by design; the database is the one (ADR-0002), and its removal test is the restore
drill. The verdict is a rule over what was observed (`components/catalog`,
`domain/service/removal.py`), never a judgement, which is why the `verdict` step is `exact`.

**Where it reaches the instance.** Every step is a call of a capability — `orchestrator.
integrations`, `orchestrator.removal`, `orchestrator.maturity` — served by the *loopback
connector*, through which Taktus reaches itself (`src/taktus/adapters/driven/connectors/
loopback/`, `docs/architecture/contracts.md` §4). Its operations stay inside Taktus and write
no egress entry. The removal test never lists the loopback as an integration: Taktus is not an
integration of Taktus.

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

The bundle's trigger says `weekly`; the scheduler starts it from the trigger once it acts on
triggers (`0.2.0`). Until then the script is the schedule.

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
   step it ended at, and the consumption line.
4. **Measure.** For every step the integration served: does another configured adapter serve
   it? If not, does the step's `fallback:` name `human`? If neither, the process *broke*. If the
   reduced run reached the same point as the original, or stopped exactly at a step a person
   takes over, the process *changed*. The integration's verdict is *broke* if any process broke.
5. **Restore.** Put the configuration back and run step 1 again: the integration serves what
   it served.
6. **Record.** Write the verdict, the date, the processes and the run identifiers into the
   register of adapter maturity — today the `adapter_maturity` table, or the notes of the
   operating documentation — and keep the two runs' output as the evidence.

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
verdicts to the reasons above.
