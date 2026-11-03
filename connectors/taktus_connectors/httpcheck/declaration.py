"""What the check connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation, `check.http.run`, of effect `read`: a check observes a service and changes
nothing there. Its demand is one request, which is what a run reserves before calling it
(ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "check.http"
ACTIONS_CREDENTIAL = "CHECK_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "check.http.run",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Send one request to a path of the configured service and judge the answer "
        "against the declared expectation: the status, a text the body contains, the longest "
        "duration. Reports the outcome, passed or failed, with every expectation that failed, "
        "the status and the duration in milliseconds. A service that does not answer is a "
        "failed check, not an error.",
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
