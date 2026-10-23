# ADR-0133 — A deadline is declared in the process and kept by the elected scheduler

**Status:** accepted · extends ADR-0035 (the elected scheduler), ADR-0023 (a rule decides a stop) and ADR-0015 §4 (deadlines with handover) · issue #430, UC-4.17

## Context

Much of an operation is about time. A support case is answered within a day. A data protection
request has a legal deadline. A certificate expires in thirty days. UC-4.17 asks that such a
deadline be a rule of the process, kept by Taktus, and never a timer inside a worker or a
system outside: a timer is lost with whatever held it, and nobody sees all of them at once.
UC-03 needs it for a software business (B-3.08, B-3.12, B-10.01, DEC-0199).

Four words are used below. A **case** is one run of a process: what the deadline is about. A
deadline **starts** at a moment the process names. It **falls due** at its limit, counted from
that moment. It is **met** when the event that satisfies it happens before or after it falls
due. The **lead time** is a stretch before the limit at which a first action is taken.

The engine had a clock for waits (ADR-0103) and the scheduler had a clock for slots
(ADR-0035). Neither knew a deadline.

## Decision

### 1. A process version declares its deadlines

A bundle may declare `deadlines`, a mapping from a name to a deadline:

```yaml
deadlines:
  first_answer:
    from: run                       # or {after: <step>}, or {date: <input>}
    limit: 1d
    lead: 4h                        # optional
    counts: working                 # or calendar, the default
    until: {step: answer}
    at_lead: {remind: support}
    at_limit: {escalate: support-lead}
```

- **`from`** is the moment it starts: `run`, when the run is created; `{after: <step>}`, when
  the step finished; or `{date: <input>}`, the date or moment an input of the run names, such
  as the day a certificate expires.
- **`limit`** is how long after that moment the deadline falls due. It may be `0`, for a date
  that is itself the limit.
- **`lead`** is how long before the limit the lead action is taken. It is optional.
- **`counts`** is `calendar` or `working`. Working time is the tenant's configuration (§4).
- **`until`** names the step whose finish meets the deadline: `{step: <step>}`.
- **`at_lead`** and **`at_limit`** are the actions. Each is exactly one of
  `{remind: <role>}`, `{escalate: <role>}` or `{start: {process: <process>, inputs: {...}}}`.

A deadline without `at_limit` is refused at registration, and so is a `lead` without
`at_lead`, an `at_lead` without a `lead`, a step or an input the version does not declare, a
role that is not a token, and an action naming anything but a role or a process. A reminder and
an escalation name a role, never a person (UC-1.4, principle 14). Who holds the role is the
organisation's structure.

The deadlines are part of the version and stored with it (migration 0068).

### 2. A run carries its version's deadlines, and its ledger starts and meets them

When a run is created, it takes a copy of its version's deadlines, as it takes the steps and
their work. A run created before its version declared one has none.

Every entry the run engine records for a run is looked at in the same transaction:

- An entry that is the moment a deadline starts — `run.created` for `run` and `{date: ...}`,
  `step.finished` of the named step for `{after: ...}` — opens a deadline record and writes
  `deadline.started`. The record holds when it falls due and when its lead time begins. Its
  identifier is derived from the run and the deadline's name. A run that records the same
  moment again opens nothing new.
- An input that does not read as a date or a moment starts nothing. The ledger records
  `deadline.refused` with outcome `no_date`.
- `step.finished` of the step `until` names, with any outcome but `failed` or `skipped`, meets
  the deadline: `deadline.met`.
- `run.finished` ends every deadline of the run still open: `deadline.met` with outcome
  `run_finished`. A run that finished has nothing left to answer. A run that escalated keeps
  its deadlines: the case is still open.

A rehearsal starts no deadline: it acts on nothing outside (ADR-0030).

### 3. The elected scheduler takes each action once

While it leads, the scheduler looks at the deadlines of every tenant it serves on every tick
(ADR-0035). A deadline whose lead time began and whose lead action was not taken is due for
it. So is a deadline that fell due and whose limit action was not taken. A deadline met before
either moment has no action left.

An action is taken in one transaction, with its ledger entry:

- `deadline.lead` at the lead time and `deadline.reached` at the limit, each with the kind of
  the action as outcome (`remind`, `escalate` or `start`). Each entry names the run and the
  deadline.
- The record notes that the action was taken.

The entry is written first. Writing it takes the tenant's ledger lock (issue #317). Under the
lock the record is read again. If another scheduler took the action meanwhile, the transaction
is rolled back. The action is therefore taken once, also by two schedulers that both believe
they lead.

A reminder and an escalation are kept on the deadline: the role it is addressed to, and when.
The role's holders read it where they read the decision requests addressed to their role, on
the control plane's own surface (`taktusctl deadline list --role`).

