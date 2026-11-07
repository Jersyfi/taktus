"""What the product analytics connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

One operation of the capability `analytics.reports`, of effect `read`, under the name, the
inputs and the output of the analytics connector (`googleanalytics/`); its names are the API's.
One request per metric asked, so the demand names up to three units. The API admits sixty
queries an hour, so the window is an hour.
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
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "A report of the configured project's `events` (1 to 100 of its event "
        "names): the `metrics` (`general`, the events counted; `unique`, the users who did "
        "them; `average`, events per user) by the `dimensions` (at most one of `day`, `week`, "
        "`month`, and `event`) between `start` and `end` (YYYY-MM-DD, `today`, `yesterday` or "
        "`NdaysAgo`), at most `limit` rows (default 1000, at most 10000), optionally ordered by "
        "`order`. Each row names its dimension values as the API keyed them and its metric "
        "values as decimal text. No figure names a person.",
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
