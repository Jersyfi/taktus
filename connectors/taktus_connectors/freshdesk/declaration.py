"""What the second helpdesk connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

The capability `helpdesk.tickets` with the four operations and the shapes the other helpdesk
connector declares, so that a process runs on either (ADR-0205). Both writes are `marked`: a
note carries the idempotency key as its last paragraph, a close its own tag. A note is internal;
nothing here writes to a customer.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
TICKETS = "helpdesk.tickets"
ACTIONS_CREDENTIAL = "HELPDESK_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "helpdesk.tickets.list",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "read",
        "summary": "The tickets of `status` (open, pending, solved, closed; `unsolved`, the "
        "default, for open and pending; `all`) created in the past 30 days, newest change "
        "first, up to `limit` (default 100, at most 1000). Each names its subject, its status, "
        "its requester by identifier only, its tags and when it was created and changed. "
        "`with_comments` adds the description and every conversation (then at most 25 "
        "tickets). `complete` says whether every ticket was read.",
    },
    {
        "name": "helpdesk.tickets.read",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "read",
        "summary": "One ticket by its `id`, with its description and `comments`: each "
        "conversation with its text, whether it is public and whether the requester wrote it.",
    },
    {
        "name": "helpdesk.tickets.note",
        "demand": {"quota_units": 3},
        "capability": TICKETS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Add a private note of `text` to the ticket `id`. The note ends with the "
        "idempotency key; a repeat finds it among the ticket's conversations.",
    },
    {
        "name": "helpdesk.tickets.close",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Add the tag `tag` to the ticket `id` and set it resolved, without a reply. "
        "The tag is its own mark: a ticket resolved with the tag already is not changed, and a "
        "repeat reports replayed. Weaker than a key, and stated so.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [TICKETS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
