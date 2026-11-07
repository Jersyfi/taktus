"""What the site connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes. Reading a site changes nothing. A release and a rollback publish a
deploy the service already built. The request takes no body, so the idempotency key has no
place in the host: both are declared `none`, and the engine never repeats them (ADR-0024 §3,
ADR-0211). Before writing, the connector reads which deploy the site publishes; one already
published is not published again and reports replayed.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "deployment.sites"
ACTIONS_CREDENTIAL = "SITES_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "deployment.sites.read",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one site: the version it publishes now, and, where `version` names "
        "one, that version's state, whether it is ready, and `rolled_out`: it is ready and "
        "the site publishes it.",
    },
    {
        "name": "deployment.sites.release",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "none",
        "summary": "Publish a version of a site that the service already built. The version "
        "the site publishes is read first: one already published changes nothing and reports "
        "replayed. The key has no place in the host, so the engine never repeats it. A "
        "version not ready is a conflict.",
    },
    {
        "name": "deployment.sites.rollback",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "none",
        "summary": "Put an earlier version of a site back, the one `version` names. Read "
        "first as a release is: one already published changes nothing and reports replayed.",
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
