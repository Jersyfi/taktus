# ADR-0271 — A result is judged against the moving median, and its window found by the check again

**Status:** accepted · extends ADR-0082, ADR-0153, ADR-0179, ADR-0185 · UC-4.10, UC-4.11 ·
DEC-0228

## Context

UC-4.10 names four families of check. Three are rows of the catalogue (ADR-0185); the first,
**distribution** — the result lies where the step's earlier results lie, within a band around
their moving median, of the same sign — had no row: a bound is fixed in the bundle, and does not
move with the series. UC-4.10 also requires that a check declares its method, `rule` or
`statistics` and never a language model, and that the result of a step that declares no check is
recorded as **unchecked**, never as passed.

UC-4.11 requires that the window of a result defect starts at a change found over the provenance
chain, including a source whose content changed; and, where no change is found, at the earliest
result the check would have marked, the check run again over the recorded results. The analysis
of ADR-0153 found a change in how the step produced only, and with none started at the first
record.

## Decision

### 1. Distribution is a row of the catalogue

`{"kind": "distribution", "window": <n ≥ 3>, "band": <share > 0>}` (`contracts/shared/v1`,
additive). Its method is a statistic: the median of the step's `window` earlier results. A result
passes when it lies within `band` times the median's size of the median, and has the median's
sign. Fewer earlier results than the window judge nothing yet, and the finding says so.

### 2. It judges after the result counted, and marks it suspect

A distribution is applied once the step's result counted, as a sample is. Its earlier results are
the step's results in the process's earlier runs that finished — every version of the process,
never a rehearsal — read from the object store by each run's checkpoint. A result that fails is
marked suspect: `check.suspect`, its family `distribution`, what it compared, naming the median
and the band. The run goes on: a statistic that flags a result does not stop it (UC-4.10). The
mark is a finding of ADR-0179 §2, raised as a result defect by itself.

### 3. A check declares its method, and a result without one is unchecked

A check may name `method`: `statistics` for a distribution, `rule` for every other row, and
nothing else; without it, the row's own holds. A result of a step of class `tolerant` or `free`
that declares no check is recorded as `result.unchecked` beside its `step.finished`, never as
passed. A rehearsal records none.

### 4. A cause in the content of a source

Where no change in how the step produced is found, the analysis compares the shape of what each
result of the series read: the result itself where the step read a source, otherwise the results
of the steps it read. The shape is an object's keys with the shape of each value, a list's items,
a table's header row (`defects.shape_of`). The first result after the shape changed starts the
window, and the cause names `source_content` with the shape before and after.

### 5. No change found: the check again

Where no change is found at all, and the check that marked the result judges the value alone — a
distribution, bounds, the shape of the source — it is run again over the recorded results of the
series, each against those recorded before it. The earliest it marks starts the window, recorded
as `rechecked_from`. A check that reads a source is not run again: the source cannot be read as
it was. Where nothing can be run again, the window starts at the first record, as before.

## Alternatives

- **A distribution that fails the step before its value counts**, as every other row does
  (ADR-0152). A monthly total that is right and unusual would stop every month it is unusual;
  UC-4.10 says a check never stops a run by itself.
- **Bounds derived by a statistic and written into the bundle.** The bundle would change with
  every result.
- **`result.checked` for every result that passed.** The checks' own entries already say it;
  only the absence of a check needed saying.

## Consequences

- `Check.json` gains a row and three properties; every existing document is valid as it was.
  The compatibility tool reports the new `allOf` branch as breaking; no release exists, so
  nothing is enforced (ADR-0019 rule 2), as for ADR-0185.
- `result.unchecked` is a new ledger kind; `check.suspect` names `distribution` as a family.
- `ResultDefects` takes the port `RecordedContents`, which the composition answers
  (`composition/contents.py`).

## Where this promise ends

- **What follows a failed check** — `escalate` or `stop` per check — is the rule's of ADR-0023,
  not declared on the check; UC-4.10 says otherwise, and NTC-0268 records the restatement, which
  lands apart.
- **A slow drift passes**: each result against a median that drifts with it.
- **The earlier results are read in full each time**: a step with very many runs reads every
  `step.finished` of the tenant to find its own.
- **A shape is structure, not value**: a source that keeps its form and changes its meaning is not
  found as a cause.
