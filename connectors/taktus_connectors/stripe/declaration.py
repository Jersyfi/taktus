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
FAILURES = "payments.failures"
INVOICES = "payments.invoices"
EVENTS = "payments.events"
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
    {
        "name": "payments.customers.failures",
        "demand": {"quota_units": 1},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "The failed payments of the customer `customer`, in the shape of "
        "`payments.failures.list`, with `as_of`. Scoped like the customer's subscriptions.",
    },
    {
        "name": "payments.customers.contact",
        "demand": {"quota_units": 1},
        "capability": CUSTOMERS,
        "effect": "read",
        "summary": "The e-mail address of the customer `customer`, as `{customer, email}`, "
        "email null where none is held. Answered only to a call that serves that customer's "
        "case; without a scope, or for another customer, out_of_scope.",
    },
    {
        "name": "payments.failures.list",
        "demand": {"quota_units": 1},
        "capability": FAILURES,
        "effect": "read",
        "summary": "Every payment that failed and is still owed: the open invoices whose "
        "payment was attempted, up to `limit` invoices read (default 1000). Each names its "
        "customer and subscription by identifier, the amount owed in minor units, currency, "
        "attempts, failed_at and next_attempt_at in seconds since the epoch, the whole "
        "days_failing since, the decline code as reason, and update_url, the provider's page "
        "where the customer pays with another method. `as_of` is the moment of the reading.",
    },
    {
        "name": "payments.invoices.list",
        "demand": {"quota_units": 1},
        "capability": INVOICES,
        "effect": "read",
        "summary": "The invoices created in `month` (YYYY-MM, default the month before), in "
        "`status` (draft, open, paid, uncollectible, void, or all, the default), up to `limit` "
        "(default 1000, at most 10000). Each names its number, customer and subscription by "
        "identifier, status, currency, total, tax, paid and remaining in minor units, and "
        "issued_at, due_at and paid_at in seconds since the epoch.",
    },
    {
        "name": "payments.events.undelivered",
        "demand": {"quota_units": 1},
        "capability": EVENTS,
        "effect": "read",
        "summary": "The events of the last 30 days not delivered to every webhook endpoint, "
        "still pending or failed, up to `limit` (default 1000). Each names its id, type, "
        "created, the whole hours_pending since, pending_webhooks, and the kind and "
        "identifier of the object it is about. `as_of` is the moment of the reading.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, CUSTOMERS, EVENTS, FAILURES, INVOICES],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
        "scoped": [CUSTOMERS],
    }
