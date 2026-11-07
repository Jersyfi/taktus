"""What the app stores connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two capabilities, three reads and four writes. Every write leaves the system, `marked`. A Play
release carries the key's mark as its name. Where no field can carry it — App Store Connect,
and a staged rollout's fraction or halt — the state a write leaves is its own mark, as a label
is (ADR-0097): a build in a group, a phased release's state, a version waiting for review.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
BETA = "stores.beta"
RELEASES = "stores.releases"
ACTIONS_CREDENTIAL = "STORES_KEY"

_STATE_MARK = (
    " The state is its own mark: a repeat that finds it changes nothing and reports replayed. "
    "Weaker than a key, and stated so: a repeat after somebody else made the same state "
    "reports replayed too."
)

OPERATIONS: list[Json] = [
    {
        "name": "stores.beta.builds",
        "demand": {"quota_units": 3},
        "capability": BETA,
        "effect": "read",
        "summary": "List an app's builds, newest first, on the platform the call names (ios or "
        "android): each with its identifier, marketing version where the store gives one, build "
        "number or version code, the store's own word for its state, and when it was uploaded.",
    },
    {
        "name": "stores.beta.distribute",
        "demand": {"quota_units": 5},
        "capability": BETA,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Give one build to testers: add it to a beta group (ios), or release it on a "
        "test track (android) as a release whose name is the idempotency key's mark, found again "
        "on the track by a repeat. On ios the build in the group is its own mark: a repeat that "
        "finds it there changes nothing and reports replayed, also after somebody else added it.",
    },
    {
        "name": "stores.beta.feedback",
        "demand": {"quota_units": 2},
        "capability": BETA,
        "effect": "read",
        "summary": "List the feedback testers sent on an app's beta builds, newest first: its "
        "kind (screenshot or crash), when, the comment and the build. Never the tester or the "
        "device's settings. Only the iOS store publishes it; android is invalid.",
    },
    {
        "name": "stores.releases.read",
        "demand": {"quota_units": 3},
        "capability": RELEASES,
        "effect": "read",
        "summary": "Read an app's newest release: its version, the store's own word for its "
        "state, the review as preparing, waiting, in_review, rejected, approved, live or other, "
        "its staged rollout (the iOS phased release's state and day, or the android fraction), "
        "and whether it is rolled out to everyone.",
    },
    {
        "name": "stores.releases.raise",
        "demand": {"quota_units": 5},
        "capability": RELEASES,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Raise a staged rollout: the android fraction of users set, or the release "
        "completed at 1; the iOS phased release resumed, or completed at 1 (its fraction is the "
        "store's own schedule)." + _STATE_MARK,
    },
    {
        "name": "stores.releases.halt",
        "demand": {"quota_units": 5},
        "capability": RELEASES,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Halt a staged rollout: the android release halted, the iOS phased release "
        "paused. No staged rollout in progress is a conflict." + _STATE_MARK,
    },
    {
        "name": "stores.releases.submit",
        "demand": {"quota_units": 6},
        "capability": RELEASES,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Submit a version: the iOS version sent for review, the android version "
        "code released on the production track, at a fraction where one is given, as a release "
        "whose name is the idempotency key's mark; a version code already on production under "
        "another name is a conflict. On ios a version already waiting for review or further is "
        "its own mark: a repeat that finds it changes nothing and reports replayed, also after "
        "somebody else submitted it.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [BETA, RELEASES],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
