"""A tenant's limits per unit of its structure, seen from the run (ADR-0282, UC-8.5, UC-8.10).

The governance component keeps the limits a tenant set: per unit of the structure — the
company, a department, a team, each person of a unit — and per process, money, compute seconds
or tokens per day, week or month. The engine attributes a run to where its identity sits when
it is created, and admits a step only where its priced reservation fits what remains of every
limit on the run's path. It hands back what it saw, so that the governance component can alert,
forecast, find an anomaly and judge whether a limit does harm. The composition root answers from the
governance component, because components never import each other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class AppliedLimit(Value):
    """One limit that holds a run."""

    name: str = Field(min_length=1)
    unit: tuple[str, ...] = ()
    individually: bool = False
    """Each person of the unit is held on their own, by the runs they commissioned."""
    process: str | None = None
    period: Literal["day", "week", "month"]
    lines: Mapping[str, float]
    """Each amount by its line: `money.<currency>`, `compute_seconds`, `tokens`."""
    policy: Literal["halt", "wait"]
    check_every_seconds: int = Field(default=900, ge=1)
    role: str = Field(min_length=1)
    key: str = Field(min_length=1)
    """The period in force now: `2026-11`, `2026-W45`, `2026-11-07`."""
    starts: datetime
    ends: datetime
    """The first instant of the period and of the next, in UTC."""

    def where(self) -> str:
        return "/".join(self.unit) if self.unit else "company"

    def applies(self, path: Sequence[str], process: str) -> bool:
        if tuple(path[: len(self.unit)]) != self.unit:
            return False
        return self.process is None or self.process == process


class UnitLimitsPort(Protocol):
    async def placed(self, tenant: Tenant, identity: str) -> tuple[str, ...] | None:
        """Where the identity sits below the tenant, or None where the directory does not know
        it. Opens its own unit of work."""
        ...

    async def applying(
        self, tenant: Tenant, path: Sequence[str], process: str
    ) -> Sequence[AppliedLimit]:
        """Every limit that holds a run of this path and process."""
        ...

    async def every(self, tenant: Tenant) -> Sequence[AppliedLimit]:
        """Every limit the tenant holds, of every unit."""
        ...

    async def observed(
        self,
        tenant: Tenant,
        name: str,
        spent: Mapping[str, float],
        daily: Mapping[date, Mapping[str, float]],
        process_version: str,
    ) -> None:
        """What the limit's runs cost this period and per day: alert and watch for anomalies."""
        ...

    async def refused(
        self,
        tenant: Tenant,
        name: str,
        process_version: str,
        spent: Mapping[str, float],
        demand: Mapping[str, float],
    ) -> None:
        """A step did not fit the limit; it is booked already. Tell, and judge its harm."""
        ...
