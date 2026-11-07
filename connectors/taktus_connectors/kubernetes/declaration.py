"""What the workload connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and three writes (ADR-0195). Reading a deployment changes nothing. A release and a
rollback leave the system, `marked`: the pod template carries the idempotency key as an
annotation, and the revisions the cluster keeps are where a repeat finds it. Scaling is
`marked` by the number itself, as a label is its own mark (ADR-0097).
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
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one deployment of the namespace: its containers with their images, "
        "the replicas wanted, updated, ready and available, its revision, the key its pod "
        "template carries, `changed_at`: when its rollout last progressed, and "
        "`rolled_out`: the controller has seen the newest change and "
        "every wanted replica is updated and available.",
    },
    {
        "name": "deployment.workloads.release",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Set the image of one container of a deployment. The pod template carries "
        "the idempotency key as an annotation; a repeat finds it in the deployment or in one of "
        "the revisions the cluster keeps. A deployment changed between the reading and the "
        "write is a conflict.",
    },
    {
        "name": "deployment.workloads.rollback",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Put back the pod template of an earlier revision of a deployment: the one "
        "`revision` names, or the newest before the current. The restored template carries "
        "the idempotency key, found again as for a release. No earlier revision is not_found.",
    },
    {
        "name": "deployment.workloads.scale",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Set the replicas a deployment wants. The number is its own mark: a repeat "
        "that finds it set changes nothing and reports replayed. Weaker than a key, and stated "
        "so: a repeat after somebody else set the same number reports replayed too.",
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
