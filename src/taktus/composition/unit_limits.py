"""The run's port `UnitLimitsPort`, answered from the governance component's unit limits and the
identity component's directory (ADR-0282, UC-8.5, UC-8.10). Components never import each other;
the composition root joins them here."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date

from taktus.components.governance.application.service.unit_limits import UnitLimits
from taktus.components.governance.domain.model.unit_limits import UnitLimit, period_of
from taktus.components.identity.application.service.directory import IdentityDirectory
from taktus.components.run.ports.unit_limits import AppliedLimit
from taktus.ports.clock import Clock
from taktus.ports.persistence import Tenant

type Placed = Callable[[Tenant, str], Awaitable[tuple[str, ...] | None]]
"""Where an identity sits below the tenant, or None where the directory does not know it."""


def applied(limit: UnitLimit, clock: Clock) -> AppliedLimit:
    key, starts, ends = period_of(limit.period, clock.now())
    return AppliedLimit(
        name=limit.id,
        unit=limit.unit,
        individually=limit.individually,
        process=limit.process,
        period=limit.period,
        lines=limit.amounts.lines(),
        policy=limit.policy,
        check_every_seconds=limit.check_every_seconds,
        role=limit.role,
        key=key,
        starts=starts,
        ends=ends,
    )


class UnitLimitsOfTheRun:
    def __init__(self, limits: UnitLimits, placed: Placed, clock: Clock) -> None:
        self.limits = limits
        """The use case itself, for the command line that shows and sets the limits."""
        self._placed = placed
        self._clock = clock

    async def placed(self, tenant: Tenant, identity: str) -> tuple[str, ...] | None:
        return await self._placed(tenant, identity)

    async def applying(
        self, tenant: Tenant, path: Sequence[str], process: str
    ) -> Sequence[AppliedLimit]:
        return [
            applied(lim, self._clock) for lim in await self.limits.applying(tenant, path, process)
        ]

    async def every(self, tenant: Tenant) -> Sequence[AppliedLimit]:
        return [applied(lim, self._clock) for lim in await self.limits.all(tenant)]

    async def observed(
        self,
        tenant: Tenant,
        name: str,
        spent: Mapping[str, float],
        daily: Mapping[date, Mapping[str, float]],
        process_version: str,
    ) -> None:
        await self.limits.observed(tenant, name, spent, daily, process_version)

    async def refused(
        self,
        tenant: Tenant,
        name: str,
        process_version: str,
        spent: Mapping[str, float],
        demand: Mapping[str, float],
    ) -> None:
        await self.limits.refused(tenant, name, process_version, spent, demand)


def placed_in(directory: IdentityDirectory) -> Placed:
    """Where an identity sits below the tenant, as the identity directory holds it now."""

    async def placed(tenant: Tenant, identity: str) -> tuple[str, ...] | None:
        known = await directory.identity(tenant, identity)
        return None if known is None else tuple(known.org_path[1:])

    return placed
