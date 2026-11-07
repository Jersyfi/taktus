"""What the website connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes, the operations of `website.posts` under the names the WordPress
connector serves them. A draft is `marked`: the document's identifier is a digest of the
idempotency key, and a repeat finds the document by it. Publishing is `marked` by the
document's own state: a post with no draft left and a published version is not published again.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "website.posts"
ACTIONS_CREDENTIAL = "WEBSITE_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "website.posts.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one post of the dataset: whether it is a draft or published, its "
        "title, the link that opens it in the Studio and when it was last changed.",
    },
    {
        "name": "website.posts.draft",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a post as a draft document, with its title, its content as Portable "
        "Text and an excerpt. Nothing is published. The document's identifier is a digest of "
        "the idempotency key; a repeat finds the post, draft or published, by it.",
    },
    {
        "name": "website.posts.publish",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Publish a drafted post. The post's state is its own mark: one published with "
        "no draft left is not published again and reports replayed. Weaker than a key, and "
        "stated so. A draft changed while it was published is a conflict.",
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
