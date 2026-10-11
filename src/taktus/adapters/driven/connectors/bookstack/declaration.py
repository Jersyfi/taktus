"""What the wiki connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

The three operations of the capability `knowledge.pages`, as ADR-0065 §4 states them. Each
declares its `demand`: the most requests to the wiki one call makes, which is what a run
reserves before calling it (ADR-0005). A place is found in two requests — the shelf by its name,
then its books. The pages of a book are listed `PAGE` entries at a time, in at most
`MAX_LISTINGS` requests. A list then reads every page it names, at most `MAX_PAGES` of them. A
write reads the page it replaces and writes once. It writes the page's tags a second time only
where the wiki changed the text it stored (`operations.py`).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "knowledge.pages"
LIST = f"{CAPABILITY}.list"
READ = f"{CAPABILITY}.read"
WRITE = f"{CAPABILITY}.write"

ACTIONS_CREDENTIAL = "KNOWLEDGE_TOKEN"

PAGE = 500
"""How many entries one listing request asks for: the most the wiki answers with."""
MAX_LISTINGS = 2
"""How many listing requests the pages of one book take, at most."""
MAX_BOOKS = 4
"""How many books of a shelf one list reads, at most; a shelf with more is refused."""
MAX_PAGES = 60
"""How many pages one list reads, at most; a place with more is refused, never cut short."""

FIND = 2  # the shelf by its name, then its books
LIST_DEMAND = FIND + MAX_BOOKS * MAX_LISTINGS + MAX_PAGES
READ_DEMAND = FIND + MAX_LISTINGS + 1
WRITE_DEMAND = FIND + MAX_LISTINGS + 4  # the page read, the write, a read-back, the tags

OPERATIONS: list[Json] = [
    {
        "name": LIST,
        "capability": CAPABILITY,
        "effect": "read",
        "demand": {"quota_units": LIST_DEMAND},
        "summary": "Every page at or below a place — a shelf, a book of it, or one page — each "
        "with its place, the digest of its text and the mark kept beside it.",
    },
    {
        "name": READ,
        "capability": CAPABILITY,
        "effect": "read",
        "demand": {"quota_units": READ_DEMAND},
        "summary": "One page at a place of three names, shelf, book and page: its text, the "
        "digest of the text, the mark kept beside it; not_found where no page is.",
    },
    {
        "name": WRITE,
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "demand": {"quota_units": WRITE_DEMAND},
        "summary": "Put a page at a place of three names, with a mark beside it, only where the "
        "page there has the expected digest, or none is there when none is expected. The key "
        "is kept in the page's tags; a repeat finds it there and writes nothing.",
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
