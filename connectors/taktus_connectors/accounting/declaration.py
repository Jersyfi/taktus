"""What the accounting connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes. Reading an order changes nothing. Proposing a booking and submitting a
released payment each leave the system, `marked`: the record carries a mark derived from the
idempotency key, and a repeat finds it before acting (contract §4). A read is one request; a
write two, the lookup and the creation.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
ORDERS = "accounting.orders"
BOOKINGS = "accounting.bookings"
PAYMENTS = "payment.release"
ACTIONS_CREDENTIAL = "ACCOUNTING_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "accounting.orders.read",
        "demand": {"quota_units": 1},
        "capability": ORDERS,
        "effect": "read",
        "summary": "What was ordered or contracted under `reference` — a purchase order, or a "
        "standing contract such as a subscription: its supplier by tax identifier and the "
        "account the system pays it to, its currency, its lines with price, quantity received "
        "and quantity invoiced, its net total and what was invoiced against it, and the "
        "account and cost centre it is booked to. Every amount as decimal text.",
    },
    {
        "name": "accounting.bookings.propose",
        "demand": {"quota_units": 2},
        "capability": BOOKINGS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Propose a booking of one document to the accounting system: the document, "
        "its digest, the supplier, the currency, the dates, the account and cost centre, the "
        "net, tax and gross amounts as decimal text and the tax breakdown. A person of the "
        "organisation posts it there; the system's own record is what is booked. The record "
        "carries a mark derived from the key; a repeat finds it and proposes nothing again.",
    },
    {
        "name": "payment.release.submit",
        "demand": {"quota_units": 2},
        "capability": PAYMENTS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Hand a payment a person released to the accounting system's payment run: "
        "the document, the supplier, the currency, the amount as decimal text, the date it is "
        "due and the booking it settles. The system pays the account it holds for the "
        "supplier, never one the call names. The record carries a mark derived from the key; "
        "a repeat finds it and submits nothing again.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [ORDERS, BOOKINGS, PAYMENTS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
