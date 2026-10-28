"""What the payment provider connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `payments.subscriptions`, both of effect `read`: reading
subscriptions changes nothing. Each page of an answer is one request, so the demand names one
unit and the consumption counts every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "payments.subscriptions"
ACTIONS_CREDENTIAL = "PAYMENTS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "payments.subscriptions.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every subscription in `status` (default `active`; `all` for every status), "
        "up to `limit` (default 1000, at most 10000). Each names its customer by identifier "
        "only, its status, the end of its current period, whether it ends then, its items with "
        "price, product, quantity, amount in minor units, currency and interval, and its "
        "metadata. `complete` says whether every subscription fit within `limit`.",
    },
    {
        "name": "payments.subscriptions.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One subscription by its `id`, in the same shape as a listed one.",
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
