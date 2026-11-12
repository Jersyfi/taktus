"""What the log store connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `logs.query`, of effect `read`: reading log lines changes
nothing. One read is one request, so the demand names one unit and the consumption counts it
(ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "logs.query"
ACTIONS_CREDENTIAL = "LOGS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "logs.query.entries",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The log lines the LogQL query `filter` selects, passed verbatim, within "
        "the `since_minutes` (default 15, at most 44640) before now, or from `start` to `end` "
        "(RFC 3339, `end` default now); at most `limit` (default 100, at most 1000), newest "
        "first. Each entry is `timestamp`, `severity` (the stream's `level` or "
        "`detected_level` label, else null), `message` (at most 2000 characters), `source` "
        "(the stream's labels) and `id` (always null). A metric query is refused. `complete` "
        "is true only when fewer than `limit` lines came back. `source` as input is refused: "
        "the stream selector is part of the query.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
