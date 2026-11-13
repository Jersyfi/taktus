"""What the serverless connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and three writes of `deployment.workloads`. The read, the release and the rollback are
the operations the cluster connector serves under the same names, so that a release process runs
on either. The split is the platform's own: a share of the traffic on a canary revision beside
the stable one (ADR-0312). Scaling is not served: the service scales its instances itself. Every
write leaves the system, `marked`: the release's key is an annotation of the template every
revision keeps, the rollback's and the split's an annotation of the service.
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
    {
        "name": "deployment.workloads.split",
        "demand": {"quota_units": 5},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Send a share of a service's traffic, `percent` from 0 to 100, to a canary "
        "revision, the one `revision` names or the latest ready one, and the rest to the stable "
        "revision: the other one that takes the most traffic. 100 promotes the canary, 0 puts "
        "all traffic back on the stable one. No template is changed and no revision made. The "
        "service carries the idempotency key as an annotation, where a repeat finds it. A canary "
        "that is not ready, or no stable revision beside it, is not_found.",
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
