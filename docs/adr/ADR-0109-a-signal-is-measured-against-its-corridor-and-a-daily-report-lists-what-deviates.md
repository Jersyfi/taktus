# ADR-0109 — A signal is measured against its corridor, and a daily report lists what deviates

**Status:** accepted · builds UC-6.13 on ADR-0045 (the owner's channel), ADR-0106 (a report of
what needs a person) and ADR-0107 (the incident) · issue #428

## Context

Stage 0 of the second tenant is a daily report (UC-03 B-9.01, DEC-0199). A person reads it every
morning and intervenes from it. It lists only figures that left their band. UC-6.13 states the
requirement.

Five facts shape the decision.

- A step's result is stored in the object store. The ledger entry `step.finished` names it by
  its digest, beside the step's method. Its provenance record names the method and the
  exactness class (ADR-0021).
- The ledger store reads a process's entries of given kinds since a moment, without reading the
  chain (ADR-0107).
- The governance component keeps incidents, one row each, raised by rule (ADR-0107).
- A report to the owner goes through the owner-facing channel. A decision request reaches the
  owner when its role is one the channel carries (ADR-0045).
- A tenant's configuration that a person sets records who set it as the actor of its ledger
  entry, never as a field beside its figures (ADR-0107 §6, principle 14).

## Decision

### 1. A signal is the result of one step, read at one place

A **corridor** is the tenant's configuration of one signal. It names the signal, the process and
the step that measures it, and the place in the step's result where the number stands
(`select`, a dotted path). The step's result is the signal's value. The history of the signal
is the results of that step in earlier runs of the process.

A value counts only when four things hold. The step finished with outcome `succeeded`. Its
method is `rule` or `statistics`. Its exactness is `exact` or `sourced`. A provenance record of
the step run exists, and it says the same. Otherwise the value is no measurement. A step of
method `llm` therefore never produces a signal's value.

A corridor may only name a step of the process's active version whose declared method and
exactness admit it. Otherwise it is refused when it is configured.

### 2. The corridor's two thresholds

A corridor has a yellow and a red threshold and a direction, `above` or `below`.

- **`median`**: each threshold is a multiple of the median of the signal's admissible values
  within `window` before the value judged. Above, `1 < yellow ≤ red`; below, `red ≤ yellow < 1`.
  With fewer than `minimum` such values the corridor cannot be computed.
- **`fixed`**: each threshold is a bound. Above, `yellow ≤ red`; below, `red ≤ yellow`.

A value beyond the red threshold is **red**. A value beyond the yellow threshold and not beyond
the red one is **yellow**. A value at a threshold is within it. Every other value is **normal**.

A signal is **not measured** when its newest attempt failed, when its newest value is no
measurement or no number, when no attempt lies within `fresh` before now, or when its median
cannot be computed. The reason is a token: `failed`, `not_admissible`, `not_a_number`,
`no_measurement` or `too_little_history`. A signal not measured is never shown as normal.

Nothing else decides. No model, no estimate and no reading of words is involved (ADR-0023).

### 3. A corridor is versioned, and changed only by a person

Each change of a corridor is a new version, stored beside the earlier ones and never changed.
Its identifier is `<signal>@<version>`. The newest version is in force. A retired version ends
the signal.

The ledger records each version as `corridor.changed`, with the person in `refs.actor` and the
digest of the version in `content_digest`. Who changed it and when is read from that entry. The
corridor itself names no person.

A change is refused when it comes from a run or from a worker's assignment. It is refused when
the identity is not one the tenant knows. Each refusal is recorded as `corridor.refused`, with
the reason as outcome: `process`, `worker` or `unknown`. The only surface that changes a
corridor is `taktusctl signal configure`, which acts for the identity it names.

A corridor names what it is about: the operation, a role or a department. It never names a
person. A corridor whose signal or subject is the name of an identity the tenant knows is
refused. A signal is one number, so a signal about people's work is a figure of a role or a
department (principle 14).

### 4. A red signal is an incident and reaches its role at once

The corridor names a role. It is refused unless the tenant's owner-facing channel carries that
role, because the channel is how a role is reached (ADR-0045).

While the scheduler leads, it looks once a minute. A corridor whose process recorded no new
`step.finished` since the last look is not judged again. A red value raises an incident in the
governance component, of kind `signal.red`. Its identifier is derived from the tenant, the
process, the signal, the run and the step. While a red incident of the signal is open, a further
red value is recorded on it as `red`, and raises no second incident. The ledger records
`incident.raised` or `incident.recorded`, with outcome `red`.

