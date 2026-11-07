"""Use cases of a tenant's domains and their owners (ADR-0259, UC-15.5).

`instantiate` makes a domain with its owner, its jurisdiction and its processes; one without an
owner, with an owner the tenant does not know, with a process another domain holds, or for which
no legal anchor of the tenant would be in force, is refused and changes nothing. `name_owner`
names a new owner; `vacate` records that the owner left, and the domain is shown without an
owner until one is named. `ownerless` is registration's port: the domain of a process that has
no owner, under which no process is raised in autonomy. `views` shows each domain with its
owner, its legal anchors in force and whether its takeover and removal tests passed.

Every change is a ledger entry `domain.*` by the person who made it, in the transaction that
stores it. The owner is named as the domain's addressee, never measured (principle 14).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from taktus.components.governance.domain.model.anchors import (
    AnchorConfiguration,
    shipped_default,
)
from taktus.components.governance.domain.model.domains import Domain, DomainView
from taktus.components.governance.domain.service.anchors import legal_for
from taktus.components.governance.ports.domains import DomainTests
from taktus.components.governance.ports.stages import Identities
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

INSTANTIATED = "domain.instantiated"
OWNER_NAMED = "domain.owner_named"
OWNER_LEFT = "domain.owner_left"


class DomainRefused(ValueError):
    """The domain is not stored; the message says why."""


class UnknownDomain(LookupError):
    def __init__(self, tenant: str, domain: str) -> None:
        super().__init__(f"tenant {tenant!r} has no domain {domain!r}")


@dataclass(frozen=True)
class InstantiateDomain:
    tenant: Tenant
    domain: str
    name: str
    owner: str | None
    jurisdiction: str
    processes: tuple[str, ...] = ()


class TenantDomains:
    def __init__(
        self,
        domains: Repository[Domain],
        anchors: Repository[AnchorConfiguration],
        identities: Identities,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        tests: DomainTests | None = None,
    ) -> None:
        self._domains = domains
        self._anchors = anchors
        self._identities = identities
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._tests = tests
        """Whether a process passed its takeover and removal tests. None: neither is shown as
        passed, and no domain as able to run without Taktus."""

    async def instantiate(self, command: InstantiateDomain, *, by: str) -> Domain:
        """The domain, stored; refused with `DomainRefused` naming why."""
        tenant = command.tenant
        if command.owner is None:
            raise DomainRefused(
                f"the domain {command.domain!r} names no owner: every domain has exactly one "
                "person who answers for it (UC-15.5)"
            )
        await self._known(tenant, command.owner)
        try:
            domain = Domain(
                id=command.domain,
                tenant=tenant,
                name=command.name,
                owner=command.owner,
                jurisdiction=command.jurisdiction,
                processes=command.processes,
                created_at=self._clock.now(),
            )
        except ValueError as error:
            raise DomainRefused(str(error)) from error
        async with self._work.transaction(tenant):
            existing = list(await self._domains.list(tenant))
            if any(d.id == domain.id for d in existing):
                raise DomainRefused(f"the tenant has a domain {domain.id!r} already")
            for other in existing:
                shared = sorted(set(other.processes) & set(domain.processes))
                if shared:
                    raise DomainRefused(
                        f"{', '.join(shared)} belongs to the domain {other.id!r}; a process "
                        "belongs to one domain at most"
                    )
            configuration = await self._anchors.get(tenant, tenant) or shipped_default(tenant)
            if not legal_for(configuration, domain):
                raise DomainRefused(
                    f"no legal anchor of the tenant is in force for the domain {domain.id!r} "
                    f"under {domain.jurisdiction}: its catalogue would be empty, and it can be "
                    "reduced but never emptied (UC-15.5, ADR-0008)"
                )
            await self._domains.put(tenant, domain)
            await self._record(tenant, INSTANTIATED, "instantiated", by)
        return domain

    async def name_owner(self, tenant: Tenant, domain_id: str, owner: str, *, by: str) -> Domain:
        """The domain's owner from now on."""
        await self._known(tenant, owner)
        async with self._work.transaction(tenant):
            domain = await self._get(tenant, domain_id)
            named = domain.model_copy(update={"owner": owner})
            await self._domains.put(tenant, named)
            await self._record(tenant, OWNER_NAMED, "named", by)
        return named

    async def vacate(self, tenant: Tenant, domain_id: str, *, by: str) -> Domain:
        """The owner left: the domain is shown without one until a new one is named."""
        async with self._work.transaction(tenant):
            domain = await self._get(tenant, domain_id)
            left = domain.model_copy(update={"owner": None})
            await self._domains.put(tenant, left)
            await self._record(tenant, OWNER_LEFT, "left", by)
        return left

    async def every(self, tenant: Tenant) -> list[Domain]:
        async with self._work.transaction(tenant):
            return sorted(await self._domains.list(tenant), key=lambda d: d.id)

    async def ownerless(self, tenant: Tenant, process: str) -> str | None:
        """The domain the process belongs to, where that domain has no owner now; None where
        the process belongs to none or its domain has an owner."""
        for domain in await self.every(tenant):
            if process in domain.processes and domain.owner is None:
                return domain.id
        return None

    async def views(self, tenant: Tenant) -> list[DomainView]:
        """Every domain with its owner, its legal anchors in force and its tests."""
        domains = await self.every(tenant)
        async with self._work.transaction(tenant):
            configuration = await self._anchors.get(tenant, tenant) or shipped_default(tenant)
        shown: list[DomainView] = []
        for domain in domains:
            takeover = {p: await self._takeover(tenant, p) for p in domain.processes}
            removal = {p: await self._removal(tenant, p) for p in domain.processes}
            shown.append(
                DomainView(
                    domain=domain.id,
                    name=domain.name,
                    owner=domain.owner,
                    jurisdiction=domain.jurisdiction,
                    processes=domain.processes,
                    legal=legal_for(configuration, domain),
                    takeover=takeover,
                    removal=removal,
                )
            )
        return shown

    async def emptied(self, tenant: Tenant, configuration: AnchorConfiguration) -> Sequence[str]:
        """The domains a configuration would leave without a legal anchor in force: the
        anchors' configuration is refused for each (UC-15.5 §2)."""
        return [d.id for d in await self.every(tenant) if not legal_for(configuration, d)]

    async def _takeover(self, tenant: Tenant, process: str) -> bool:
        return self._tests is not None and await self._tests.takeover_passed(tenant, process)

    async def _removal(self, tenant: Tenant, process: str) -> bool:
        return self._tests is not None and await self._tests.removal_passed(tenant, process)

    async def _known(self, tenant: Tenant, owner: str) -> None:
        if await self._identities.identity(tenant, owner) is None:
            raise DomainRefused(
                f"{owner!r} is no identity of the tenant: the owner of a domain is a person "
                "the tenant knows"
            )

    async def _get(self, tenant: Tenant, domain_id: str) -> Domain:
        domain = await self._domains.get(tenant, domain_id)
        if domain is None:
            raise UnknownDomain(tenant, domain_id)
        return domain

    async def _record(self, tenant: Tenant, kind: str, outcome: str, by: str) -> None:
        await self._ledger.record(
            tenant, Fact(kind=kind, refs=LedgerRefs(tenant=tenant, actor=by), outcome=outcome)
        )
