"""What the error tracking connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of the capability `errors.issues`, both of effect `read`: reading issues changes
nothing. Each page of an answer is one request, so the demand names one unit and the
consumption counts every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "errors.issues"
ACTIONS_CREDENTIAL = "ERRORS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "errors.issues.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The issues that match `query` (default `is:unresolved`) and had events "
        "within `period` (default `24h`), in the order `sort` names — `freq` (default), `new`, "
        "`date` or `user` — optionally of one `project`, at most `limit` (default 100, at most "
        "1000). Each issue names its identifier, title, culprit, level, status, project, "
        "event count, affected users, first and last sighting and its link; never a person. "
        "`complete` says whether every matching issue was read.",
    },
    {
        "name": "errors.issues.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One issue by its numeric `id`, in the shape `errors.issues.list` gives.",
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
