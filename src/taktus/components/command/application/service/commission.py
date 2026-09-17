"""Use case: a command becomes a commissioned plan.

The steps the plan carries are given in execution order by whoever holds the process version;
this component reads them as the shared kernel's `Step` and knows nothing of the process
component's classes (ADR-0016). The command is stored, the plan is stored — one transaction —
and the plan is returned commissioned by the command's identity at the clock's time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import (
    AutonomyLevel,
    Command,
    Commissioned,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)


@dataclass(frozen=True)
class CommissionPlan:
    command: Command
    tenant: Tenant
    goal: str
    autonomy_level: AutonomyLevel
    steps: Sequence[Step]
    results_in: PlanResult = PlanResult.RUN


class CommissionPlanHandler:
    def __init__(
        self,
        commands: Repository[Command],
        plans: Repository[Plan],
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._commands = commands
        self._plans = plans
        self._work = work
        self._clock = clock
        self._ids = ids

    async def execute(self, command: CommissionPlan) -> Plan:
        plan = Plan(
            id=self._ids.new("pln"),
            command_id=command.command.id,
            goal=command.goal,
            autonomy_level=command.autonomy_level,
            steps=tuple(command.steps),
            results_in=command.results_in,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by=command.command.identity, at=self._clock.now()),
        )
        async with self._work.transaction(command.tenant):
            await self._commands.put(command.tenant, command.command)
            await self._plans.put(command.tenant, plan)
        return plan
