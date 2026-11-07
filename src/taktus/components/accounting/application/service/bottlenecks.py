"""The bottleneck and waiting analysis of a tenant (UC-9.5, ADR-0015, ADR-0283).

What a higher limit would have bought, per limit account and process; a recommendation for
each, which checks a change of method before it proposes a raise; the waits on people by role
or by department; and the ways to wait less on them that the records give a reason for.

Everything is read through this component's ports: the run's blocked-time accounts, the run's
step measures for the check of a method, and the decision component's rules from precedent. A
wait on a person reaches this component only grouped, by role or department, and withheld where
fewer than two persons answered (ADR-0015, protective rule). No figure here names a person.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.accounting.domain.service.bottleneck import (
    MarginalValue,
    Offer,
    Recommendation,
    held_up,
    marginal_values,
    offers,
    recommend,
)
from taktus.components.accounting.ports.bottlenecks import (
    BlockAccounts,
    Grouping,
    MethodCheck,
    Period,
    RecurringDecisions,
    WaitGroup,
)
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class BottleneckAnalysis(Value):
    tenant: str
    marginal: tuple[MarginalValue, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    waits: tuple[WaitGroup, ...] = ()
    """The waits on people, grouped as asked, per period."""
    offers: tuple[Offer, ...] = ()


@dataclass(frozen=True)
class BottlenecksOf:
    tenant: Tenant
    grouping: Grouping = "role"
    period: Period = "month"


class BottlenecksHandler:
    def __init__(
        self,
        accounts: BlockAccounts,
        methods: MethodCheck,
        rules: RecurringDecisions | None = None,
    ) -> None:
        self._accounts = accounts
        self._methods = methods
        self._rules = rules

    async def execute(self, query: BottlenecksOf) -> BottleneckAnalysis:
        blocks = tuple(await self._accounts.blocks(query.tenant))
        marginal = marginal_values(blocks)
        steps = sorted({step for value in marginal for step in held_up(value)})
        checked = {
            (found.process_version, found.step_id): found
            for found in await self._methods.check(query.tenant, steps)
        }
        by_role = tuple(await self._accounts.waits(query.tenant, "role", query.period))
        waits = (
            by_role
            if query.grouping == "role"
            else tuple(await self._accounts.waits(query.tenant, query.grouping, query.period))
        )
        rules = () if self._rules is None else tuple(await self._rules.rules(query.tenant))
        return BottleneckAnalysis(
            tenant=query.tenant,
            marginal=marginal,
            recommendations=tuple(recommend(value, checked) for value in marginal),
            waits=waits,
            offers=offers(blocks, by_role, rules),
        )
