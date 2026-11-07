"""What a process spends per case, served to a process through the loopback connector
(ADR-0216, UC-03 B-2.02).

A version names the input that is its run's case (`case`): the support message, the pull
request. Every run carries its inputs, so a run's case is the value of that input in the run.
This module names the case of every run of the process, by the version each run ran, and asks
the accounting component for the spend of those runs grouped by case. It is wiring, because it
reads the process and the run component and asks the accounting component, and only the
composition root may hold all three (`composition/README.md`).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from taktus.components.accounting.application.service import SpendHandler, SpendOfCases
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import Run
from taktus.ports.clock import Clock
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class InstanceSpend:
    """The loopback connector's `Spend`, over the instance's versions, runs and ledger."""

    def __init__(
        self,
        spend: SpendHandler,
        versions: Repository[ProcessVersion],
        runs: Repository[Run],
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._spend = spend
        self._versions = versions
        self._runs = runs
        self._work = work
        self._clock = clock

    async def cases(self, tenant: Tenant, process: str, days: int) -> dict[str, Any]:
        cases = await self.of_runs(tenant, process)
        until = self._clock.now()
        found = await self._spend.of_cases(
            SpendOfCases(
                process_id=process,
                tenant=tenant,
                cases=cases,
                since=until - timedelta(days=days),
                until=until,
            )
        )
        document = found.model_dump(mode="json")
        document["days"] = days
        return document

    async def of_runs(self, tenant: Tenant, process: str) -> dict[str, str]:
        """The case of every run of the process whose version names one and which carries it."""
        async with self._work.transaction(tenant):
            versions = {
                v.ref: v.case for v in await self._versions.list(tenant) if v.process_id == process
            }
            runs = [r for r in await self._runs.list(tenant) if r.process_version in versions]
        found: dict[str, str] = {}
        for run in runs:
            name = versions[run.process_version]
            value = None if name is None else run.inputs.get(name)
            if isinstance(value, str | int) and not isinstance(value, bool) and str(value):
                found[run.id] = str(value)
        return found
