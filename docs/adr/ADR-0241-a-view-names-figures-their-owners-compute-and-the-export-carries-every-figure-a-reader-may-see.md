# ADR-0241 — A view names figures their owners compute, and the export carries every figure a reader may see

**Status:** accepted · builds on ADR-0029, ADR-0015 and ADR-0055 §5 · serves UC-6.4, UC-5.7,
UC-6.10 · DEC-0228

## Context

UC-6.4 asks for views defined per role, given to a person beyond their roles by configuration,
with the roles entitled to each figure declared, and no figure with a named person as its
subject. UC-5.7 asks that every figure any view shows leaves Taktus too, with the same
definition and the same value, and only to a reader entitled to it. UC-6.10 holds its figures
to the run's own record "until the export exists". ADR-0029 forbids a figure defined in
`reporting`: every number is its owner's.

## Decision

### 1. A figure is handed in by its owner

A **figure** is a value with an identifier (`value.time_saved_hours`, `run.working`), the
component that owns it, its definition in one sentence, its unit, its scope — the tenant, a
process, a value stream, an organisational unit, a role or a supplier, never a person — its
period, its value or the reason it is withheld, the basis it was computed from, and two marks:
whether it rests on an assumption, and whether it is a simulation. The owner defines and
computes it; the composition gathers the figures of every owner once per read and hands them
to `reporting`, which only selects among them (`reporting/domain/service/views.py`). The value
component's figures come from ADR-0244; the overview's counts `run.working` and `run.waiting`
are read from the overview level itself, so the representation and the export cannot differ.

### 2. Views and entitlements are the tenant's configuration

The tenant's **view configuration** holds:

- the **views**: an identifier, a title, the figures it shows, the roles that hold it, the
  persons it is given to beyond their roles, and the unit it groups by (`tenant`, `process`,
  `stream`, `unit`, `role`); grouping by person is refused when the configuration is stored;
- the **entitlements**: per figure, the roles entitled to it;
- per role, the **depth** and the **language** of an explanation (ADR-0243).

A reader holds the views whose roles they hold, and those given to them. A view shows only
the figures the reader's roles are entitled to: giving a view never widens an entitlement. A
figure the reader is not entitled to is absent, not greyed out. A figure of what Taktus took off
people — the time saved and its personnel equivalent — is withheld where no role that would do
the work by hand is held by two identities or more, and says why (ADR-0015, NTC-0168, UC-13.5).
A person's own view is the exception, and only they read it (ADR-0245).

Until a tenant stores a configuration, the shipped default holds: five example views — the day,
the team, management, the executive, the investor — each held by `owner`, and every figure
entitled to `owner`. A person holding `owner` stores a configuration (`PUT
/views/configuration`); `views.configured` records it with the person in `refs.actor` and the
configuration's digest.

### 3. The export is the same gathering

`GET /figures` answers every figure the reader is entitled to, as JSON; `GET /figures.csv` the
same rows as CSV, an open format any business-intelligence tool reads. `GET /views` answers the
reader's views with their figures. Both are composed from one gathering, so a figure in a view
is in the export with the same identifier, definition and value; a test fails a figure shown
and not exported.

### 4. Nothing is bound to the dashboard

Every action the web app takes is a route of the HTTP surface, which the other channels and any
client reach as well; a test reads every path the web app calls and finds each in the surface's
OpenAPI document. A figure of the organisation's business-intelligence tool is read through the
capability `bi.figures`, whose one operation reads and none writes; a process step reads it as
an input, and a process on a schedule trigger that reads it and decides by a rule step is how
it triggers.

## Alternatives

- **Views in the web app only.** Rejected by ADR-0029: a channel, a report and the export must
  hold the same rule.
- **An export endpoint per figure family.** Rejected: two gatherings could disagree; one
  gathering is the guarantee of one value.
- **Pushing figures into the business-intelligence tool.** Not built: UC-5.7 asks for export,
  interface or push; the interface and the file are the two built.

## Where this promise ends

- That a figure's definition is its owner's holds by review: nothing detects a definition
  written in `reporting` (ADR-0029).
- The export is read on request; nothing pushes it as it changes.
- A view shows the figures the gathering computes; a figure an owner does not hand in cannot be
  configured into a view, and the configuration refuses it.
- The small-group rule counts identities holding a role now, not when the figure's period ran,
  and it holds the figures of relief; a figure of a process done by one person's role in
  another way is not seen.
- The scan of the web app's paths reads the literal paths in its sources; a path built at run
  time from parts it cannot read is not checked.
