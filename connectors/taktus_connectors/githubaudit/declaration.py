"""What the audit connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `audit.events`, of effect `read`: reading an audit log changes
nothing. Each page of an answer is one request, so the demand names one unit and the
consumption counts every page (ADR-0005). The investigation stays a person's (UC-03 B-5.04).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "audit.events"
ACTIONS_CREDENTIAL = "AUDIT_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "audit.events.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The privileged actions of the past `hours` (default 24), up to `limit` "
        "(default 1000, at most 10000), newest first: each its id, when (`at`, and `hour` in "
        "UTC), the `action`, the account that acted, what it acted on, and `escalation`, "
        "whether the action grants rights. `actions` counts the events per action, never per "
        "actor. `complete` says whether every event was read.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 3600},
        "permissions": "passthrough",
    }
