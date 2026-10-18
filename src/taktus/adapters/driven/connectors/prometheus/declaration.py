"""What the metrics connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `metrics.series`, both of effect `read`: a query reads and
changes nothing. Each makes one request, which is its demand (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "metrics.series"
ACTIONS_CREDENTIAL = "METRICS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "metrics.series.query",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Evaluate a query at one moment (`time`, now when absent). Returns every "
        "series of the answer with its labels and its value, as a number and as the text the "
        "store gave. `complete` says whether every series fit within `limit`.",
    },
    {
        "name": "metrics.series.range",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Evaluate a query over a range (`start`, `end`, `step` in seconds). Returns "
        "every series of the answer with its labels and its values, oldest first. `complete` "
        "says whether every series fit within `limit`.",
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
