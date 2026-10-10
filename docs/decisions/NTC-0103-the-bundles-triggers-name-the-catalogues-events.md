# NTC-0103 — The bundles' triggers name the catalogue's events, and P-03 has none yet

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#76](https://github.com/Jersyfi/taktus/issues/76), in the pull request that closes it

## 1. What was decided

The event triggers of the dev-orchestration bundles were written before the events contract and
named events it does not have. Now:

- **P-01 Roadmap control** (version 3): `roadmap.changed` became `branch.pushed` with the filter
  `branch: main, paths: docs/roadmap.md`, and the inputs its daily trigger gives.
- **P-02 Refinement** (version 4): `issue.opened` keeps its kind and takes the issue's number
  from the event. Its filter, "a section of the ready standard missing", is gone: the step
  `missing` already refuses an issue that lacks nothing.
- **P-03 Implementation** (version 4): no trigger. The blueprint's `issue.ready` is
  `issue.labelled` with `label: ready` and `capacity.available`, and its trigger is in the bundle
  as a comment. It cannot be active yet: a run started by an event has nobody to ask, and the
  input `closing_section` can only be given by whoever starts the run until the worker generates
  it (DEC-0037, issue #77). P-03 starts by hand, as it did.

## 2. The evidence

- `contracts/events/v1` §2 maps the blueprint's names; ADR-0048 §7 refuses a version whose event
  trigger leaves an input without a value.
- `tests/integration/test_dev_orchestration.py` registers the three bundles at their new
  versions; `tests/components/process/test_event_triggers.py` shows that P-03 with the trigger
  in place is refused, for `closing_section` alone.

## 3. What was considered

- **Give `closing_section` an empty value in the trigger.** Rejected: the repository generates
  one, so a pull request opened with an empty one fails its description check — a run that would
  look started correctly and fail at its end.
- **Keep P-02's filter and have a model read it.** Rejected by ADR-0048 §2: whether a run starts
  is a rule over the event alone.

## 4. Which entry permits it

M2.4, inside the scope of issue #76, whose boundary names this case. No limit, level or published
contract moves; P-03 runs exactly as before.
