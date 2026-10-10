"""The levels of a live representation, read for one reader (UC-6.10, ADR-0063).

A level is read from the records of the component that owns them and drawn by
`domain/service/levels.py`; nothing drawn is stored. Whether the reader may see it is the one
predicate of `domain/service/visibility.py`, the same the stream of changes asks (ADR-0055 §5).
A run the reader may not see is answered as absent, exactly as one that does not exist.
"""

from __future__ import annotations

from taktus.components.reporting.domain.model.live import ProcessRef, Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.levels import (
    OverviewLevel,
    ProcessLevel,
    RunLevel,
    overview_level,
    process_level,
    run_level,
)
from taktus.components.reporting.ports.levels import LevelRecords


class LevelQueries:
    def __init__(self, records: LevelRecords) -> None:
        self._records = records

    async def run(self, reader: Reader, run_id: str) -> RunLevel | None:
        """The run level of one run; None when there is no such run or the reader may not
        see it — the two are answered alike."""
        facts = await self._records.run(reader.tenant, run_id)
        if facts is None:
            return None
        ref = RunRef(id=facts.id, tenant=facts.tenant, process_version=facts.process_version)
        if not visibility.may_see(reader, ref):
            return None
        return run_level(facts)

    async def process(
        self, reader: Reader, process_id: str, version: str | None = None
    ) -> ProcessLevel | None:
        """The process level of one version — the active one by default; None when there is
        no such process or version, or the reader may not see it. Only the runs the reader may
        see are drawn and counted."""
        facts = await self._records.process(reader.tenant, process_id, version)
        if facts is None:
            return None
        if not visibility.may_see_process(reader, ProcessRef(id=facts.id, tenant=facts.tenant)):
            return None
        ref = facts.ref
        seen = tuple(
            run
            for run in facts.runs
            if visibility.may_see(reader, RunRef(id=run.id, tenant=run.tenant, process_version=ref))
        )
        return process_level(facts.model_copy(update={"runs": seen}))

    async def overview(self, reader: Reader) -> OverviewLevel:
        """The overview of the reader's tenant. A process the reader may not see is absent, and
        so is every run of it; a run the reader may not see is neither drawn nor counted."""
        facts = await self._records.overview(reader.tenant)
        processes = tuple(
            p
            for p in facts.processes
            if visibility.may_see_process(reader, ProcessRef(id=p.id, tenant=facts.tenant))
        )
        runs = tuple(
            r
            for r in facts.runs
            if visibility.may_see_process(reader, ProcessRef(id=r.process, tenant=r.tenant))
            and visibility.may_see(
                reader, RunRef(id=r.id, tenant=r.tenant, process_version=r.process_version)
            )
        )
        return overview_level(facts.model_copy(update={"processes": processes, "runs": runs}))
