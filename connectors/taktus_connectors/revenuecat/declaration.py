"""What the in-app subscription connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

The same three operations, under the same names and in the same shape, as the first payment
provider connector (ADR-0150, ADR-0206). All are of effect `read`, every request one unit.
The provider has no list of every subscription of a project, so `payments.subscriptions.list`
reads the customers page by page and each customer's subscriptions: its consumption grows with
the number of customers, and its demand names the least it costs.

`payments.customers` is declared `scoped` (ADR-0130): the provider answers one customer's
subscriptions, and a call that names another customer than the case's subject is refused as
`out_of_scope` before the provider is asked.
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
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every subscription of the project in `status` (default `active`; also "
        "`trialing`, `past_due`, `paused`, `canceled`, `incomplete`, or `all`), up to `limit` "
        "(default 1000, at most 10000), read customer by customer: the provider lists no "
        "project's subscriptions. Each in the shared shape: its customer by the app's user "
        "identifier only, its status mapped, the end of its current period, whether it ends "
        "then, its product as one item. `complete` says whether every customer was read and "
        "every subscription fit within `limit`.",
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
        "summary": "Every subscription of the customer `customer` (the app's user identifier), "
        "in every status, in the shape of a listed one. Scoped: a call that serves a case "
        "answers only the case's subject, and refuses another customer as out_of_scope.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, CUSTOMERS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
        "scoped": [CUSTOMERS],
    }
