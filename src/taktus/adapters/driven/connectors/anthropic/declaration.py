"""What the model costs connector over the cost report declares about itself: the document
served as the resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

One operation of the capability `models.costs`, of effect `read`: reading costs changes nothing.
Each page of the answer is one request, so the demand names one unit and the consumption counts
every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "models.costs"
ACTIONS_CREDENTIAL = "MODEL_COSTS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "models.costs.daily",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "What the organisation spent at the model provider on each of the `days` "
        "days (default 29, at most 92) before `end` (a date, default today in UTC), by "
        "`group_by` — `line_item` (default: the model and the kind of usage) or `workspace`. "
        "Every amount is decimal text in the currency's main unit; each day's `total` is their "
        "exact sum. `complete` says whether every page of the answer was read.",
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
