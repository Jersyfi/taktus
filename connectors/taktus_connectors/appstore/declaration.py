"""What the store reviews connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two reads and one write of the capability `stores.reviews` (ADR-0207). Reading reviews changes
nothing. A reply leaves the system and is public: `marked` by its own text, which a repeat
finds in the response the review carries.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "stores.reviews"
ACTIONS_CREDENTIAL = "STORE_REVIEWS_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "stores.reviews.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The reviews of the app `app` (its identifier at the store), newest first, "
        "up to `limit` (default 200, at most 2000), of the `ratings` given (1 to 5) or of "
        "every rating. Each names its identifier, rating, title, text, territory or language, "
        "when it was written, the app version where the store gives one, and the response in "
        "place; never the reviewer. `complete` says whether every review fit within `limit`.",
    },
    {
        "name": "stores.reviews.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One review of the app `app` by its identifier `review`, in the shape of a "
        "listed one.",
    },
    {
        "name": "stores.reviews.reply",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Publish `text` as the public response to the review `review` of the app "
        "`app`. The text is its own mark: a review whose response is the text already is "
        "replayed and written nothing. A response of another text is a conflict unless "
        "`replace` is true. Weaker than a key, and stated so: a repeat after somebody else "
        "wrote the same text reports replayed too.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 3600},
        "permissions": "passthrough",
    }
