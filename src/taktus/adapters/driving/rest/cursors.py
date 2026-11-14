"""The opaque cursor a page hands out, and the place it names (ADR-0094 §3, ADR-0319).

A cursor is the creation time and the id of the last aggregate a reader received, encoded so
that the reader passes it back unread. One this surface did not hand out names no place.
"""

from __future__ import annotations

import base64
from datetime import datetime

from taktus.ports.persistence import Mark


def marked(created_at: datetime, id: str) -> str:
    """Where the next page starts, as the reader passes it back: opaque to them."""
    return base64.urlsafe_b64encode(f"{created_at.isoformat()} {id}".encode()).decode()


def unmarked(cursor: str) -> Mark | None:
    """The place a cursor names; None for one this surface did not hand out."""
    try:
        at, _, id = base64.urlsafe_b64decode(cursor.encode()).decode().partition(" ")
        created = datetime.fromisoformat(at)
    except ValueError:
        return None
    if not id or created.tzinfo is None:
        return None
    return Mark(created_at=created, id=id)
