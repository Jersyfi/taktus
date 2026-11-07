"""What the warehouse connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `warehouse.queries`. `run` is a `read`: the connector runs only
a statement the warehouse itself calls a SELECT. The token exchange, the dry run and the query
are three requests, so the demand names three units; a page more is one more. `change` is a
`write`, `marked` by the job's identifier, which the call's idempotency key gives (ADR-0262):
the token, the dry run, the job and one reading of it are four. The run calls it only on a
connection a person granted writing.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "warehouse.queries"
ACTIONS_CREDENTIAL = "WAREHOUSE_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "warehouse.queries.run",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Run one `query` in standard SQL over the configured dataset, with named "
        "`parameters` (text and numbers), at most `limit` rows (default 1000, at most 10000). "
        "Only a statement that starts with SELECT or WITH, and that a dry run of the warehouse "
        "calls a SELECT, is run. The answer is the `schema`, the `rows` with every value as "
        "text or null, `total_rows`, `complete` and `bytes_processed`.",
    },
    {
        "name": "warehouse.queries.change",
        "demand": {"quota_units": 4},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Run one `query` that changes data over the configured dataset — a statement "
        "that begins with INSERT, UPDATE, DELETE or MERGE and that a dry run of the warehouse "
        "calls one of them — with named `parameters`, as a job whose identifier the "
        "idempotency key gives; a repeat finds the job and reports replayed. The answer is the "
        "`statement_type`, the `affected_rows` and the `job`.",
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
