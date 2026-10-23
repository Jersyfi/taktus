"""A tenant's declaration of its sources, kept and changed (ADR-0130, UC-7.7).

The run asks it through its port `Sources` before a step calls a connector, and registration
asks it before it stores a version with an analytic step. A change is the ledger entry
`sources.configured` in the transaction that stores it, naming who changed it.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.governance.domain.model.sources import (
    SourceDeclaration,
    shipped_declaration,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "sources.configured"


@dataclass(frozen=True)
class DeclareSources:
    """What a tenant changes of its declaration: each capability in `free` or `personal` is
    put on that list, and taken off the other; each in `withdrawn` is taken off both."""

    tenant: Tenant
    free: tuple[str, ...] = ()
    personal: tuple[str, ...] = ()
    withdrawn: tuple[str, ...] = ()


class TenantSources:
    def __init__(
        self,
        declarations: Repository[SourceDeclaration],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._declarations = declarations
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def declaration(self, tenant: Tenant) -> SourceDeclaration:
        """The tenant's declaration, or the shipped default where it declared nothing."""
        async with self._work.transaction(tenant):
            found = await self._declarations.get(tenant, tenant)
        return found or shipped_declaration(tenant)

    async def free_of_personal_fields(self, tenant: Tenant, capability: str) -> bool:
        """The run's and registration's port: whether an analytic step may read it."""
        return capability in (await self.declaration(tenant)).free

    async def personal(self, tenant: Tenant, capability: str) -> bool:
        """The run's port: whether the tenant declares that it serves personal data."""
        return capability in (await self.declaration(tenant)).personal

    async def declare(self, command: DeclareSources, *, by: str) -> SourceDeclaration:
        """Change what the command names, keep the rest. A capability named on both lists, or
        not a capability, is refused as a ValueError and changes nothing."""
        current = await self.declaration(command.tenant)
        moved = set(command.free) | set(command.personal) | set(command.withdrawn)
        free = [c for c in current.free if c not in moved] + list(dict.fromkeys(command.free))
        personal = [c for c in current.personal if c not in moved] + list(
            dict.fromkeys(command.personal)
        )
        declared = SourceDeclaration.model_validate(
            {
                "id": command.tenant,
                "tenant": command.tenant,
                "free": sorted(free),
                "personal": sorted(personal),
                "configured_at": self._clock.now(),
            }
        )
        async with self._work.transaction(command.tenant):
            await self._declarations.put(command.tenant, declared)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="declared",
                ),
            )
        return declared
