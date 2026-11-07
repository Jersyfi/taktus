"""What the newsletter connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One read and two writes. A draft is `marked`: the campaign's internal title carries a digest of
the idempotency key, and a repeat finds it among the account's campaigns. A send is `marked` by
the campaign's own status: a campaign already sending or sent is not sent again.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "newsletter.broadcasts"
ACTIONS_CREDENTIAL = "NEWSLETTER_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "newsletter.broadcasts.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Read one campaign: its status, its audience, how many recipients the "
        "audience holds, how many messages were sent and when. Never a recipient's address.",
    },
    {
        "name": "newsletter.broadcasts.draft",
        "demand": {"quota_units": 12},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a campaign to one audience as a draft, with its subject, sender name, "
        "reply address and content. Nothing is sent. The campaign's internal title carries a "
        "digest of the idempotency key; a repeat finds the campaign by it.",
    },
    {
        "name": "newsletter.broadcasts.send",
        "demand": {"quota_units": 3},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Send a drafted campaign to its whole audience. The campaign's status is its "
        "own mark: one already scheduled, sending or sent is not sent again and reports "
        "replayed. Weaker than a key, and stated so.",
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
