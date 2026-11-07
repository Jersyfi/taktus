# ADR-0242 — A report is a reader role, a trigger and a channel, and its first level carries only what bears on the reader

**Status:** accepted · builds on ADR-0241, ADR-0045 and ADR-0109 · serves UC-6.2 · DEC-0228

## Context

UC-6.2 asks for reports on request and on a schedule, each with a reader and a trigger,
delivered in the channel the reader chose, whose first level carries only what bears a decision
or a consequence for the reader, and one sentence when nothing does. The owner's reports of
ADR-0045 carry one need each; the daily report of ADR-0109 lists signals. Neither is a report
for a role.

## Decision

### 1. A report definition

A **report definition** names its reader — a role — its trigger — `request`, or a schedule
`day` or `week` at an hour in UTC and, for a week, a weekday — and the channel and address
its reader chose. A definition without a reader is refused; so is a schedule without its hour.
A person holding `owner` stores it (`PUT /reports/definitions/{id}`); `report_definition.set`
records it with the person in `refs.actor`.

### 2. The first level

The report is composed from the figures the reader role is entitled to (ADR-0241) and from four
records, each over the report's period — since the last delivery, or the last day or week:

- a figure outside the target the tenant set for it (ADR-0244 §4);
- a decision request open whose decider is the reader role;
- a run escalated, of a process the reader may see;
- a run waiting for a person of the reader role.

A process proposed to be switched off (ADR-0244 §3) is added to every report whose reader is
`owner`, without being asked. Each item names a process, a role, a request or a figure, never a
person. Nothing else is on the first level; its last line names where the detail is. A period in
which none of these exists is one sentence that says so.

A report carries figures, never a step's result: a result of an `exact` or `sourced` step
reaches a reader through the process's own report step, which carries the exactness statement
(ADR-0226 §4).

### 3. Delivery

On request, `GET /reports/definitions/{id}/now` composes it for the asker, who must hold the
reader role. On a schedule, the scheduler's tick composes every due definition once per slot and
says it in the channel through the reporting port `Deliveries`, with the key
`report:<id>:<slot>`; the slot is stored on the definition only once the channel accepted it,
so a restart repeats nothing and loses nothing. `report_definition.delivered` records it. A
reply in that channel arrives through the channel's intake like every message to Taktus, and
becomes a command there (UC-1.1).

## Alternatives

- **A report designer.** Excluded by UC-6.2 §3.
- **Everything in the view, with deviations highlighted.** Rejected: an unread report is worse
  than none, and a long one goes unread.

## Where this promise ends

- A report's composition reads the records when it is composed; a record written after it is in
  the next report.
- The schedule has two cadences, a day and a week, in UTC.
- Delivery is the channel's: a channel that accepted the message and lost it is not seen.
- The text is composed by a template; a model does not phrase it.
