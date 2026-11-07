"""What the social mentions connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `mentions.search`, of effect `read`: a search changes nothing.
Each page of an answer is one request, so the demand names one unit and the consumption counts
every page (ADR-0005). The forum connector serves the same operation in the same shape
(ADR-0207).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "mentions.search"
ACTIONS_CREDENTIAL = "MENTIONS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "mentions.search.query",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The public posts that match `query`, up to `limit` (default 40, at most "
        "400), those since `since` (a date, YYYY-MM-DD) where it is given: each its id, url, "
        "its text without markup, its moment, and `source` social. Never its author. "
        "`complete` says whether every match fit within `limit`.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 300},
        "permissions": "passthrough",
    }
