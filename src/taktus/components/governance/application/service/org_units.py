"""A tenant's quotas per organisational unit, kept and changed (ADR-0166, UC-7.11).

The runner asks for the units' limits of concurrent runs, the run for a unit's monthly budget,
through its port `OrgUnits`, which the composition root answers from here. A change is the
ledger entry `units.configured`, by the person who made it, in the transaction that stores it.

A quota limits a unit and never a person (principle 14): a unit whose name is an identity of
the tenant is refused, and nothing here counts or shows what a named person ran.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from taktus.components.governance.domain.model.org_units import OrgUnitQuota
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CONFIGURED = "units.configured"


class OrgUnitQuotaRefused(ValueError):
    """A quota that would not limit a unit: it names a person, or it does not hold."""


@dataclass(frozen=True)
class SetOrgUnitQuota:
    """The quota one unit holds from now on; neither limit clears it."""

    tenant: Tenant
    org_unit: str
    concurrent_runs: int | None = None
    budget: Mapping[str, float] | None = None
    check_every_seconds: int = 900


class TenantOrgUnits:
    def __init__(
        self,
        quotas: Repository[OrgUnitQuota],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        names_a_person: Callable[[Tenant, str], Awaitable[bool]],
    ) -> None:
        self._quotas = quotas
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._names_a_person = names_a_person
        """Whether a name is an identity of the tenant: such a name is never a unit."""

    async def quotas(self, tenant: Tenant) -> list[OrgUnitQuota]:
        """Every quota the tenant holds, by unit; a cleared one is not listed."""
        async with self._work.transaction(tenant):
            stored = await self._quotas.list(tenant)
        return sorted((q for q in stored if not q.cleared), key=lambda q: q.org_unit)

    async def quota(self, tenant: Tenant, org_unit: str) -> OrgUnitQuota | None:
        async with self._work.transaction(tenant):
            found = await self._quotas.get(tenant, org_unit)
        return None if found is None or found.cleared else found

    async def set(self, command: SetOrgUnitQuota, *, by: str) -> OrgUnitQuota:
        """Store the unit's quota, replacing the one it held. Refused, and nothing changed,
        for a unit that names an identity of the tenant or a quota that does not hold."""
        if await self._names_a_person(command.tenant, command.org_unit):
            raise OrgUnitQuotaRefused(
                f"{command.org_unit!r} is an identity of the tenant; a quota limits a unit, "
                "never a person (principle 14)"
            )
        try:
            quota = OrgUnitQuota(
                id=command.org_unit,
                tenant=command.tenant,
                org_unit=command.org_unit,
                concurrent_runs=command.concurrent_runs,
                budget=None if command.budget is None else dict(command.budget),
                check_every_seconds=command.check_every_seconds,
                configured_at=self._clock.now(),
            )
        except ValueError as error:
            raise OrgUnitQuotaRefused(str(error)) from error
        async with self._work.transaction(command.tenant):
            await self._quotas.put(command.tenant, quota)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind=CONFIGURED,
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="cleared" if quota.cleared else "configured",
                ),
            )
        return quota

    async def concurrent(self, tenant: Tenant) -> dict[str, int]:
        """Each unit's limit of concurrent runs; a unit without one is absent."""
        return {
            q.org_unit: q.concurrent_runs
            for q in await self.quotas(tenant)
            if q.concurrent_runs is not None
        }
