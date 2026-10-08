# NTC-0045 — P-01's daily trigger reports on issue #129

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#127](https://github.com/Jersyfi/taktus/pull/127)

## 1. What was decided

P-01 Roadmap control (#128) declares three inputs: `roadmap_path`, `records_path` and
`report_issue`, the number of the one issue labelled `report` whose comments carry its
reports. Its bundle has a `daily` schedule trigger. Since ADR-0035 a schedule trigger gives
every input the process declares, or the version does not register (NTC-0043).

- **Old:** the daily trigger named no inputs. The report issue did not exist; #128 said a
  person opens it when P-01 first runs for real. With ADR-0035 the bundle no longer registered.
- **New:** the issue exists: #129, "P-01 Roadmap control — reports", labelled `report` (the
  label created with it). The daily trigger gives `roadmap_path: docs/roadmap.md`,
  `records_path: docs/decisions/open` and `report_issue: 129`. The bundle registers, and an
  instance's elected scheduler runs P-01 daily at 00:00 UTC. `blueprint.yaml` and the
  blueprint's README say the same.

## 2. The evidence

- CI run 37858890719 of #127, after #128 merged: `gate-exactness` failed four tests on
  "the schedule trigger 'daily' gives no value for the input(s) records_path, report_issue,
  roadmap_path".
- `tools/backlog.py` already leaves out issues labelled `report` (#128), so #129 is not work
  and does not enter the backlog.

## 3. What was considered

- **Declare `report_issue` with a default the trigger carries once the issue exists.** The
  issue would still have to be opened before P-01 runs, and the bundle would carry a value
  that is wrong until then.
- **Keep the trigger, and let the version register without being schedulable.** The rule of
  NTC-0043 exists so that a trigger that cannot fire is said at registration, not found by its
  silence weeks later. An exception for one bundle would undo it.
- **Drop the daily trigger until the issue exists.** P-01's purpose is a daily report
  (`blueprint.yaml`). Removing what makes it daily, to avoid opening one issue, is the weaker
  option.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is #127, which
made schedule triggers act; P-01 must satisfy its rule to register. Opening an issue labelled
`report` is what #128 already said a person does before P-01's first real run. No contract,
limit or level moves.
