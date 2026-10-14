---
id: UC-6.13
title: Signals against corridors, and a daily report of only what deviates
component: reporting
serves: [P7, P8, P9, P14]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0008: e6a4e033abd4, ADR-0021: 202e0442e7ec, ADR-0082: c64fba9bd04a}
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
