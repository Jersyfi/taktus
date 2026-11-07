"""What the second payment provider connector declares about itself: the document served as
the resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

The same three operations, under the same names and in the same shape, as the first payment
provider connector (ADR-0150, ADR-0206), so that B-6.01, B-3.04 and B-5.06 read either
provider unchanged. All are of effect `read`. Every request is one unit: the access token, each
page of the list and each plan read.

`payments.customers` is declared `scoped` (ADR-0130). The provider's list cannot be narrowed to
one customer, so the connector reads the list and answers the subject's subscriptions only; a
call that names another customer is refused as `out_of_scope` before the provider is asked.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "payments.subscriptions"
CUSTOMERS = "payments.customers"
FAILURES = "payments.failures"
INVOICES = "payments.invoices"
ACTIONS_CREDENTIAL = "PAYMENTS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "payments.subscriptions.list",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every subscription in `status` (default `active`; also `paused`, "
        "`canceled`, `incomplete`, or `all`), up to `limit` (default 1000, at most 10000). "
        "Each names its customer by the payer's identifier only, its status in the shared "
        "vocabulary, the next billing time as the end of its period, its plan as one item with "
        "product, quantity, amount in minor units, currency and interval, and its own "
        "identifier as metadata. `complete` says whether every subscription fit within `limit`.",
    },
    {
        "name": "payments.subscriptions.read",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One subscription by its `id` (I-…), in the same shape as a listed one.",
    },
    {
        "name": "payments.customers.subscriptions",
        "demand": {"quota_units": 2},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "Every subscription of the customer `customer` (the payer's identifier), in "
        "every status, in the shape of a listed one. Scoped: a call that serves a case answers "
        "only the case's subject, and refuses another customer as out_of_scope.",
    },
    {
        "name": "payments.customers.failures",
        "demand": {"quota_units": 2},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "The failed payments of the payer `customer`, in the shape of "
        "`payments.failures.list`, with `as_of`. Scoped like the payer's subscriptions.",
    },
    {
        "name": "payments.customers.contact",
        "demand": {"quota_units": 2},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "The e-mail address of the payer `customer`, from a subscription of theirs, "
        "as `{customer, email}`. Answered only to a call that serves that payer's case; "
        "without a scope, or for another payer, out_of_scope.",
    },
    {
        "name": "payments.failures.list",
        "demand": {"quota_units": 2},
        "capability": FAILURES,
        "effect": "read",
        "summary": "Every active or suspended subscription whose consecutive payments failed, "
        "in the first connector's shape: the payer as customer, the outstanding balance as "
        "amount in minor units, the count of failures as attempts, the last failure's moment, "
        "next retry and reason code; update_url null. `as_of` is the moment of the reading.",
    },
    {
        "name": "payments.invoices.list",
        "demand": {"quota_units": 2},
        "capability": INVOICES,
        "effect": "read",
        "summary": "The invoices dated in `month` (YYYY-MM, default the month before), in "
        "`status` (draft, open, paid, void, refunded, or all, the default), up to `limit` "
        "read (default 1000), in the first connector's shape; customer and subscription null, "
        "as the provider names a recipient by e-mail only.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, CUSTOMERS, FAILURES, INVOICES],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
        "scoped": [CUSTOMERS],
    }
