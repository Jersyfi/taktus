"""The facts the levels of a live representation read, from the run's and the process's records
(ADR-0063, ADR-0064, ADR-0067, ADR-0068).

`reporting` draws a level and never imports another component (ADR-0003); this module reads a
run from the run's repository, a process version from the process's, the status of a decision
request from the decision component's, and the provenance records behind a result from the
run's provenance store, and hands their facts over in reporting's own shape. Every figure is
the run component's own: what a step recorded it used, and the run's sum, `Run.consumed`
(ADR-0029).
"""

from __future__ import annotations

from collections.abc import Mapping

from taktus.components.decision.domain.model import Request
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import (
    DecisionFacts,
    OriginFacts,
    OverviewFacts,
    ProcessFacts,
    ProcessStepFacts,
    ProcessSummary,
    RunActivity,
    RunAtVersion,
    RunFacts,
    RunningStep,
    StepFacts,
    VersionRef,
    Wait,
)
from taktus.components.run.domain.model import WAITING, WORKING, Run, StepRun, StepState
from taktus.ports.persistence import ProvenanceStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import DecisionStatus, Provenance


class RepositoryLevelRecords:
    """`reporting.ports.LevelRecords` over the run's and the process's repositories."""

    def __init__(
        self,
        work: UnitOfWork,
        runs: Repository[Run],
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        provenance: ProvenanceStore,
        requests: Repository[Request],
    ) -> None:
        self._work = work
        self._runs = runs
        self._processes = processes
        self._versions = versions
        self._provenance = provenance
        self._requests = requests

    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            if run is None:
                return None
            raised = [r for s in run.step_runs if s.anchoring for r in s.anchoring.requests]
            found = [await self._requests.get(tenant, r) for r in raised]
        statuses = {r.id: r.status for r in found if r is not None}
        return facts_of(run, statuses)

    async def origin(self, tenant: Tenant, run_id: str, step_id: str) -> OriginFacts | None:
        records: dict[str, list[Provenance]] = {}
        async with self._work.transaction(tenant):

            async def of(run: str) -> list[Provenance]:
                if run not in records:
                    records[run] = list(await self._provenance.of_run(tenant, run))
                return records[run]

            produced = [r for r in await of(run_id) if r.step_id == step_id]
            if not produced:
                return None
            path: list[Provenance] = [max(produced, key=lambda r: r.ledger_seq)]
            seen = {(run_id, step_id)}
            index = 0
            while index < len(path):
                for run, step in sorted(path[index].reads_from()):
                    if (run, step) in seen:
                        continue
                    seen.add((run, step))
                    earlier = [r for r in await of(run) if r.step_id == step]
                    if earlier:
                        path.append(max(earlier, key=lambda r: r.ledger_seq))
                index += 1
        return OriginFacts(tenant=tenant, run_id=run_id, step_id=step_id, records=tuple(path))

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

    async def overview(self, tenant: Tenant) -> OverviewFacts:
        async with self._work.transaction(tenant):
            processes = list(await self._processes.list(tenant))
            versions = {v.ref: v for v in await self._versions.list(tenant)}
            runs = list(await self._runs.list(tenant))
        summaries = []
        for process in processes:
            active = versions.get(f"{process.id}@{process.active_version}")
            summaries.append(
                ProcessSummary(
                    id=process.id,
                    name=process.name,
                    active_version=process.active_version,
                    autonomy_level=None if active is None else active.autonomy.level,
                )
            )
        return OverviewFacts(
            tenant=tenant,
            processes=tuple(summaries),
            runs=tuple(activity_of(run) for run in runs),
        )


def activity_of(run: Run) -> RunActivity:
    """A run as the overview counts it: whether it works or waits is the run component's own
    definition, `WORKING` and `WAITING`."""
    plan = {step.id: step for step in run.steps}
    return RunActivity(
        id=run.id,
        tenant=run.tenant,
        process_version=run.process_version,
        state=str(run.state),
        working=run.state in WORKING,
        waiting=run.state in WAITING,
        rehearsal=run.rehearsal,
        running=tuple(
            RunningStep(
                id=s.step_id,
                method=plan[s.step_id].method,
                exactness=plan[s.step_id].exactness,
            )
            for s in run.step_runs
            if s.state is StepState.RUNNING and s.step_id in plan
        ),
    )


def facts_of(run: Run, statuses: Mapping[str, DecisionStatus] | None = None) -> RunFacts:
    """The facts of a run as reporting reads them, with the status of each decision request a
    step raised as the decision component records it."""
    statuses = statuses or {}
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
                decisions=()
                if ran is None or ran.anchoring is None
                else tuple(
                    DecisionFacts(id=r, status=statuses[r])
                    for r in ran.anchoring.requests
                    if r in statuses
                ),
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
