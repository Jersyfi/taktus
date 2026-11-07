---
id: UC-6.2
title: Reports on request and on a schedule
component: reporting
epic: E6
serves: [P7, P9]
state: built
version: 0.5.0
tests: [tests/adapters/rest/test_figures.py::test_a_report_without_a_reader_is_refused_and_one_with_one_tells_what_bears_on_it, tests/adapters/rest/test_figures.py::test_a_quiet_period_is_one_sentence, tests/components/reporting/test_views_and_reports.py::test_a_report_needs_a_reader_and_a_schedule_needs_its_hour, tests/components/reporting/test_views_and_reports.py::test_the_first_level_carries_only_what_bears_on_the_reader]
adrs: {ADR-0029: 37c061ef032a, ADR-0242: d86032064894}
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

## 5. What is proven so far

Built (ADR-0242). By the named tests: a report without a reader is refused; a scheduled one is
said in its reader's channel once per slot; its first level carries decisions waiting for the
role, escalations and blocked work of processes the role takes part in, figures outside their
target and, for `owner`, a process proposed to be switched off; a quiet period is one sentence;
no line names a person. Not yet shown by a test: that a reply to a report reaches Taktus as a
command — it arrives through the channel's intake like every message (UC-1.1).
