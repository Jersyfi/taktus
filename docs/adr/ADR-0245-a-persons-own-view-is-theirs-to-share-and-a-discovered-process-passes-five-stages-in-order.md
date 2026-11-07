# ADR-0245 — A person's own view is theirs to share, and a discovered process passes five stages in order

**Status:** accepted · builds on ADR-0015, ADR-0241, ADR-0244 · serves UC-13.5, UC-13.4, UC-9.4
· DEC-0228

## Context

UC-13.5 and UC-13.4 ask for a person's own view of what Taktus took off them — tasks, time
regained, goals they set and reached — visible to them alone unless they share it, never a
score. UC-9.4 asks that a process nobody wrote down passes five stages in order, each a ledger
entry, with the decision to automate a person's.

## Decision

### 1. The own view

`GET /me/relief?days=` answers, for the reader, every process that relieves one of their roles:
a process whose steps, fallbacks or roles by hand (ADR-0244 §2) name a role the reader holds.
For each: its runs finished in the period, the minutes a case takes by hand, the time regained
(`value.time_saved_hours` of the process, the same figure every view shows), and the link to
its takeover instructions. These are process figures; the view selects them by the reader's
roles. The view adds the goals the reader set — a title and the hours a week they want back —
each reached when the time regained in the last seven days meets it. There are no points,
levels, streaks, ranks or comparisons.

The view's settings are the reader's own record: the roles they share it with, their goals, and
how often a short line of it reaches their channel (`never`, `day`, `week`). Its one person
field is `reader`; `PUT /me/relief/settings` writes it for the reader alone. Another reader reads
`GET /people/{identity}/relief` only while it is shared with a role they hold; withdrawing the
share closes it at once. A share names a role, never a person.

### 2. A discovered process

A **discovered process** is a record of the value component: its title, what was found and
where — `interview`, `pattern` or `request` — and the role that owns it once documented. It
passes five stages, each recorded as a ledger entry: `discovery.visible`,
`discovery.documented` (a description and an owner role), `discovery.valued` (the minutes by
hand, from which its balance follows), `discovery.decided` (a person's decision, `automate` or
`keep`, with the person in `refs.actor`) and `discovery.automated` (a registered process whose
active version is at level 1 or 2 and carries takeover instructions). A stage is refused unless
the one before it is recorded. Taktus never records `discovery.decided`.

A pattern found in a person's own tools or requests is recorded for that person first, visible
to them alone, and becomes the organisation's only when they agree; it is then stated as a
procedure of the organisation, its finder no longer named on it.

The interview asks the same five questions in the guided and the expert mode and writes the
same documented process; the modes differ in the help given, not in what is recorded.

## Alternatives

- **An own view others can be granted by an administrator.** Rejected: showing it is the
  person's act (UC-13.5).
- **Automate on a high-confidence pattern.** Excluded by UC-9.4: discovery ends at a proposal.

## Where this promise ends

- What relieves a role is read from the process's declarations; a process that relieves a person
  without naming their role is not in their view.
- The short line in a channel is composed on the scheduler's tick; a channel the person has not
  linked receives nothing.
- Patterns are found by a rule over the recurring requests made of Taktus; patterns in connected
  tools are recorded when a process reports one, not searched for by Taktus.