The same red value raises a report of kind `failure` through the owner-facing channel at once.
Its identifier is derived from the incident and the run. It names the value, the thresholds,
the run, the step, the incident and the case. A yellow value raises nothing until the daily
report.

### 5. The daily report

Every day from 06:00 UTC, the scheduler raises the tenant's daily report once, as a report of
the new kind `signals`. Its identifier is `signals-<date>`. A tenant without a corridor in force
gets none.

It lists every signal that is red or yellow, and every signal not measured with its reason. When
none is, it says that every signal was measured within its corridor. A normal signal is not
listed.

Each line names the run and the step that measured the value, and the time. It links the run's
page in the web app when the channel names the control plane's address. Each corridor names the
address of the case: where a deviation of the signal is worked. Every line carries it.

### 6. A reply that intervenes is a command, confirmed first

A corridor may name processes that intervene. The report offers to start each of them, worded
by the phrasebook's `intervene`. A reply in the report's thread is read by rule against these
offers and the words for "done". The reading is sent back, and nothing runs before the same
person confirms it (ADR-0008). Only the owner, or someone the owner named, may answer
(UC-1.7).

A confirmed intervention becomes a command on behalf of that person. It is commissioned as a
plan of the process's active version and submitted as a run. The reply names the run. The report
is filed with the run as its record. An intervention that cannot start is answered with the
phrasebook's `act_refused`, and the report is open again.

## Alternatives

- **Declare the signal in the process bundle.** The bundle is written by whoever writes the
  process, and the corridor must be changed only by a person of the tenant. The step's own
  declaration of method and exactness is checked when the corridor is configured.
- **Keep the last judgement per signal in a table.** It would be a second memory beside the
  ledger and the results, and it could disagree with them. The judgement is computed from the
  recorded results each time.
- **Judge from the provenance records alone.** They name no outcome of a failed attempt, and a
  failed attempt must name the signal as not measured.
- **A yellow value at once.** A person who is told every small move stops reading. The red value
  is the one that cannot wait for the morning.
- **One incident per red value.** A daily signal red for a week would raise seven incidents for
  one cause. The incident records every further red value instead.
- **The report hour per tenant.** No tenant needs another yet. A fixed hour needs no further
  configuration, and moving it later changes no stored record.

## Consequences

- `reporting`: `Corridor`, `Subject`, `Recorded`, `Judged`, the rule `domain/service/corridors.py`,
  the ports `Measurements`, `MeasuringSteps`, `RedIncidents` and `Interventions`, and the use
  cases `Corridors` and `SignalWatch`. `ReportKind.SIGNALS`, and the phrasebook's optional
  `signals`, `intervene` and `intervened`.
- `governance`: `IncidentKind.SIGNAL_RED`, the timeline's `red`, and the use case
  `SignalIncidents`.
- Migration 0058, the table `corridor`, one row per version.
- `composition/signals.py`: the readers over the ledger, the object store and the provenance
  store, the incident and the intervention, and the scheduler's tick. `taktusctl signal`.

## Where this promise ends

A signal is measured only where a process runs the step that measures it. A corridor schedules
nothing. Its `fresh` says when a missing measurement is named, and the watch over expected runs
says when the run itself did not happen (ADR-0107). A value is read from a JSON result. A step
whose result is an artifact of another type yields no number. The method and exactness of a
value are what its provenance record says. They are not checked again against the work the
step did.

The scheduler judges while it leads. With no scheduler, no red is noticed and no report is
raised. The next leader judges the newest value of each signal at once, and raises the report
of the day once. A red value that was followed by another value before any look is not judged.
Only the newest value of a signal is judged at each look. A day the scheduler did not lead at
all has no report.

A red reaches its role through the owner-facing channel, and only while the channel carries
that role and its connector delivers. A role reached elsewhere is not supported. The incident
is raised either way. Its delivery into the organisation's tracking system is UC-6.8, at
`0.5.0`.

The daily report is raised at 06:00 UTC for every tenant. A tenant without an owner-facing
channel gets none, and `taktusctl signal list` shows its signals judged. Its lines link the run's page only
when the channel names the control plane's address, and otherwise name the run and the step.
The case is the address the corridor names. Taktus does not check that it is reachable. An
intervention starts a process. It does not pause or cancel a run, which UC-1.5 brings at
`0.5.0`. A process that needs inputs cannot be started from the report. The rule that a
corridor names no person rests on names: a person's identity kept under an unrelated name is
not recognised.
