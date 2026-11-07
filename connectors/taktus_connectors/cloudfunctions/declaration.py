"""What the functions connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes of `deployment.sites`, the operations the site connectors serve under
the same names and with the same inputs, so that a release process runs on any of them. A
release and a rollback leave the system, `marked`: the function carries a label with a digest
of the idempotency key, where a repeat finds it.
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
        "summary": "Read a function: the source archive it serves live, and with `version` "
        "whether that archive is live and the function active, `rolled_out`.",
    },
    {
        "name": "deployment.sites.release",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Deploy a source archive the business's build uploaded to a function. The "
        "function carries a label with a digest of the idempotency key; a repeat finds it. A "
        "function still deploying is a conflict.",
    },
    {
        "name": "deployment.sites.rollback",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Deploy an earlier source archive to a function again, the one `version` "
        "names. The label carries a digest of the idempotency key, found again as for a "
        "release.",
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
