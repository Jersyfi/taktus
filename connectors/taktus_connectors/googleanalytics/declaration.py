"""What the analytics connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `analytics.reports`, of effect `read`: a report changes
nothing. The token exchange and the report are two requests, so the demand names two units.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "analytics.reports"
ACTIONS_CREDENTIAL = "ANALYTICS_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "analytics.reports.run",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "A report of the configured property: the `metrics` (1 to 10) by the "
        "`dimensions` (0 to 9) between `start` and `end` (YYYY-MM-DD, `today`, `yesterday` or "
        "`NdaysAgo`), at most `limit` rows (default 1000, at most 10000), optionally ordered by "
        "`order`. Each row names its dimension values and its metric values as the decimal text "
        "the API gave. A dimension that can name a person is refused. `complete`, `sampled` and "
        "`thresholded` say whether the rows are all of it and exact.",
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
