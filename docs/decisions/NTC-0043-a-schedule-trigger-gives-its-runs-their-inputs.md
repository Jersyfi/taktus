# NTC-0043 — A schedule trigger gives its runs their inputs

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** issue [#69](https://github.com/Jersyfi/taktus/issues/69)

## 1. What was decided

A trigger in a bundle was `schedule` or `event`, with `filter` and `condition`, and the
schedule was free text. Now a schedule trigger says when, precisely, and what its runs are
given (ADR-0035 §1 and §5).

- **When:** a five-field cron expression in UTC, or `hourly`, `daily`, `weekly` (Mondays
  00:00 UTC) or `monthly`. A schedule that cannot be read, or matches no day, is refused when
  the bundle is registered.
- **What it gives:** `inputs`, fixed values, and `each`, one run per item of a list a
  connector's `read` operation answers — `input`, `operation`, `select` and an optional
  `field`. Together they give every input the process declares and none it does not, or the
  version is refused at registration. Both belong to a schedule trigger only.
- **S-01** carries `each` over `orchestrator.integrations.list`: the weekly trigger starts one
  run per integration the instance lists, as `tools/removal_test.sh` did by hand.

## 2. The evidence

- S-01 declares the input `integration` and is meant to run "once per configured integration"
  (`blueprints/self-operation/processes/S-01-removal-test.yaml`, the script's loop). A schedule
  alone gives a run no input; the run would be refused, or run on the example only.
- `tests/components/process/test_schedule.py` holds the slot arithmetic, the refusals and the
  input rule; `tests/integration/test_time_triggers.py` runs S-01 from its trigger for both
  integrations a test instance lists.
- No bundle in the repository had a schedule other than `weekly` (S-01); the persistence
  sample's `0 6 * * 1-5` reads as before. The blueprint overviews (`blueprint.yaml`) are not
  parsed as bundles; their `nightly` is description.

## 3. What was considered

- **Give a scheduled run the declared examples.** An example shows the shape of an input. S-01
  would test `worker.endpoint` alone every week and call that the removal test.
- **One trigger per integration in the bundle.** Integrations are the instance's
  configuration, not the bundle's; a bundle cannot know them.
- **A cron dependency.** A technology import in the core is what `tests/architecture` forbids,
  and five fields fit in a page of standard Python.
- **Accept a free-text schedule and fail when it fires.** A schedule nobody can read would be
  found by its silence, weeks later. Refusing at registration says it at once.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #69,
whose purpose is that S-01 runs weekly on an instance without the workflow; S-01 needs its
input to run at all. The bundle format is not a published contract until `0.3.0`
(`contracts/process/v1`, ADR-0019); no limit or level moves.
