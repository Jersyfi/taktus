# ADR-0191 — A stage counts only processes that run, and shows its evidence per process

**Status:** accepted · extends ADR-0137 (a tenant introduced in stages) and ADR-0109 (signals
and the daily report) · issues #400, #437, #401, #438, #439, #440, UC-9.6, UC-03 §5

## Context

ADR-0137 built the stages: a plan, a ceiling, an opening by a person, a fall by rule. Building
the second tenant's introduction on it (UC-03 §5) met four gaps.

1. **A stage could hold over nothing.** The condition counts what the stage's processes did.
   A process the tenant never registered does nothing, so it misses no expected run, raises
   no incident and leaves no proposal waiting. Stage 0's condition — four weeks, no missed
   run, nothing undecided — therefore held after four weeks of a tenant that ran nothing. UC-03
   §5 says stage 0 opens once the tenant's first processes are *registered*.
2. **The daily report is not a process.** UC-03 §5 says stage 0 holds when "the report ran
   every day". The daily report of signals is the instance's (ADR-0109 §5): the scheduler raises
   it for every tenant with a corridor in force, and records `report.raised` for the report
   `signals-<YYYYMMDD>`. No process version stands behind it. The blueprint nevertheless named
   it as the process `b-9-01`, which no tenant can register.
3. **The blueprint's stages did not name its bundles.** `stages.yaml` named `b-1-01`; the bundle
   of B-1.01 was `b-1-01-daily-cost`. A ceiling matches a process by its identifier, so the
   shipped plan neither capped nor granted the shipped bundle. B-1.01 also stated level 3,
   while UC-03 §4 says every process starts at level 1 or 2 when its stage opens.
4. **The evidence was the command line's alone.** UC-9.6 §1 asks that the business sees at any
   time which stage it is in, what the next one needs and what is missing. `taktusctl stage show`
   is read by the operator of the instance. The person who opens a stage is the business's, and
   the view showed figures summed over the stage, not which process lacked what.

## Decision

### 1. A stage opens, and holds, only over processes that run

A process **runs for the tenant** when the tenant has an active version of it (ADR-0137 §7,
`ProcessLevels.running`).

- A stage opens only once every process it adds runs. Otherwise the opening is refused with
  the reason `not_run`, recorded as `stage.refused`, and the view's *missing* names each process
  as "<tenant> runs no version of <process>". The check comes after the predecessor's and
  before the takeover instructions', since instructions belong to a version.
- An open stage holds only while every process it adds runs. A process deactivated after the
  opening is missing from the condition. A stage that held then falls, by ADR-0137 §4.

This is a rule of the plan, not a figure of the condition. It binds every stage of every plan,
and a tenant cannot leave it out.

### 2. The days without the daily report are a figure

The condition gains a seventh figure, `reports_missed`: at most this many whole UTC days of the
window passed without the tenant's daily report. A day counts as reported when the ledger holds
`report.raised` for the report `signals-<YYYYMMDD>` of that day. A day counts once it has
ended, and only if it began at or after the window's start. A rehearsal's entry counts for
nothing (ADR-0030). A tenant with no corridor in force receives no daily report, so each of its
days counts as missed. That is the intent: without a corridor nothing was measured.

The governance component reads the kind and the prefix from the ledger. It imports nothing of
the reporting component; the prefix is restated as a constant beside the rule.

Like every figure, it is a floor in a blueprint (ADR-0137 §6): a plan that leaves it out, or
sets it higher, is looser.

### 3. The view shows each process

Every stage in the view carries `processes`: one entry per process it adds, with

| Field | Meaning |
|---|---|
| `process` | the process identifier |
| `version`, `level` | its active version and the level it runs at now; absent where the tenant runs none |
| `granted` | the level the stage lets it reach once open |
| `runs`, `missed`, `incidents`, `last_finished` | what it did within the stage's window; zero for a stage not open |

The entries are counted per process from the same ledger entries as the stage's figures. None
names a person.

### 4. A blueprint names a process by its bundle's identifier

A stage names a process by the identifier its bundle carries. In `software-operations` that is
`b-<area>-<number>`: B-1.01 is `b-1-01`, whether or not its bundle exists yet. The bundles of
B-1.01 and B-2.01 take those identifiers, and B-1.01 starts at level 2. B-9.01 leaves the stages'
lists. Stage 0's condition gains `reports_missed: 0`. A test holds every bundle of the blueprint
to an identifier its stages name, derived from its file name, and to a level of at most 2.

### 5. The stages on the HTTP surface

- `GET /stages` answers every stage as the view computes it, with the condition in words and
  one sentence on where it stands.
- `POST /stages/{stage_id}/open` opens a stage for the identity of the key or the session,
  under the rules of ADR-0137 §3 and §1 above. A refusal answers `409` with its reason. An
  unknown stage answers `404`.

Both are for an identity that holds the plan's **responsible role**. That role receives every
proposal to open a stage and every fall. Another identity of the tenant is answered `403`. The
command line keeps its own access: it authenticates by holding the instance's state.

## Alternatives

- **Count a process that is not registered as a missed run.** The figure `missed` would then
  mean two things, and a tenant could bound it above zero and so hold a stage without the
  process. Requiring the process to run is the plan's own rule.
- **B-9.01 as a bundle that raises the daily report.** The instance already raises it for every
  tenant with a corridor. A second path to the same report would let the two disagree on the
  day. Counting the instance's own report keeps one truth.
- **Rename `stages.yaml`'s entries to the bundles' long identifiers.** Every bundle still to be
  written would then have to guess the identifier the stages chose. A short identifier derived
  from the catalogue's number is known before the bundle exists.
- **Any identity of the tenant reads the stages.** The view names processes a reader may not see
  (ADR-0055 §5). The responsible role is the one the stages already report to.

## Consequences

- `Condition` gains `reports_missed`; `StageFigures` gains it too; `StageView` gains
  `processes`, of the new type `ProcessEvidence`. Stored plans without the figure read it as
  unbound: no migration.
- `Stages.open` refuses with `not_run`; an open stage misses every process that does not run.
- `blueprints/software-operations/stages.yaml` drops `b-9-01`, and stage 0 binds
  `reports_missed: 0`. The bundles of B-1.01 and B-2.01 are `b-1-01` and `b-2-01`. B-1.01
  starts at level 2.
- The REST interface gains `stages.py`; `RestServices` gains `stages`.

## Where this promise ends

- **"Runs" means an active version, not a run that happened.** A registered process that never
  starts — a schedule that never fires, an event that never comes — counts as running. Its
  missed expected runs are UC-4.16's: a schedule's missed run raises an incident and counts
  under `missed`. An event-triggered process that receives no event misses nothing.
- **The daily report is counted by its identifier, not by its content.** A report that was
  raised and could not be delivered counts as raised. Its delivery is the report's own record.
- **A day is a UTC day.** A tenant whose report hour falls late in another time zone's day is
  still counted by the UTC day its report names.
- **The HTTP surface opens a stage for the responsible role only.** Rights per role (UC-7.3) may
  later name another role. Until then the command line and the responsible role are the two
  ways.
- **Nothing here runs the business's stages.** Which processes the business registers, which
  systems serve them, and when a person of the business opens a stage stay the business's
  (DEC-0201). The product proves the rule against fakes; the four weeks of each stage are
  counted on the business's own instance.
