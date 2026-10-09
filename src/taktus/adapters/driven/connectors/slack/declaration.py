"""What the chat connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations of one capability, `chat.threads`, and an intake of two event kinds. Each
operation declares its `demand`: the most requests to the service one call makes, which is what
a run reserves before calling it (ADR-0005). A read pages through a thread, at most `MAX_PAGES`
pages; a post looks for its mark first — in the thread, page by page, or among the most recent
messages of the conversation — and then posts once.

The effect of a post is `delivery`: a message reaches a person through a channel (ADR-0022). Its
idempotency is `marked`: the service keeps a structured field on every message, its metadata,
and the key goes there; a repeat finds the message by it.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CHANNEL = "channel.chat"

ACTIONS_CREDENTIAL = "CHAT_TOKEN"
INTAKE_CREDENTIAL = "CHAT_SIGNING_SECRET"

MAX_PAGES = 10
"""How many pages of a thread a read or a lookup reads, at most."""

CAPABILITIES = ["chat.threads"]

OPERATIONS: list[Json] = [
    {
        "name": "chat.threads.read",
        "demand": {"quota_units": MAX_PAGES},
        "capability": "chat.threads",
        "effect": "read",
        "summary": "Read one thread of a conversation: its first message and every reply, "
        "oldest first, each with its author as the service names them. `complete` says "
        "whether every page was read.",
    },
    {
        "name": "chat.threads.post",
        "demand": {"quota_units": MAX_PAGES + 1},
        "capability": "chat.threads",
        "effect": "delivery",
        "idempotency": "marked",
        "summary": "Post a message into a conversation, into a thread when one is named. The "
        "message carries the idempotency key in its metadata; a repeat finds it there and "
        "posts nothing.",
    },
]

INTAKE_EVENTS = ["message.posted", "message.mentioned"]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": list(CAPABILITIES),
        "operations": [dict(op) for op in OPERATIONS],
        "intake": {
            "events": list(INTAKE_EVENTS),
            "signature": {"scheme": "hmac-sha256-timestamped"},
        },
        "credentials": [
            {"name": ACTIONS_CREDENTIAL, "purpose": "actions"},
            {"name": INTAKE_CREDENTIAL, "purpose": "intake"},
        ],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