A start runs the named process's active version through the one path every channel takes, as a
schedule trigger does (ADR-0035 §4 to §6). The run's identifier is derived from the deadline
and the moment, so a start repeated after a crash meets the run it started. It acts for the
identity that registered the started process's active version (ADR-0040). Its `run.triggered`
entry names a trigger of kind `deadline`. A start the engine refuses is recorded as
`deadline.reached` with outcome `refused`, and is not tried again.

A deadline restarts nowhere. It lives in the database, and every instance that leads reads it
from there.

### 4. Working time is the tenant's configuration

A tenant's working time names a time zone, the working days of the week, the hours of a working
day and the dates that are not working days. `taktusctl deadline working-time` sets it. A
tenant that set none holds the shipped default: Monday to Friday, 09:00 to 17:00 UTC, no
holidays (NTC-0227). It is the tenant's, never a person's.

A deadline that counts in working time counts its limit and its lead in working hours only. A
limit of `1d` in working time is one working day of the tenant's configuration: eight hours
under the default. A deadline that starts outside working time begins to count at the next
working hour.

### 5. Every open deadline can be listed

`taktusctl deadline list` prints a tenant's open deadlines ordered by when they fall due, each
with its case, its process version, its lead time, whether it is overdue, the actions taken and
the link to its case's page in the web app. `--role` narrows the list to the deadlines whose
reminder or escalation went to that role.

The list names no person. A deadline missed is the case's and the role's. Nothing in this
decision measures how fast anyone answers: there is no response time per person, and no
aggregate of one (ADR-0015, principle 14).

### 6. Every check is a rule

| Check | Method | Reason | Rejected |
|---|---|---|---|
| whether an entry starts or meets a deadline | `rule` | the same entries must start and meet the same deadlines, and a person must be able to check it from the ledger | `llm` — a judgement whether a case was answered would differ from one run to the next |
| whether a deadline is due for an action | `rule` | an escalation is a stop of the waiting, and a stop is decided by a rule (ADR-0023) | `statistics` — a predicted answer time would escalate cases the facts do not escalate |

Each produces a decision, not a result of the process. The decision is `exact`, and `exact`
admits a rule (ADR-0014, ADR-0023 §4). The facts it read — the record's moments and the
clock — are recorded with it.

## Alternatives

- **A `wait` step as the timer.** A wait parks one run at one step (ADR-0103). It cannot wait
  beside the step that answers, and it cannot be listed across processes.
- **A timer per worker or per connector.** That is what UC-4.17 forbids: the timer is lost with
  what holds it.
- **A deadline computed from the ledger on every look.** The ledger holds no date input, and the
  list would read every run of the tenant on every tick.
- **Deadlines on the decision request.** A request has a due date (ADR-0042). A deadline runs
  across steps that are not decisions, such as a case waiting for an outside answer.
- **A deadline met by an event of the intake.** The intake does not say which run an event
  belongs to. The step that reads the answer meets the deadline.

## Consequences

- `ProcessVersion.deadlines` and `Run.deadlines`. Migration 0068 adds the columns
  `process_version.deadlines` and `run.deadlines`, and the tables `deadline` and
  `working_time`.
- The run's port `DeclaredDeadlines`, answered by the composition root from the process
  component (`composition/decisions.py`).
- The run's domain model `Deadline`, `DeadlineRule`, `DeadlineAction` and `WorkingTime`, the
  domain service `deadlines`, and the application service `DeadlineKeeper`.
- The scheduler's tick `composition/deadlines.py`.
- `refs.deadline_id` in `contracts/shared/v1/LedgerEntry.json`, optional, so every entry
  written before is unchanged. The ledger kinds `deadline.started`, `deadline.refused`,
  `deadline.lead`, `deadline.reached` and `deadline.met`.
- `taktusctl deadline list` and `taktusctl deadline working-time`.
- UC-4.17 is `building`.

## Where this promise ends

A deadline's action is taken at the first tick of a leading scheduler after its moment. No
scheduler, or a database it cannot reach, delays it, and the record keeps the moment it was due
beside the moment it was taken. Time is the clock of the instance that leads, as for a slot
(ADR-0035).

A deadline is met only by the step `until` names, or by its run finishing. An answer given
outside Taktus that no step reads does not meet it. A run abandoned while halted keeps its
deadlines open in the list for good. A run that started before its version declared a deadline
has none, and a new version's deadlines apply only to runs created from it.

A reminder and an escalation are kept on the deadline and listed for the role. They are not
delivered into a chat or a mail of the role's holders: that is the owner-facing channel's, and a
role's channel is not built (#85). A start acts for the identity that registered the started
process; a process registered by nobody starts nothing, and the refusal is recorded.

Working time knows a zone, days, one stretch of hours a day and holidays by date. Two stretches
in one day, such as a lunch break, are counted as one. Which deadline the law sets is the
tenant's to declare (UC-4.17 §3). The list reads every deadline of the tenant, open or not.
