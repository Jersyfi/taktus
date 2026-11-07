# ADR-0240 — The automation coach finds a person's recurring requests by rule, and tells only them

**Status:** accepted · extends ADR-0015, ADR-0029 · UC-13.3, DEC-0228

## Context

UC-13.3 asks Taktus to point a person to work they repeat — "you ask this every Monday" — so that
they automate it for good. Hints must be few and switchable off; a dismissed hint must not return;
whether an accepted hint led to an automation that lasts must be recorded and shown to the person,
and to anyone else only by role or department. What the coach passes on to the skill lifecycle
must describe a procedure, never how a named person works. Principle 14 forbids any figure that
assesses a named person, and ADR-0015 keeps what concerns a person with that person.

## Decision

### 1. A pattern is found by rule among the person's own commands

A request is a command's intent, as recognised or as written, folded to lower case. A request on
the same weekday in three different weeks is a weekly pattern; otherwise a request made four
times within 28 days is a frequent one. A rule, never a model: the same requests give the same
hints. Only the person's own commands are read, and only those received since the coach was last
switched on.

### 2. The person sets the coach, and it is theirs alone

A person's settings are whether the coach is on and how many hints a week they receive, zero to
seven; the default is one. Switching it off is one setting: no request is read from then on, and
none made while it was off is ever read. A hint is offered once per person and pattern, ever: one
dismissed is not offered again. Every call names the identity that asks and reads only what
belongs to it.

### 3. Whether a hint lasted is read from the ledger

When the person accepts a hint, it names the process version it led to. After the tenant's
period — 28 days unless the tenant sets another — the hint is checked: it lasted when a run of
that version was created within the period before the check. The person sees the share of their
own checked hints that lasted. Anyone else sees the share only per role, over the people the
caller places in it.

### 4. What is passed on names a procedure

For a hint the coach produces a procedure draft: the request and its cadence, owned by the person
whose hint it is, naming nobody (UC-14.2).

## Alternatives

- **A model that clusters similar requests.** It would find more, but the same requests could
  give different hints, and a hint the person dismissed could come back worded differently.
- **Observing what a person does in their tools.** That is surveillance of a person's work,
  which principle 14 forbids; the coach reads only what the person asked Taktus for.

## Consequences

- `components/command/domain/model/coach.py`, `domain/service/coach.py`,
  `application/service/coach.py`.
- `migrations/versions/0101_steering_plan_drafts_and_coach.py`: `coach_settings`, `coach_hint`,
  `coach_policy`.
- `tests/components/command/test_coach.py`.

## Where this promise ends

- Two requests that mean the same but are worded differently are two requests.
- A hint is not shown on any surface yet: the web app and the chat do not present them, and the
  draft is not handed to the skill catalogue by any wiring. The use case's calls exist; their
  presentation does not.
- The check of a lasting automation looks for a run created within the period; an automation
  that runs less often than its period counts as not lasting.
- The share by role is computed over whatever roles the caller gives; it does not hide a role
  with one person in it.
