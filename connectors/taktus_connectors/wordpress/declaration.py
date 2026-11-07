"""What the website connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes. A draft is `marked`: its slug carries a digest of the idempotency key,
and a repeat finds the post by it. Publishing is `marked` by the post's own status: a post
already published is not published again.
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
        "summary": "Read one post of the site: its status, its title, its address and when it "
        "was last changed.",
    },
    {
        "name": "website.posts.draft",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a post as a draft, with its title, its content and an excerpt. "
        "Nothing is published. The post's slug carries a digest of the idempotency key; a "
        "repeat finds the post by it.",
    },
    {
        "name": "website.posts.publish",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Publish a drafted post. The post's status is its own mark: one already "
        "published is not published again and reports replayed. Weaker than a key, and stated "
        "so. A post a person scheduled is a conflict.",
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
