"""What the business-intelligence connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

One operation of the capability `bi.figures`, of effect `read`: a query reads a semantic model
and changes nothing. No operation writes: the connection is read-only (UC-5.7). A call is two
requests, the access token it exchanges first and the query, so the demand names two units and
the consumption counts both (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "bi.figures"
ACTIONS_CREDENTIAL = "BI_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "bi.figures.query",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The rows one DAX `query` (it begins with EVALUATE or DEFINE) answers over "
        "the semantic model `dataset`, of the workspace `group` when one is named, at most "
        "`limit` rows (default 1000, at most 10000). Each row maps a column, as the query "
        "names it (`Table[Column]`, `[Measure]`), to its value as the tool gave it, a blank "
        "as null. `complete` says whether every row the query answered was returned.",
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
