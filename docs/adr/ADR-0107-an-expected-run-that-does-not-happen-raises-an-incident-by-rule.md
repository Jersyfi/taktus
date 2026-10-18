# ADR-0107 — An expected run that does not happen raises an incident by rule

**Status:** accepted · extends ADR-0021 (the first incident Taktus raises), ADR-0023 (a rule decides it) and ADR-0035 (what a schedule expects) · issue #427, UC-4.16

## Context

A watcher that stopped running looks exactly like a watcher that found nothing. Both are silent.
Stage 0 of the second tenant needs every watcher to be seen to run (UC-03 B-11.01, DEC-0199).

Four facts shape the decision.

- A run ends in the ledger as `run.finished` or `run.escalated`. Neither says whether the run found anything to do, and neither carries how long the run took.
- A schedule trigger whose `each` list is empty starts no run (ADR-0035 §5). Such a firing leaves nothing in the ledger, so it cannot be told from a firing that never happened.
- The scheduler fires only while it leads, and a slot that passed during an outage is fired late, once (ADR-0035). Nothing notices that a slot was late or never fired.
- No incident exists yet. ADR-0021 defines the word and UC-6.8 places the tracked object, with its delivery, at `0.5.0`.

## Decision

### 1. A process version declares when a run is expected

A bundle may carry `expect` at its top level:

| Field | Meaning |
|---|---|
| `schedule` | a run is expected at every slot of this schedule, in the form of ADR-0035 §1 |
| `gap` | the longest time between the starts of two runs, as a duration |
| `bound` | the longest time a run may take from its start to its end, as a duration |

`schedule` and `gap` exclude each other. A version without either inherits its schedule triggers: each schedule trigger expects a run at each of its slots. A version with neither, and no schedule trigger, expects no run. `bound` stands on its own beside any of these.

### 2. Every run ends `ok`, `empty` or `error`, with its duration

The run engine writes `run.ended` in the same transaction as `run.finished` and as `run.escalated`.

- A run that escalated ends `error`, whatever its steps returned.
- A run that finished ends `empty` when a step whose work carries `empty_when_skipped: true` was skipped because its `when` did not hold. Otherwise it ends `ok`.
- Its duration is the time from the run's creation to this end. It is carried in the entry's new field `duration_seconds`.

A halted run and a run waiting for a person have not ended. A run that escalated and is resumed ends again, with the outcome of that end.

A firing whose `each` list is empty records `trigger.empty` for the process version, with outcome `empty` and the duration of the read. The watcher counts it as a run that happened and found nothing.

### 3. The rule that a run is missing

The scheduler applies the rule to every tenant it serves, once a minute while it leads. It reads the active version of every process, the tenant's watch configuration and the tenant's ledger. A rehearsal's entries count for nothing (ADR-0030).

- **A missed slot.** The latest slot at or before `now − grace` of each expected schedule is expected, when it lies after the version was activated. The run happened when the ledger holds a `run.started` or a `trigger.empty` of the process between the slot and the slot plus the grace. Otherwise the run is missing.
- **A missed gap.** A run is expected at the start of the process's last run plus the gap. Without a run since the version was activated, the activation counts as the last start. The run is missing when that moment plus the grace has passed.
- **An overrun.** A run is overdue when it started more than its bound plus the grace ago and has neither ended nor been stopped by a person since.

`grace` is the tenant's. Given the same schedule, ledger and configuration, the rule yields the same answer. No model decides it (ADR-0023 §1).

### 4. What a missing or overdue run raises

An **incident** is a record of its own in the governance component, one row per incident. It names the process and its version, the expected time, the last run that did happen, the rule that fired and the facts it read. Its identifier is derived from the tenant, the process, the rule and the expected time or the run. A second look at the same miss finds the same incident and raises nothing. The ledger records `incident.raised`, with the incident in `refs.incident_id` and `missed` or `overdue` as the outcome.

While a missing-run incident of a process is open, a further miss of that process is recorded on it and raises no second incident. A run that happens after a miss closes nothing. The watcher records it on the incident as `incident.recorded` with outcome `happened`. A person closes the incident, recorded as `incident.closed` with the person as actor. The incident itself names no person (principle 14).

A process that is switched off has no active version, so it expects nothing while it is off (UC-13.6). A run a person stopped is never overdue.

### 5. A watcher that never finds anything is reported

The tenant sets a share, a window and a minimum number of runs. A process whose `empty` ends exceed the share of at least the minimum of ends within the window is reported. The ledger records the crossing as `watch.empty_share` with outcome `exceeded`, and `ok` once it falls back. The log says so, and `taktusctl incident blind` lists every process whose share is exceeded.

### 6. The tenant's watch configuration

A tenant that configured nothing holds the shipped default: a grace of 15 minutes, and an empty share above 90 % of at least 10 ends within 30 days (NTC-0212). `taktusctl incident configure` sets it.

## Alternatives

- **Use `slo.freshness` and `slo.latency` as the expectation.** They describe the service a reader is promised: how fresh a result is, how long a run takes. A watcher can promise a fresh result while it runs more often than that. Giving one field two meanings would make either change the other.
- **Keep a watch state per process, read forward through the ledger.** It would read each entry once. It would also be a second memory beside the ledger, and the rule would answer from it, not from the ledger.
- **One incident per missed slot.** An hourly watcher down for a day would raise 24 incidents for one cause. The incident records every miss instead.
- **A run that happens closes the incident.** A watcher that ran three hours late may still have missed what it was watching for. Whoever looks at it decides that.
- **Derive the duration from two entries' timestamps.** The entry that ends a run would not say how long it took, and every reader would join two entries to know it.
- **Mark an empty run by a model's reading of its result.** An outcome that varies between two readings of the same result is no heartbeat. A declared `when` that did not hold is a fact of the run.

## Consequences

- `LedgerEntry.json` gains `duration_seconds` and `refs.incident_id`, both optional. The ledger table gains the column, and an index finds a process's entries by kind and time (migration 0056).
- The process version gains `expect`. The tables `incident` and `watch_configuration` are new (migration 0056).
- A step's work gains the control key `empty_when_skipped`.
- The ledger store answers a process's entries of given kinds since a moment, and the newest of them, without reading the chain.
- The scheduler's tick runs the watcher. `taktusctl incident` lists, closes and configures.

## Where this promise ends

The watcher runs while a scheduler leads. With no scheduler, nothing is fired and nothing is watched. The next leader raises the misses it can still see: the latest slot of each schedule, the gap, and runs started within a day before their bound plus the grace. A slot older than the latest one is not looked at again. An overrun that began more than a day before its bound and grace ran out, while no scheduler led, is not raised. A version activated before activation times were recorded (ADR-0048 §6) is not watched until it is registered again. Time is the clock of the instance that leads, as for the triggers. A run is `empty` only where its bundle declares a step that marks it. Every other finished run is `ok`, including one that found nothing and does not say so. The incident is recorded in Taktus and logged. Delivering it into the organisation's tracking system, its severity, its situation package and its report are UC-6.8, at `0.5.0`. An incident is closed by a person. A rule that closes one arrives with UC-6.8.
