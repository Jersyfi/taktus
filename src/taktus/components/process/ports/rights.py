"""Who may create a process, approve a version for operation and set its autonomy level, seen
from registration (ADR-0257, UC-7.3). The identity component keeps the rights per role; the
composition root answers this port from it."""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant

CREATE = "process.create"
APPROVE = "process.approve"
SET_AUTONOMY = "autonomy.set"
OF_A_PROCESS = frozenset({CREATE, APPROVE, SET_AUTONOMY})
"""The three rights of ADR-0257, as the identity component names them."""


class ProcessRights(Protocol):
    async def granting(self, tenant: Tenant, rights: frozenset[str]) -> bool:
        """Whether any role of the tenant holds one of the rights."""
        ...

    async def holds(self, tenant: Tenant, identity: str, right: str) -> bool:
        """Whether the identity holds the right through one of its roles now."""
        ...
