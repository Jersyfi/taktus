"""What the product finding reads and where it sends (UC-6.12, ADR-0046).

Two ports. **`Blocks`** is the run's blocked-time accounts, read: every block that ended and
every block still open, as the run records them (ADR-0043). The composition root binds it to the
run's query; this component never imports the run.

**`FindingChannel`** is where findings are sent: the Taktus repository, through a connector, on
an instance whose operator enabled it. It holds every finding it was sent, each with its texts.
The marks in those texts say what it holds (`domain/service/texts.py`), so the instance keeps no
memory of what it sent and a restart sends nothing twice.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import Field

from taktus.components.reporting.domain.model import Blocked
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class Blocks(Protocol):
    async def blocks(self, tenant: Tenant) -> Sequence[Blocked]:
        """Every block of the tenant, ended or open, a rehearsal's left out."""
        ...


class Held(Value):
    """One finding a channel holds: where it is, whether it is still open, and its texts — the
    body and every later addition — in order."""

    reference: str = Field(min_length=1)
    open: bool
    texts: tuple[str, ...]


class ChannelIncomplete(Exception):
    """The channel could not read everything it holds. Nothing is sent: a finding sent on an
    incomplete reading could be sent twice."""


class FindingChannel(Protocol):
    @property
    def name(self) -> str:
        """The identifier of the channel's adapter configuration: what the ledger records."""
        ...

    async def held(self, tenant: Tenant) -> Sequence[Held]:
        """Every finding the channel holds, open or closed. Raises `ChannelIncomplete` when it
        cannot read them all."""
        ...

    async def open(self, tenant: Tenant, title: str, body: str, *, key: str) -> str:
        """Open a finding; its reference. The same key again opens nothing new."""
        ...

    async def add(self, tenant: Tenant, reference: str, text: str, *, key: str) -> None:
        """Add a text to an open finding. The same key again adds nothing new."""
        ...
