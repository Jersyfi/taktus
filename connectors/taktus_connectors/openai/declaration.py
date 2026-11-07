"""What the model costs connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations, both of effect `read`: reading costs or the catalogue changes nothing.
`models.costs.daily` is the capability `models.costs`, `models.catalogue.list` the capability
`models.catalogue`. Each page of the answer is one request, so the demand names one unit and the
consumption counts every page (ADR-0005).
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
        "`group_by` — `line_item` (default) or `project`. Every amount is the decimal text the "
        "provider gave; each day's `total` is their exact sum. `complete` says whether every "
        "page of the answer was read.",
    },
    {
        "name": "models.catalogue.list",
        "demand": {"quota_units": 1},
        "capability": CATALOGUE,
        "effect": "read",
        "summary": "The models the referenced key may use, at most `limit` (default and most "
        "1000), sorted by identifier: each `{id, name, created_at, lifecycle, deprecated_at, "
        "retires_at}`. `name`, `lifecycle` and `deprecated_at` are always null: the provider "
        "states none. `created_at` is the creation moment; `retires_at` the announced shutdown "
        "date at midnight UTC, or null. `ids` is the identifiers alone; `retiring` those with "
        "a retirement set; `current` the others; `complete` says whether every model was read.",
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
