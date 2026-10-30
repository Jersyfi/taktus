"""What the payment provider connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `payments.subscriptions`, both of effect `read`: reading
subscriptions changes nothing. Each page of an answer is one request, so the demand names one
unit and the consumption counts every page (ADR-0005).

One operation of the capability `payments.customers`, declared `scoped`: the subscriptions of
one customer, for a step that serves that customer's case. A call that carries a case's scope
and names another customer is refused as `out_of_scope` (ADR-0130). `payments.subscriptions`
is not scoped: a reconciliation reads every subscription, and its step is analytic or anchored.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "payments.subscriptions"
CUSTOMERS = "payments.customers"
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
    {
        "name": "payments.customers.subscriptions",
        "demand": {"quota_units": 1},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "Every subscription of the customer `customer` (its identifier, cus_…), in "
        "every status, in the shape of a listed one. Scoped: a call that serves a case answers "
        "only the case's subject, and refuses another customer as out_of_scope.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, CUSTOMERS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
        "scoped": [CUSTOMERS],
    }
