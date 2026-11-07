"""What the serverless connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes of `deployment.workloads`, the operations the cluster connector serves
under the same names, so that a release process runs on either. Scaling is not served: the
service scales its instances itself. A release and a rollback leave the system, `marked`: the
release's key is an annotation of the template every revision keeps, the rollback's an
annotation of the service.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "deployment.workloads"
ACTIONS_CREDENTIAL = "WORKLOADS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "deployment.workloads.read",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one service of the location: its containers with their images, the "
        "latest ready revision, the key its template carries, and `rolled_out`: the service is "
        "not reconciling, its newest revision is ready, and it takes all the traffic.",
    },
    {
        "name": "deployment.workloads.release",
        "demand": {"quota_units": 5},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Set the image of one container of a service, which makes a new revision, "
        "and send all traffic to the latest revision. The template carries the idempotency key "
        "as an annotation; a repeat finds it in the service or in a revision it keeps. A "
        "service changed between the reading and the write is a conflict.",
    },
    {
        "name": "deployment.workloads.rollback",
        "demand": {"quota_units": 5},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Send all traffic to an earlier ready revision of a service: the one "
        "`revision` names, or the newest before the one serving. The service carries the "
        "idempotency key as an annotation, where a repeat finds it. No earlier revision is "
        "not_found.",
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
