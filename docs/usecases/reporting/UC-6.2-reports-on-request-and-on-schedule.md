---
id: UC-6.2
title: Reports on request and on a schedule
component: reporting
epic: E6
serves: [P7, P9]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-6.2 — Reports on request and on a schedule

## 1. What must be achieved

Taktus reports — when asked, and on a schedule — compactly and in the channel the reader chose.
The report says what the reader has to know or decide, and nothing more; the detail is there when
the reader asks for it. An unread report is worse than none, because it creates the impression
that somebody is watching.

## 2. How it is verified

- Every report has a reader — a role — and a trigger: a request, or a schedule. A report configured
  without a reader is refused.
- A report is delivered through the channel its reader chose, and a reply to it reaches Taktus as a
  command (UC-1.1).
- The first level of a report carries only what bears a decision or a consequence for its reader:
  a figure outside its expected range, a decision waiting for them, an escalation, blocked work.
  Everything else is one request away and not in the report. A period in which nothing was outside
  its range is reported in one sentence that says so.
- A figure in a report has the definition and the value it has in the reader's view (ADR-0029).
- A report that carries a result of an `exact` or `sourced` step carries the exactness statement of
  the process behind it (UC-6.9).
- A report never names a person as the subject of a figure (principle 14).

## 3. Where the boundary lies

**Not a report designer.** The layout of a report is not configurable beyond its reader, its
trigger and its channel. **Not the wording.** A report may be phrased by a language model, and the
figures in it are never produced by one. **Not delivery guarantees** of the channel. **Not
incidents**, which are raised into the organisation's own tracking (UC-6.8).

## 4. What it rests on

The views of UC-6.4 and the component that owns them (ADR-0029); the channels of UC-1.1; the
exactness statement of UC-6.9. Definition `UC-6.2`.
