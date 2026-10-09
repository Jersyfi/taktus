"""Who may decide: an identity, the roles it holds, its department (ADR-0042).

The identity component keeps identities and their roles; the decision component asks through
this port, and the composition root answers from the identity component, because components
never import each other.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class Decider(Value):
    identity: str = Field(min_length=1)
    roles: tuple[str, ...] = ()
    department: str | None = Field(default=None, min_length=1)
    """The first unit below the tenant in the identity's organisational path; None for an
    identity placed at the tenant itself."""


class Deciders(Protocol):
    async def place(self, tenant: Tenant, identity: str) -> Decider | None:
        """The identity as a decider, or None when the tenant does not know it."""
        ...
