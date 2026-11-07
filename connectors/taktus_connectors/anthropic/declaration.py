"""What the model costs connector over the cost report declares about itself: the document
served as the resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

Two operations, both of effect `read`: reading costs or the catalogue changes nothing.
`models.costs.daily` is the capability `models.costs`, `models.catalogue.list` the capability
`models.catalogue`.
Each page of the answer is one request, so the demand names one unit and the consumption counts
every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "models.costs"
CATALOGUE = "models.catalogue"
ACTIONS_CREDENTIAL = "MODEL_COSTS_TOKEN"
CATALOGUE_CREDENTIAL = "MODELS_TOKEN"
"""The ordinary API key the catalogue is read with; the costs need an administration key."""

OPERATIONS: list[Json] = [
    {
        "name": "models.costs.daily",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "What the organisation spent at the model provider on each of the `days` "
        "days (default 29, at most 92) before `end` (a date, default today in UTC), by "
        "`group_by` — `line_item` (default: the model and the kind of usage) or `workspace`. "
        "Every amount is decimal text in the currency's main unit; each day's `total` is their "
        "exact sum. `complete` says whether every page of the answer was read.",
    },
    {
        "name": "models.catalogue.list",
        "demand": {"quota_units": 1},
        "capability": CATALOGUE,
        "effect": "read",
        "summary": "The models the referenced key may use, retired ones among them, at most "
        "`limit` (default and most 1000), sorted by identifier: each `{id, name, created_at, "
        "lifecycle, deprecated_at, retires_at}`, `name` the display name, `created_at` the "
        "release moment or null, `lifecycle` `active`, `deprecated` or `retired`, the two "
        "others RFC 3339 or null. `ids` is the identifiers alone; `retiring` those deprecated, "
        "retired or with a retirement set; `current` the others; `complete` says whether "
        "every model was read.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, CATALOGUE],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [
            {"name": ACTIONS_CREDENTIAL, "purpose": "actions"},
            {"name": CATALOGUE_CREDENTIAL, "purpose": "actions"},
        ],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
