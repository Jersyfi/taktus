---
id: UC-6.13
title: Signals against corridors, and a daily report of only what deviates
component: reporting
serves: [P7, P8, P9, P14]
state: verified
version: 0.4.0
tests: [tests/components/reporting/test_corridors.py::test_a_value_that_is_no_measurement_is_named_never_normal, tests/components/reporting/test_corridors.py::test_a_language_model_s_value_never_counts_as_history, tests/components/reporting/test_signals.py::test_a_corridor_on_a_step_that_cannot_measure_is_refused, tests/components/reporting/test_corridors.py::test_fixed_bounds_turn_yellow_and_red_exactly_beyond_their_thresholds, tests/components/reporting/test_corridors.py::test_a_median_corridor_is_computed_from_the_step_s_own_earlier_results, tests/composition/test_signals.py::test_a_red_value_measured_by_a_run_is_an_incident_and_reaches_the_owner_at_once, tests/components/reporting/test_signals.py::test_each_change_is_a_version_with_who_made_it_and_when, tests/components/reporting/test_signals.py::test_a_process_or_a_worker_that_changes_a_corridor_is_refused_and_recorded, tests/components/reporting/test_signals.py::test_a_red_value_raises_an_incident_and_reaches_its_role_at_once, tests/components/reporting/test_signals.py::test_a_yellow_value_waits_for_the_daily_report, tests/components/governance/test_signal_incidents.py::test_a_red_value_raises_one_incident_however_often_it_is_looked_at, tests/components/governance/test_signal_incidents.py::test_a_further_red_value_is_recorded_on_the_open_incident, tests/components/reporting/test_signals.py::test_the_daily_report_lists_only_what_deviates_and_names_what_was_not_measured, tests/components/reporting/test_signals.py::test_the_daily_report_says_so_when_nothing_deviates, tests/components/reporting/test_signals.py::test_a_missing_measurement_is_never_shown_as_normal, tests/components/reporting/test_corridors.py::test_each_line_names_the_run_the_step_and_the_case, tests/components/reporting/test_signals.py::test_a_reply_that_intervenes_is_confirmed_before_its_process_starts, tests/components/reporting/test_signals.py::test_a_reading_rejected_or_from_someone_not_named_starts_nothing, tests/composition/test_signals.py::test_the_daily_report_s_reply_starts_the_intervention_as_a_command, tests/components/reporting/test_signals.py::test_a_corridor_that_names_a_person_is_refused, tests/components/reporting/test_corridors.py::test_a_signal_is_about_the_operation_a_role_or_a_department_never_a_person]
adrs: {ADR-0008: e6a4e033abd4, ADR-0021: dc801ddd1c47, ADR-0082: c64fba9bd04a}
supersedes: null
---

# UC-6.13 — Signals against corridors, and a daily report of only what deviates

## 1. What must be achieved

An operation is steered by a few dozen figures: yesterday's cloud cost, the error rate, the
model credit left, recurring revenue, cancellations. Each is normal within a band and alarming
outside it. A person who reads every figure every day stops reading.

A **signal** is a figure a process measures on a schedule. Its history is the results of the
step that measured it. A **corridor** is the signal's band: a yellow and a red threshold, as a
multiple of the signal's median over a window, or as fixed bounds. Corridors are configuration,
versioned, and changed only by a person.

Every morning Taktus reports only what left its corridor. Each line carries a link to the run
that measured it and to where the case is worked. A person can intervene from the reply.

## 2. How it is verified

- A signal is the result of a step of method `rule` or `statistics`, with exactness `exact` or
  `sourced` and a provenance record. No language model produces a signal's value.
- A signal's median and its corridor are computed from the step's own recorded results. A test
  feeds a series and finds yellow at the first value beyond the yellow threshold and red beyond
  the red one, and nothing within.
- A corridor is part of the tenant's configuration, with a version. A change records who made
  it and when. A process or a worker that tries to change one is refused, and the refusal is
  recorded.
- A red signal raises an incident (UC-6.8) and reaches the role its corridor names at once. A
  yellow one waits for the daily report.
- The daily report lists only signals outside their corridor, and says so when there are none.
  It also names every signal that could not be measured. A missing measurement is never shown
  as normal.
- Every line links to the run and the step that measured it, and to the case in the tool where
  it is worked.
- A reply to the report that names an intervention becomes a command (UC-1.5). Its
  interpretation is confirmed before it runs (ADR-0008).
- No signal measures a named person. A signal about people's work is aggregated by role or
  department (principle 14).

## 3. Where the boundary lies

**Not a data warehouse or a dashboard of everything.** A signal is a figure a process measures
for steering; analysis of the business's data stays in its own tools (UC-5.6). **Not result
checks.** Whether a step's result is wrong is UC-4.10; a signal outside its corridor may be
entirely correct. **Not the weekly trend report.** Trends within corridors are UC-6.2.

## 4. What it rests on

Requirements 11 and 12 of the catalogue behind UC-03; UC-03 B-1.01, B-1.03, B-1.04, B-2.01,
B-2.03, B-6.03, B-8.04 and B-9.01; DEC-0199; NTC-0210. Checks from a fixed catalogue
(ADR-0082); incidents (ADR-0021, UC-6.8); reports on a schedule (UC-6.2). Its version is
`0.4.0`, because the daily report opens stage 0 of UC-03.
