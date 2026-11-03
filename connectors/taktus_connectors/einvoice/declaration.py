"""What the documents connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `documents.invoices`, both of effect `read`: listing the inbox
and reading one document change nothing there. A list is one request, a read one request.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "documents.invoices"
ACTIONS_CREDENTIAL = "DOCUMENTS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "documents.invoices.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The documents in the inbox folder, up to `limit` (default 100, at most "
        "1000), oldest first: each by its `document` name, its size in bytes, when it was last "
        "changed and its entity tag. `complete` says whether every document fit within `limit`.",
    },
    {
        "name": "documents.invoices.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One document of the inbox by its `document` name, read as an electronic "
        "invoice of EN 16931 in UBL 2.1 or CII D16B: its syntax, type, number, dates, currency, "
        "references, seller, the account to be paid, its lines, its tax breakdown and its "
        "totals, every amount as the decimal text the document gave, and the SHA-256 digest of "
        "its bytes. A document that is not such an invoice, or declares a document type or an "
        "entity, is refused as invalid.",
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
