"""What the cloud billing connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `billing.costs`, of effect `read`: reading costs changes
nothing. Each page of the answer is one request, and the provider bills each request, so the
demand names one unit and the consumption counts every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "billing.costs"
ACTIONS_CREDENTIAL = "BILLING_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "billing.costs.daily",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The cost of each of the `days` days (default 29, at most 92) before `end` "
        "(a date, default today in UTC), by `group_by` — `service` (default), `account` or "
        "`region` — under `metric` — `unblended` (default), `amortized` or `net_unblended`. "
        "Every amount is the decimal text the provider gave; each day's `total` is their exact "
        "sum. `estimated` marks a day the provider has not closed; `complete` says whether "
        "every page of the answer was read.",
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
