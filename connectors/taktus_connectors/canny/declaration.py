"""What the feedback portal connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes of the capability `feedback.posts` (ADR-0207). Reading posts changes
nothing. Creating a post leaves the system, `marked`: the post's details carry a reference
derived from the idempotency key, and the customer's own posts on the board are searched for it
before acting. A vote is `marked` by itself: the portal holds one vote per customer and post,
and a repeat that finds the customer's vote changes nothing and reports replayed — weaker than a
key, and stated so, as a label is its own mark (ADR-0097).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "feedback.posts"
ACTIONS_CREDENTIAL = "FEEDBACK_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "feedback.posts.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The posts of the board `board`, those matching `search` where it is given, "
        "up to `limit` (default 100, at most 1000): each its id, title, details, status, score "
        "(the votes it holds) and url, never its author. `complete` says whether every post "
        "fit within `limit`.",
    },
    {
        "name": "feedback.posts.create",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a post on the board `board` with `title` and `details`, authored by "
        "the portal's user of the customer `email`. The details carry a reference derived "
        "from the idempotency key; a repeat finds it among the customer's posts on the board "
        "and creates nothing. A customer the portal does not know is invalid.",
    },
    {
        "name": "feedback.posts.vote",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Count the vote of the portal's user of the customer `email` on the post "
        "`post`. The vote is its own mark: the portal holds one per customer and post, and a "
        "repeat that finds it changes nothing and reports replayed — so does a call after the "
        "customer voted by other means.",
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
