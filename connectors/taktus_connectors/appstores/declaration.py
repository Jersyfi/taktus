"""What the app stores connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Every store capability, each call answered by the store its `platform` names (ADR-0210):
`stores.beta` and `stores.releases`, three reads and four writes; `stores.reviews` (ADR-0207),
two reads and a reply; and `expiry.credentials` (ADR-0203), one read of App Store Connect
alone, which takes no platform. Every write leaves the system, `marked`. A Play release carries
the key's mark as its name. Where no field can carry it — App Store Connect, and a staged
rollout's fraction or halt — the state a write leaves is its own mark, as a label is
(ADR-0097): a build in a group, a phased release's state, a version waiting for review. A reply
to a review is marked by its own text, which a repeat finds in the response the review carries.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
BETA = "stores.beta"
RELEASES = "stores.releases"
REVIEWS = "stores.reviews"
CREDENTIALS = "expiry.credentials"
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
    {
        "name": "stores.reviews.list",
        "demand": {"quota_units": 2},
        "capability": REVIEWS,
        "effect": "read",
        "summary": "The reviews of the app `app` on the platform the call names (ios: its "
        "identifier at the store; android: its package name), newest first, up to `limit` "
        "(default 200, at most 2000), of the `ratings` given (1 to 5) or of every rating. Each "
        "names its identifier, rating, title, text, territory or language, when it was written "
        "or last changed, the app version where the store gives one, and the response in place; "
        "never the reviewer, the author or the device. On android only the reviews with a text "
        "written or changed in the last week, all the store serves. `complete` says whether "
        "every review fit within `limit`.",
    },
    {
        "name": "stores.reviews.read",
        "demand": {"quota_units": 2},
        "capability": REVIEWS,
        "effect": "read",
        "summary": "One review of the app `app` on the platform the call names, by its "
        "identifier `review`, in the shape of a listed one.",
    },
    {
        "name": "stores.reviews.reply",
        "demand": {"quota_units": 3},
        "capability": REVIEWS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Publish `text` as the public response to the review `review` of the app "
        "`app` on the platform the call names; on android at most 350 characters. The text is "
        "its own mark: a review whose response is the text already is replayed and written "
        "nothing. A response of another text is a conflict unless `replace` is true. Weaker "
        "than a key, and stated so: a repeat after somebody else wrote the same text reports "
        "replayed too.",
    },
    {
        "name": "expiry.credentials.list",
        "demand": {"quota_units": 1},
        "capability": CREDENTIALS,
        "effect": "read",
        "summary": "The team's signing certificates and provisioning profiles at App Store "
        "Connect, or the `kinds` named (`certificate`, `profile`), at most `limit` (default "
        "200, at most 1000), the nearest expiry first. Each names its kind, identifier, name, "
        "type, platform, state, expiry, whole days left (negative once expired) and a key. "
        "Never the content. `complete` says whether every one was read. It takes no platform: "
        "Google Play publishes no signing credential with an expiry.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CREDENTIALS, BETA, RELEASES, REVIEWS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
