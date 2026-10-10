"""The facts the levels of a live representation read, from the run's and the process's records
(ADR-0063, ADR-0064).

`reporting` draws a level and never imports another component (ADR-0003); this module reads a
run from the run's repository, and a process version from the process's, and hands their facts
over in reporting's own shape. Every figure is
the run component's own: what a step recorded it used, and the run's sum, `Run.consumed`
(ADR-0029).
"""

from __future__ import annotations

from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import (
    ProcessFacts,
    ProcessStepFacts,
    RunAtVersion,
    RunFacts,
    StepFacts,
    VersionRef,
    Wait,
)
from taktus.components.run.domain.model import Run, StepRun, StepState
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class RepositoryLevelRecords:
    """`reporting.ports.LevelRecords` over the run's and the process's repositories."""

    def __init__(
        self,
        work: UnitOfWork,
        runs: Repository[Run],
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
    ) -> None:
        self._work = work
        self._runs = runs
        self._processes = processes
        self._versions = versions

    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
        return None if run is None else facts_of(run)

    async def process(
        self, tenant: Tenant, process_id: str, version: str | None
    ) -> ProcessFacts | None:
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            known = [v for v in await self._versions.list(tenant) if v.process_id == process_id]
            active = None if process is None else process.active_version
            chosen = version or active
            found = next((v for v in known if v.version == chosen), None)
            if found is None:
                return None
            runs = [r for r in await self._runs.list(tenant) if r.process_version == found.ref]
        return ProcessFacts(
            id=found.process_id,
            tenant=tenant,
            name=process.name if process is not None else found.name,
            version=found.version,
            autonomy=found.autonomy,
            steps=tuple(
                ProcessStepFacts(
                    id=step.id,
                    method=step.method,
                    exactness=step.exactness,
                    reason=step.reason,
                    rejected=tuple(r.method for r in step.rejected),
                    fallback=None if step.fallback is None else step.fallback.to,
                    depends_on=step.dependencies,
                )
                for step in found.steps
            ),
            versions=tuple(
                VersionRef(version=v.version, active=v.version == active)
                for v in sorted(known, key=lambda v: v.version)
            ),
            runs=tuple(
                RunAtVersion(
                    id=r.id,
                    tenant=r.tenant,
                    state=str(r.state),
                    rehearsal=r.rehearsal,
                    running=tuple(s.step_id for s in r.step_runs if s.state is StepState.RUNNING),
                    created_at=r.created_at,
                )
                for r in runs
            ),
        )


def facts_of(run: Run) -> RunFacts:
    """The facts of a run as reporting reads them."""
    states = {s.step_id: s for s in run.step_runs}
    steps: list[StepFacts] = []
    for step in run.steps:
        ran = states.get(step.id)
        steps.append(
            StepFacts(
                id=step.id,
                method=step.method,
                exactness=step.exactness,
                state="planned" if ran is None else str(ran.state),
                depends_on=step.dependencies,
                attempt=1 if ran is None else ran.attempt,
                consumption=None if ran is None else ran.consumption,
                wait=None if ran is None else _wait(ran),
                started_at=None if ran is None else ran.started_at,
                finished_at=None if ran is None else ran.finished_at,
            )
        )
    return RunFacts(
        id=run.id,
        tenant=run.tenant,
        process_version=run.process_version,
        state=str(run.state),
        rehearsal=run.rehearsal,
        consumed=run.consumed(),
        steps=tuple(steps),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _wait(ran: StepRun) -> Wait | None:
    block = ran.block
    if block is None:
        return None
    anchoring = ran.anchoring
    open_requests = (
        anchoring.requests if anchoring is not None and anchoring.verdict is None else ()
    )
    return Wait(
        account=block.account,
        cause=block.cause,
        since=block.since,
        on=block.on,
        role=block.role,
        requests=open_requests,
    )
