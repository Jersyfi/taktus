# ADR-0197 — A deadline calendar is read over iCalendar and CalDAV

**Status:** accepted · extends ADR-0111 (connectors over open standards) and ADR-0158 (every
connector is an image of its own) · serves UC-03 B-10.01, UC-4.17 · issue #437

## Context

UC-03 B-10.01 asks that the business's tax, contract, notice and renewal deadlines become tasks
with lead time. A business keeps such dates in a calendar. Calendars of every product exchange
their entries as iCalendar (RFC 5545). A calendar is either published as one iCalendar file over
HTTP, or served by a CalDAV server (RFC 4791), which answers a query for a time range.

No connector of this repository read a calendar. B-10.01 was listed as not built.

## Decision

### 1. One connector, `calendar`, with one operation

`connectors/taktus_connectors/calendar/` serves `calendar.events.list`, effect `read`: the
entries of one calendar whose moment falls within a window — `from` and `days` ahead. Each entry
answers its `uid`, `summary`, `description`, `categories`, `start`, `end` or `due`, whether it
is all day, and a `key` of its uid and its start. A process marks what it filed with the key, so
that each occurrence is filed once (ADR-0192 §1).

### 2. Two ways to reach a calendar, chosen by configuration

`--target` is the server's base address, and a call names the calendar's path under it, as the
check connector does (ADR-0111). Without `--caldav`, the connector reads the path with `GET` as
an iCalendar file and selects the window itself. With `--caldav`, it asks a `REPORT` with a
`calendar-query` for the window, once for events and once for to-dos, and reads the
`calendar-data` of each answer. The answer is parsed defused, as the document inbox's
(ADR-0169): one that declares a document type or an entity is refused unparsed.

### 3. What a deadline is

An entry is a `VEVENT` with `DTSTART`, or a `VTODO` with `DUE` or `DTSTART`. Its moment is its
start, or its due for a to-do. A date without a time is all day, at the start of that day in the
calendar's zone. A time with `TZID` is read in that zone from the time zone database. A time
without a zone is read in the zone `--zone` names, UTC by default. Every moment is answered in
UTC.

### 4. A repeating entry is expanded where its rule is simple

A deadline often repeats: each quarter, each year. An entry with `RRULE` of `FREQ` `DAILY`,
`WEEKLY`, `MONTHLY` or `YEARLY`, with `INTERVAL`, `COUNT` or `UNTIL` and nothing else, is
expanded into its occurrences within the window. A month or a year without the start's day has
no occurrence, as RFC 5545 counts it. `EXDATE` removes an occurrence, and an entry with
`RECURRENCE-ID` replaces its rule's occurrence at that moment. A rule with any other part —
`BYDAY`, `BYMONTHDAY`, `BYSETPOS` and the rest — is not expanded. The entry is answered once
under `unread` with the reason, so that a person sees what the connector did not read. So is an
entry without a uid or a moment, and one in a zone the time zone database does not know.

### 5. The credential goes to the calendar's server

The requesting identity's credential `CALENDAR_TOKEN` is sent as HTTP authentication. A value of
the form `user:password` is sent as basic authentication, which CalDAV servers ask for, and any
other value as a bearer token. A published file that admits anyone ignores it.

## Alternatives

- **A library for iCalendar and its rules.** It would expand every rule. It would also add a
  dependency to the image, whose libraries are the lock file's and audited (ADR-0158, ADR-0173).
  The rules a deadline needs are the plain ones; the others are named, not guessed.
- **Every entry, without a window.** A calendar holds years of entries. The window is what a
  lead time asks for, and the CalDAV server can apply it.
- **A product's own calendar API.** Every product with such an API also serves CalDAV or
  publishes iCalendar. One connector over the standard serves them all.

## Consequences

- A new connector and its image `taktus-connector-calendar`, a fake calendar server serving both
  an iCalendar file and CalDAV (`tests/fakes/calendar_service.py`), a scenario, and its rows in
  `CREDENTIALS.md`, the chart and the image workflow.
- B-10.01 is built: `blueprints/software-operations/processes/B-10.01-deadlines.yaml`.

## Where this promise ends

- **A rule with a `BY` part is not expanded.** Its entry is answered under `unread` and is
  never filed as a deadline. A tenant whose deadlines repeat that way enters them as plain
  rules, or a person files them.
- **The calendar is the business's.** Taktus reads what it holds. A deadline nobody entered is
  not found, and a wrong date in the calendar is filed as it stands.
- **Nothing is acted on.** The task is filed; acting on the deadline stays with a person
  (UC-03 B-10.01).
- **A moved occurrence is matched by its moment only.** An override whose `RECURRENCE-ID`
  carries `RANGE=THISANDFUTURE` moves only the one occurrence it names.
