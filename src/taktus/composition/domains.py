"""The governance component's port `DomainTests`, answered from the process and catalog
components (ADR-0259 §4, UC-15.5).

A process passed its **takeover test** when a person passed a trial of the takeover instructions
of its active version (ADR-0180 §3). It passed its **removal test** when every adapter that
served one of its steps, as the ledger records it, has a removal verdict, and none of them is
`broke` or `untested` (ADR-0030). A process that no adapter served yet has not passed it.
"""

from __future__ import annotations

from taktus.components.catalog.domain.model.maturity import AdapterMaturity, Verdict
from taktus.components.process.domain.model import Process
from taktus.components.process.domain.model.takeover import TakeoverTrial
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

PASSED = (Verdict.CHANGED, Verdict.EXCEPTION)


class DomainTestsOfTheInstance:
    def __init__(
        self,
        processes: Repository[Process],
        trials: Repository[TakeoverTrial],
        maturities: Repository[AdapterMaturity],
        ledger: Ledger,
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._trials = trials
        self._maturities = maturities
        self._ledger = ledger
        self._work = work

    async def takeover_passed(self, tenant: Tenant, process: str) -> bool:
        async with self._work.transaction(tenant):
            found = await self._processes.get(tenant, process)
            if found is None or found.active_version is None:
                return False
            ref = f"{process}@{found.active_version}"
            return any(
                t.passed and t.process_version == ref for t in await self._trials.list(tenant)
            )

    async def removal_passed(self, tenant: Tenant, process: str) -> bool:
        async with self._work.transaction(tenant):
            finished = await self._ledger.of_kinds(tenant, ("step.finished",))
            served = {
                e.adapter
                for e in finished
                if e.adapter is not None
                and (e.refs.process_version or "").rpartition("@")[0] == process
            }
            if not served:
                return False
            records = {m.id: m for m in await self._maturities.list(tenant)}
        for adapter in served:
            record = records.get(adapter)
            if record is None or record.removal is None or record.removal.verdict not in PASSED:
                return False
        return True
