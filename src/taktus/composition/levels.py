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
from typing import Any

from taktus.components.decision.domain.model import Request
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
)
from taktus.components.process.domain.model.exactness import InvalidStatement
from taktus.components.process.domain.service import exactness
from taktus.components.reporting.domain.model import (
    DecisionFacts,
    OriginFacts,
    OverviewFacts,
    PlannedStep,
    ProcessFacts,
    ProcessStepFacts,
    ProcessSummary,
    RunActivity,
    RunAtVersion,
    RunCount,
    RunFacts,
    RunningStep,
    Statement,
    StepFacts,
    TakeoverFacts,
    VersionRef,
    Wait,
)
from taktus.components.run.domain.model import WAITING, WORKING, Run, RunState, StepRun, StepState
from taktus.ports.persistence import ProvenanceStore, Queried, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import DecisionStatus, Provenance


class RepositoryLevelRecords:
    """`reporting.ports.LevelRecords` over the run's and the process's repositories."""

    def __init__(
        self,
        work: UnitOfWork,
        runs: Queried[Run],
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
            version = await self._versions.get(tenant, run.process_version)
        statuses = {r.id: r.status for r in found if r is not None}
        facts = facts_of(run, statuses)
        return facts.model_copy(update={"exactness": statement_of(version)})

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
            runs = await self._runs.having(tenant, "process_version", found.ref)
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
            exactness=statement_of(found),
        )

    async def overview(self, tenant: Tenant) -> OverviewFacts:
        async with self._work.transaction(tenant):
            processes = list(await self._processes.list(tenant))
            versions = {v.ref: v for v in await self._versions.list(tenant)}
            counted = await self._runs.count(tenant, ("process_version", "state"))
            running = await self._runs.having(tenant, "step_runs.state", str(StepState.RUNNING))
        summaries = []
        for process in processes:
            active = versions.get(f"{process.id}@{process.active_version}")
            summaries.append(
                ProcessSummary(
                    id=process.id,
                    name=process.name,
                    active_version=process.active_version,
                    autonomy_level=None if active is None else active.autonomy.level,
                    steps=()
                    if active is None
                    else tuple(
                        PlannedStep(
                            id=step.id,
                            method=step.method,
                            exactness=step.exactness,
                            depends_on=step.dependencies,
                        )
                        for step in active.steps
                    ),
                    exactness=statement_of(active),
                )
            )
        return OverviewFacts(
            tenant=tenant,
            processes=tuple(summaries),
            counts=counts_of(tenant, counted),
            runs=tuple(activity_of(run) for run in running),
        )


def statement_of(version: ProcessVersion | None) -> Statement | None:
    """The exactness statement of a version, generated by the process component and handed over
    as it is (UC-6.9); None without a version, or for one written before a statement could be
    generated from it."""
    if version is None:
        return None
    try:
        generated = exactness.statement(version.ref, version.name, version.steps)
    except (InvalidStatement, InvalidProcess):
        return None
    return Statement.model_validate(generated.as_document())


def counts_of(tenant: Tenant, counted: Mapping[tuple[Any, ...], int]) -> tuple[RunCount, ...]:
    """The runs of each process version counted by state, as the overview counts them: whether
    a state works or waits is the run component's own definition, `WORKING` and `WAITING`. A
    version whose runs have all ended counts zero of each (ADR-0067 §2, ADR-0094)."""
    working: dict[str, int] = {}
    waiting: dict[str, int] = {}
    for (process_version, state), n in counted.items():
        working.setdefault(process_version, 0)
        waiting.setdefault(process_version, 0)
        if RunState(state) in WORKING:
            working[process_version] += n
        elif RunState(state) in WAITING:
            waiting[process_version] += n
    return tuple(
        RunCount(
            tenant=tenant,
            process_version=version,
            working=working[version],
            waiting=waiting[version],
        )
        for version in sorted(working)
    )


def activity_of(run: Run) -> RunActivity:
    """A run with a step running now, as the overview draws it: each running step with how it
    works, from the run's own copy of its steps."""
    plan = {step.id: step for step in run.steps}
    return RunActivity(
        id=run.id,
        tenant=run.tenant,
        process_version=run.process_version,
        state=str(run.state),
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
                takeover=None if ran is None else _takeover(ran),
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


def _takeover(ran: StepRun) -> TakeoverFacts | None:
    """The latest take-over the step was served for, as the run component reads it from the
    step run (ADR-0128)."""
    served = ran.takeovers()
    if not served:
        return None
    latest = served[-1]
    return TakeoverFacts.model_validate(
        {"id": latest.id, "standing": str(latest.standing), "until": latest.until}
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


class VersionStatements:
    """`run.ports.Statements` over the process's versions: the statement a report step carries
    by `{"$run": "exactness"}`, rendered by the process component and handed over unchanged
    (UC-6.9)."""

    def __init__(self, work: UnitOfWork, versions: Repository[ProcessVersion]) -> None:
        self._work = work
        self._versions = versions

    async def rendered(self, tenant: Tenant, process_version: str) -> str | None:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if version is None:
            return None
        try:
            return exactness.statement(version.ref, version.name, version.steps).render()
        except (InvalidStatement, InvalidProcess):
            return None
