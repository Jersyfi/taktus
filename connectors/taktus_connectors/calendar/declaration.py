"""What the calendar connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `calendar.events`, of effect `read`: a list reads and changes
nothing. Its demand is two requests, the most it makes: one for an iCalendar file, two for
CalDAV (ADR-0197).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "calendar.events"
ACTIONS_CREDENTIAL = "CALENDAR_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "calendar.events.list",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "List the entries of the calendar at `path` whose moment falls within the "
        "window of `days` (default 30) from `from` (now when absent): events by their start, "
        "to-dos by their due. Each answers its uid, summary, description, categories, its "
        "moment in UTC as `at`, whether it is all day and whether it repeats, and a `key` of "
        "its uid and its moment. A repeating entry is expanded where its rule is plain; one "
        "that is not read is answered under `unread` with the reason. `complete` says "
        "whether every entry fit within `limit`.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
