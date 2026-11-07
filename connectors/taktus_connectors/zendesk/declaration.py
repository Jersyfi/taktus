"""What the helpdesk connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two capabilities (ADR-0205). `helpdesk.tickets`: tickets listed and read, an internal note
added and a ticket closed with a tag. `helpcentre.articles`: the help centre's articles listed,
and an article created as a draft, never published. Every write is `marked`: a note carries the
idempotency key as its last line, a draft article a label made from the key, and a close its own
tag. Nothing here writes to a customer: a note is internal, a draft is unpublished.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
TICKETS = "helpdesk.tickets"
ARTICLES = "helpcentre.articles"
ACTIONS_CREDENTIAL = "HELPDESK_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "helpdesk.tickets.list",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "read",
        "summary": "The tickets of `status` (new, open, pending, hold, solved, closed; `unsolved`, "
        "the default, for the first four; `all`), newest change first, up to `limit` (default "
        "100, at most 1000). Each names its subject, its description, its status, its requester "
        "by identifier only, its tags and when it was created and changed. `with_comments` adds "
        "every comment after the description (then at most 25 tickets). `complete` says whether "
        "every ticket was read.",
    },
    {
        "name": "helpdesk.tickets.read",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "read",
        "summary": "One ticket by its `id`, in the shape of a listed one, with `comments`: each "
        "comment after the description with its text, whether it is public and whether the "
        "requester wrote it.",
    },
    {
        "name": "helpdesk.tickets.note",
        "demand": {"quota_units": 3},
        "capability": TICKETS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Add an internal note, never public, of `text` to the ticket `id`. The note "
        "ends with the idempotency key; a repeat finds it among the ticket's comments.",
    },
    {
        "name": "helpdesk.tickets.close",
        "demand": {"quota_units": 2},
        "capability": TICKETS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Add the tag `tag` to the ticket `id` and set it solved, without a reply. The "
        "tag is its own mark: a ticket solved with the tag already is not changed, and a repeat "
        "reports replayed. Weaker than a key, and stated so.",
    },
    {
        "name": "helpcentre.articles.list",
        "demand": {"quota_units": 1},
        "capability": ARTICLES,
        "effect": "read",
        "summary": "The help centre's articles, up to `limit` (default 100, at most 1000): each "
        "with its title, section, whether it is a draft, its address, labels and last change. "
        "`complete` says whether every article was read.",
    },
    {
        "name": "helpcentre.articles.draft",
        "demand": {"quota_units": 2},
        "capability": ARTICLES,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create an article of `title` and `body` in the section `section` as a draft "
        "(`locale` default en-us), never published and without notifying subscribers. It "
        "carries a label made from the idempotency key; a repeat finds it in the section.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [TICKETS, ARTICLES],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
