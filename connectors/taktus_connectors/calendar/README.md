# The calendar connector — iCalendar and CalDAV

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over iCalendar (RFC 5545), read from a published file or from a CalDAV server (RFC 4791): the
entries of one calendar within a window. Everywhere it is the capability `calendar.events`
(ADR-0197). The deadline calendar B-10.01 of the blueprint `software-operations` reads it.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.calendar --port 9121 --target https://calendar.example \
    [--caldav] [--zone Europe/Berlin]
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
server's base address; a call names the calendar's path under it and can reach no other host.
Without `--caldav` the path is read with `GET` as an iCalendar file; with it, as a CalDAV
calendar, by a `REPORT` with a `calendar-query` for the window. `--zone` is the zone a time
without one, and a whole day, is read in (default UTC). Added to an instance by one entry of
`TAKTUS_CONNECTORS`: `calendar.events=http://calendar-connector:9121/mcp`.

## What it declares

`calendar.events.list`, effect `read`, two requests at most.

| Input | Meaning |
|---|---|
| `path` | the calendar's path under the server's address, from one `/` |
| `from` | the window's start, an RFC 3339 date or moment; now when absent |
| `days` | the window's length, 1 to 400 (default 30) |
| `limit` | the most entries answered, 1 to 2000 (default 200) |

The output is `from`, `until`, `entries`, `unread` and `complete`. Each entry has `uid`, `kind`
(`event` or `todo`), `summary`, `description`, `categories`, `start` (an event) or `due` (a
to-do) in UTC and the same moment as `at` for either, `end` where the event has one, `all_day`, `repeats` and `key`, the uid and the
moment: what a process marks a filed deadline with. A rule of `FREQ` `DAILY`, `WEEKLY`,
`MONTHLY` or `YEARLY` with `INTERVAL`, `COUNT` and `UNTIL` is expanded; `EXDATE` removes an
occurrence and `RECURRENCE-ID` replaces one. An entry that is not read — a rule with a `BY`
part, a zone the time zone database does not know, no uid, no moment — is answered under
`unread` with the reason. How the server's answers map to the contract's causes is
`operations.py`'s: 400 `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404 `not_found`, 429
and 5xx `unavailable`, any other `unexpected`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `CALENDAR_TOKEN` | actions: the **requesting identity's** credential for the calendar's server, `user:password` as basic authentication or any other value as a bearer token | the file `TAKTUS_CREDENTIAL_CALENDAR_TOKEN_FILE` names, read at the moment of each call, never stored |

`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9121/mcp --scenario connectors/taktus_connectors/calendar/scenario.json
```

[`scenario.json`](scenario.json) lists the calendar of the fake under
`tests/fakes/calendar_service.py`; it names no write, and C-05 passes as not applicable.
`--fault NAME` breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault. CalDAV is proven against
the same fake in `tests/adapters/connectors/test_calendar_connector.py`.
