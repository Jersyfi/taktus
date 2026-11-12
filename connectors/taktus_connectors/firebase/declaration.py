"""What the site connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes of `deployment.sites`: a site's live version read, a finalized version
released to it, and an earlier one put back. Both writes leave the system, `marked`: the
release's message carries a mark of the idempotency key, where a repeat finds it.
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
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read a site: the version it serves live, and with `version` that version's "
        "state and `rolled_out`: the version is finalized and live.",
    },
    {
        "name": "deployment.sites.release",
        "demand": {"quota_units": 25},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Release a finalized version of a site to its live channel. The release's "
        "message carries a mark of the idempotency key; a repeat finds it among the site's "
        "releases. A version that is not finalized is a conflict.",
    },
    {
        "name": "deployment.sites.rollback",
        "demand": {"quota_units": 25},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Put an earlier version of a site back live, the one `version` names, by a "
        "release of it. The release's message carries a mark of the idempotency key, found "
        "again as for a release.",
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
