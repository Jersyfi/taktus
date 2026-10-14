---
id: UC-4.16
title: An expected run that does not happen is an incident
component: run
serves: [P6, P10, P12]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0021: 202e0442e7ec, ADR-0023: 949c6f4e13af, ADR-0035: 070012ed0fb2}
supersedes: null
---

# UC-4.16 — An expected run that does not happen is an incident

## 1. What must be achieved

A watcher that stopped running looks exactly like a watcher that found nothing. Both are
silent. A business whose operation depends on Taktus cannot tell them apart unless Taktus
does.

Every process with a schedule or an expected cadence therefore declares when a run is
expected. Every run ends with one of three outcomes: `ok`, `empty` (it ran and found nothing to
do) or `error`, and its duration. A run that was expected and did not start, or did not end
within its bound, raises an incident by itself. Taktus watches this; no process has to watch
itself.

## 2. How it is verified

- A process version can declare its expected cadence: a schedule, or a longest gap between two
  runs. A scheduled process without one inherits its schedule as the expectation.
- Every completed run records `ok`, `empty` or `error`, and its duration, in the ledger.
  `empty` is never recorded as `ok`, and an `error` is never recorded as `empty`.
- A test stops the scheduler for one process. When the expected run's time and the tenant's
  grace period have passed, exactly one incident is raised (UC-6.8). It names the process, the
  expected time and the last run that did happen.
- A run that started and has not ended within its declared bound raises an incident in the same
  way.
- The decision that a run is missing is a rule over the schedule and the ledger. No model
  decides it (ADR-0023).
- A missed run that later happens closes nothing by itself. The incident records it, and a
  person or the incident's rule closes it.
- A process switched off or stopped on purpose (UC-7.2) raises no incident while it is off.
- A process whose `empty` outcomes exceed a share the tenant sets over a window is reported. A
  watcher that never finds anything may be blind.

## 3. Where the boundary lies

**Not the schedule itself.** When a time trigger fires is ADR-0035. **Not a deadline in a case.**
A case unanswered beyond its limit is UC-4.17. **Not monitoring of outside systems.** Whether a
website is up is the business's process (UC-03 B-1.06); this use case watches Taktus's own
runs. **Not a measure of anyone.** A missed run is the process's, never a person's.

## 4. What it rests on

Requirement 5 of the catalogue behind UC-03, heartbeat and dead man's switch; UC-03 B-11.01;
DEC-0199; NTC-0210. The incident it raises is UC-6.8; the vocabulary of failure and incident
is ADR-0021; a stop by rule is ADR-0023; time triggers fire once per slot through the elected
scheduler (ADR-0035). Its version is `0.4.0`, because stage 0 of UC-03 depends on every watcher
being seen to run.
