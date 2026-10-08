# NTC-0042 — The scheduler fires the active version's schedule triggers

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** issue [#69](https://github.com/Jersyfi/taktus/issues/69)

## 1. What was decided

The scheduler role of `taktusd` used to lead and tick, and the tick did nothing with a
bundle's triggers. Now it starts runs from them (ADR-0035).

- **Old:** `triggers` in a bundle were recorded and not acted on. Registering a version stored
  it and nothing else; the process record and its `active_version` existed in the schema and
  nothing wrote them. S-01 ran weekly only through `.github/workflows/removal-test.yml`.
- **New:** registering a version through the daemon or `taktusctl` also writes the process
  record, with this version as the active one. While it leads, the scheduler reads the active
  version of every process in every tenant it serves, and starts one run per due slot of each
  schedule trigger. A trigger counts from the moment the scheduler first sees it. Missed slots
  start one run, for the latest. A run started by a trigger carries a `run.triggered` entry
  beside `run.created`; a run the engine refuses is a `trigger.refused` entry. The scheduled
  run acts as the tenant's provisional operator identity (DEC-0013); without one nothing fires
  and the log says so on every tick.

The workflow stays. It is retired by the task that retires the standing brief, once an
installed instance runs S-01 on its own (issue #69, "Where the boundary lies").

## 2. The evidence

- Issue #69 asks for exactly this, for `0.2.0` (`docs/roadmap.md`, "the scheduler starting runs
  from a bundle's trigger").
- `tests/integration/test_time_triggers.py` runs two scheduler daemons against PostgreSQL on a
  clock the test sets: a trigger not yet due starts nothing; the due slot starts one run with
  both running; the leader restarts and the slot is not fired again; the next slot fires once
  under the new leader; five slots missed with no scheduler start one run, for the latest; every
  run carries `run.triggered` with the digest of its trigger and slot. The second test registers
  S-01 on a Sunday, moves the clock past Monday 00:00 UTC, and both integrations the instance
  lists run to their verdict and to `removal.tested`.
- `tests/components/run/test_runner.py` holds the engine to refusing a derived run identifier a
  second time, with nothing of the second attempt landing.

## 3. What was considered

- **The scheduler fires every registered version.** Every `taktusctl run` registers its
  bundle, so two versions of one process would both fire. The active-version pointer exists
  for this (control-plane.md §4.2), and registration is the one place a version is chosen.
- **Arm a trigger at registration.** Registration would need the clock and another use case's
  state. Arming on first sight loses at most the first slot after a registration made while no
  scheduler ran; ADR-0035 says so.
- **Retry a refused run every tick.** A version without a budget refuses every time; retrying
  writes the same refusal every few seconds. The slot is recorded and the refusal is said once.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #69. No
published contract changes: the bundle format is not yet one (`contracts/process/v1` is a
placeholder until `0.3.0`); no limit or level moves.
