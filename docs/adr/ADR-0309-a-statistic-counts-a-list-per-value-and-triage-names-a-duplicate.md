# ADR-0309 — A statistic counts a list per value, and triage names a duplicate

**Status:** accepted · extends ADR-0151 (a statistics step), ADR-0192 §1 (selection by rule),
ADR-0207 (store reviews) and ADR-0310 (the statistic `total`) · serves UC-03 B-3.09, B-7.01 ·
issues #400, #401

## Context

Two processes of UC-03 stopped short of their row.

1. **B-3.09** finds *patterns across releases* in store reviews. The rules select a list
   (`filter`) and match two lists (`match`); none groups a list by a field. The blueprint's
   README named it as the gap.
2. **B-7.01** turns what arrives into issues *de-duplicated*, *weekly and on arrival*. The
   model was shown one issue, never the list, and only the arrival of an issue started a run.

Counting reviews per app version is arithmetic over a reading. It must therefore come from a
reproducible method, and the number is `exact` (CLAUDE.md §4). Whether two issues describe one
thing is a reading of two texts. It is never `exact`, whatever rule holds the answer afterwards.

## Decision

### 1. The statistic `count`

A `statistics` step may compute `count`: the items of a list counted per value of one field.

- `items` is a list of objects, usually a reading. `by` is a dotted path into each item.
- An item without the field, or with null, counts under null.
- A value that is a list or an object fails the step. A number is counted by its text.
- The result is `{by, items, groups, first}`. `groups` holds every value with its count, most
  first, ties by value, null last. `first` is the largest group, or null for an empty list.

The same list always gives the same counts. The step is admissible for `exact`.

### 2. B-3.09 counts its low ratings per release

Every run of B-3.09, version 3, lists the app's reviews of one or two stars through
`stores.reviews.list` and counts them per app version. The counts stand in the run's result
beside the reply a person releases. No model summarises what the reviews of one release say.

### 3. B-7.01 is shown the open issues and runs weekly

B-7.01, version 3, lists the open issues in every run.

- **Weekly.** A schedule starts a run without an issue. A rule takes the open issue with the
  lowest number that carries no `type:` label. Without one, every later step is skipped.
- **De-duplication.** A model is shown the issue beside every open issue. It names one by its
  number, or none. A rule takes the number by a fixed pattern, never the issue's own. The rule
  `match` holds it to an open issue. These steps stay `tolerant`: holding the number to an open
  issue does not make the reading true.
- **Effect.** The issue receives one comment naming the other, with the mark
  `duplicate-of:<number>`, once a person confirmed it. A comment already there keeps it from
  being written twice. Nothing is closed and nothing merged.

## Alternatives

- **A `group` rule beside `filter` and `match`.** A rule selects; counting computes. ADR-0310
  put the weekly sum among the statistics for the same reason.
- **A model summarising the reviews per release.** Its count could differ between two runs. A
  summary of what the reviews say may follow later, as a `free` step beside the exact counts.
- **Closing the newer issue as a duplicate.** Which of two issues stays is a person's
  judgement. A wrong close hides a report; a wrong comment costs a click.
- **B-7.01's weekly run classifying every unclassified issue.** One issue per run keeps one
  confirmation per label, as B-7.04 takes one pull request per run.

## Consequences

- `CountStatistic` joins `StatisticsWork`. `domain.service.statistics.count` computes it, and
  the run engine evaluates it like `total`.
- B-3.09 version 3 has the steps `read-low` and `by-release`. B-7.01 version 3 has a schedule
  trigger, an optional `issue`, and eight new steps.

## Where this promise ends

- **A count is no pattern.** B-3.09 shows how many low ratings each release received. What
  they complain about is read by a person. A store that names no version counts every review
  under null.
- **At most 500 reviews are counted.** The newest come first, so an old release may be
  under-counted.
- **A duplicate is the model's reading.** B-7.01 names a duplicate only among the open issues
  listed, at most two thousand. A duplicate of a closed issue is not found.
- **One issue per weekly run.** A backlog of unclassified issues is worked through one issue a
  week, unless a person starts more runs.
