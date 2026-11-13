"""What the books connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and one write of `accounting.invoices`. The write exports a batch of outgoing invoices
as draft sales invoices, `marked`: each draft carries a mark derived from the idempotency key
and the invoice's number, which a repeat finds before it creates anything (ADR-0314).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "accounting.invoices"
ACTIONS_CREDENTIAL = "BOOKS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "accounting.invoices.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one sales invoice of the books by its name: its customer, dates, "
        "currency, net and gross total, whether it is a draft, submitted or cancelled, and the "
        "mark it carries.",
    },
    {
        "name": "accounting.invoices.export",
        "demand": {"quota_units": 60},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Export up to 500 outgoing invoices, in the shape `payments.invoices.list` "
        "gives them (amounts in minor units), as draft sales invoices of the books: one line of "
        "the net amount to the configured income account, the tax as an actual charge to the "
        "configured tax account, the configured collective customer. A draft is never "
        "submitted: a person posts it. Each draft carries a mark of the key and the invoice's "
        "number; a repeat finds it and creates nothing again.",
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
