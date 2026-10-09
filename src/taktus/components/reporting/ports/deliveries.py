"""Saying something in a channel, and opening a task in a ticket system (ADR-0045).

The component names a channel by its capability and a ticket system by a capability and an
operation, as the tenant configured them; which connector serves them, and how it is called as
Taktus itself (ADR-0033), is the composition root's answer. Every call carries an idempotency
key, so that a delivery repeated after a restart is said once.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Capability, Value


class Sent(Value):
    """Delivered. `thread` is where an answer to it is given, when the channel has threads;
    `record` and `url` are the record the target system made, as the connector names it."""

    thread: str | None = Field(default=None, min_length=1)
    record: str | None = Field(default=None, min_length=1)
    url: str | None = Field(default=None, min_length=1)


class NotDelivered(Value):
    reason: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    """`no_connector`: nothing serves the channel or offers the operation; `refused`: the
    connector answered with an error; `unreachable`: it did not answer."""


class Deliveries(Protocol):
    async def say(
        self,
        tenant: Tenant,
        channel: Capability,
        address: str,
        text: str,
        *,
        thread: str | None = None,
        key: str,
    ) -> Sent | NotDelivered:
        """Say `text` at `address` in `channel`, in `thread` when one is named."""
        ...

    async def open_task(
        self,
        tenant: Tenant,
        capability: Capability,
        operation: str,
        title: str,
        body: str,
        *,
        key: str,
    ) -> Sent | NotDelivered:
        """Open a task in a ticket system through the operation that serves it."""
        ...
