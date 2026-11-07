"""What the signing credentials connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

One operation of the capability `expiry.credentials`, of effect `read`: listing changes
nothing. Each page is one request, so the demand names one unit and the consumption counts
every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "expiry.credentials"
ACTIONS_CREDENTIAL = "STORE_API_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "expiry.credentials.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The team's signing certificates and provisioning profiles, or the `kinds` "
        "named (`certificate`, `profile`), at most `limit` (default 200, at most 1000), the "
        "nearest expiry first. Each names its kind, identifier, name, type, platform, state, "
        "expiry, whole days left (negative once expired) and a key. Never the content. "
        "`complete` says whether every one was read.",
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
