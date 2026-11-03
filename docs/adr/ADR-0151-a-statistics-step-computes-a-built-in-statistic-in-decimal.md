# ADR-0151 — A statistics step computes a built-in statistic, in decimal

**Status:** accepted · amends the run's executors (`domain.model.work`) · builds on ADR-0109
(a signal is judged against its corridor) · serves UC-03 B-1.01, UC-6.13 · issue #447

## Context

`statistics` is one of the eight method kinds, and one of the two that may produce an `exact`
figure (CLAUDE.md §3, §4). Until now no step of that kind could run: a plan with one was
refused before it started, because the method had no executor.

The cost watcher of UC-03 (B-1.01) judges the day's cost against the median of the weeks before
it and names the service behind a jump. Its cost is held `exact`. A median over a window is a
statistic of a series, not a fixed rule over one value (`docs/architecture/methods.md`). A
language model may not produce it, and a rule that takes one value cannot.

A corridor judges a signal against the median of the step's earlier results (ADR-0109). It
needs a week of runs before it can judge, and it judges one number. The provider's own history
is there from the first run, and the part behind a jump is not one number.

## Decision

### 1. A `statistics` step names one built-in statistic

A step of method `statistics` carries its work as `{statistic: <name>, …}`. The engine computes
it in the run, as it evaluates a rule: no worker, no model, nothing outside. The values it
reads are references to earlier results, resolved as a rule's are, and recorded in the step's
provenance. The step's declared method is `statistics`, so a corridor admits its result
(ADR-0109 §1).

### 2. The first statistic is `deviation`

`deviation` reads a series of days, each `{date, total?, groups: [{group, amount}]}`, with
amounts as decimal text: the shape a costs reading has (ADR-0150). It judges the newest day
against the `window` days before it (default 28), once there are at least `minimum` of them
(default 7). It answers:

- `day`, `total` and `total_text`: the newest day and its total;
- `median` and `median_text`: the median of the totals before it;
- `ratio`: the total over that median;
- `groups`: each group's amount, its own median and its change, the largest rise first;
- `driver`: the group that rose most above its own median, or none when none rose;
- `history`: how many days the medians were taken over.

### 3. Every figure is decimal, and checked

Every figure is computed in decimal arithmetic from the text the series gave, and reported as
that text. A number beside it, for a corridor to read, is the decimal turned into a number at
the end. A median of an even count is the mean of the middle two, exactly. A day whose total is
not the sum of its groups fails the step, as a value that is not a finite number does. With
fewer than `minimum` days of history there is no median, no ratio and no driver: the corridor
then says the signal was not measured, and never that it was normal (ADR-0109 §2).

### 4. The corridor stays the judge

The statistic computes; it does not judge. A tenant's corridor judges its `ratio` with fixed
thresholds, so it judges from the first run, or its `total` against earlier runs. A red value
raises an incident, as every red signal does (ADR-0109 §4).

## Alternatives

- **A rule that takes a series.** A rule is fixed logic over values; a median over a window is
  what `statistics` names. Calling it a rule would hide the method the step uses.
- **The corridor's median alone.** It judges the total only after a week of runs, and it cannot
  name the service behind a jump.
- **The statistic inside the connector.** A connector reads; it does not compute what a process
  is held to. The figure would leave the run's provenance.
- **A general expression language for statistics.** Each statistic is code the engine trusts
  with an `exact` figure. A built-in list is reviewed; an expression is whatever its author
  wrote.

## Consequences

- `src/taktus/components/run/domain/service/statistics.py`; `DeviationStatistic` in
  `domain/model/work.py`; the engine evaluates it beside the rules.
- A plan with a `statistics` step whose work names `deviation` runs. One naming another
  statistic is refused before it starts, as an unknown rule is.
- `blueprints/software-operations/processes/B-1.01-daily-cost.yaml` measures with it.

## Where this promise ends

There is one statistic, `deviation`. It reads days, not other periods, and compares the newest
day with the days before it in the series it was given; a day missing from the series is not
filled in. It converts no currency and checks none: its figures are in whatever unit the series
gave. The number beside each text is a floating-point number, exact as far as such a number
can hold the decimal. A day the provider has not closed is judged like any other. What the
corridor makes of the result is ADR-0109's promise, not this one.
