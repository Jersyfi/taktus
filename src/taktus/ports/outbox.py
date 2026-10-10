"""The outbox: what one use case hands to another, written in the transaction of its cause.

An entry names a topic and carries a payload of identifiers. It is written inside the unit of
work that makes the change it reports, so that the change and the entry exist together or not
at all (ADR-0002: the event bus is an outbox in the database). A reader takes the unpublished
entries of a topic in the order they were written and marks each published once it has acted
on it. An entry it leaves unpublished is read again on its next pass. The one topic today is
`intake.accepted`, written by the intake and read by the automation role (ADR-0048).

Every call happens inside a unit of work of the same persistence and names its tenant
(`ports/persistence.py`). Keeping two readers apart is not the outbox's: the automation role
leads, and only the leader reads (ADR-0048 §4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value

INTAKE_ACCEPTED = "intake.accepted"
"""An intake event was kept; the payload is `{"event_id": …}`."""


class OutboxEntry(Value):
    id: int = Field(ge=1)
    """Increases in the order entries were written, within a tenant."""
    topic: str = Field(min_length=1)
    payload: Mapping[str, Any]
    created_at: datetime


class Outbox(Protocol):
    async def write(self, tenant: Tenant, topic: str, payload: Mapping[str, Any]) -> None:
        """Add an unpublished entry, in the open transaction."""
        ...

    async def unpublished(self, tenant: Tenant, topic: str, limit: int) -> Sequence[OutboxEntry]:
        """Up to `limit` entries of the topic not yet published, the oldest first."""
        ...

    async def publish(self, tenant: Tenant, entry_id: int) -> None:
        """Mark the entry published; it is not read again. A no-op for one already published."""
        ...
