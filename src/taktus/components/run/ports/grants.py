"""Whether a person granted the writes of a connection (ADR-0262 §2).

A connection of a capability in `READ_UNLESS_GRANTED` reads until a person with the right
grants writing on it. The run asks this port before an outward call of such a capability, and
calls nothing when no grant is in force. The grant is the governance component's record; the
composition root answers this port from it.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class WriteGrants(Protocol):
    async def granted(self, tenant: Tenant, capability: str) -> bool:
        """Whether the tenant's grant of writing on the capability's connection is in force."""
        ...
