"""What the model catalogue connector over the models list declares about itself: the document
served as the resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

One operation, of effect `read`: reading the catalogue changes nothing. `models.catalogue.list`
is the capability `models.catalogue`. The list answers in one request.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CATALOGUE = "models.catalogue"
ACTIONS_CREDENTIAL = "MODELS_TOKEN"
"""The ordinary API key the catalogue is read with."""

OPERATIONS: list[Json] = [
    {
        "name": "models.catalogue.list",
        "demand": {"quota_units": 1},
        "capability": CATALOGUE,
        "effect": "read",
        "summary": "The models the referenced key may use, at most `limit` (default and most "
        "1000), sorted by identifier: each `{id, name, created_at, lifecycle, deprecated_at, "
        "retires_at}`, `name` the provider's name of the model or null, `created_at` the "
        "creation moment or null, `lifecycle` always null, `deprecated_at` the deprecation the "
        "provider set, RFC 3339 or null, `retires_at` always null. `ids` is the identifiers "
        "alone; `retiring` those with a deprecation set; `current` the others; `complete` says "
        "whether every model was read.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CATALOGUE],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
