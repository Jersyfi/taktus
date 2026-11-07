"""What the secret store connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `secrets.metadata`, of effect `read`: reading metadata changes
nothing. Each request to the store is one unit, so the demand names one unit and the
consumption counts every request (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "secrets.metadata"
ACTIONS_CREDENTIAL = "SECRETS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "secrets.metadata.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The secrets under the configured mount and path whose name starts with "
        "`prefix` (optional), at most `limit` (default 100, at most 500), the oldest change "
        "first. Each names its path, when it was created, when its current value was set, its "
        "age in whole days, its rotation, expiry and last access as far as the store states "
        "them. Never a value. `complete` says whether every secret was read.",
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
