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

import json
from collections.abc import Mapping, Sequence
from typing import Any

from taktus.components.decision.domain.model import Request
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    TakeoverTrial,
)
from taktus.components.process.domain.model.exactness import InvalidStatement
from taktus.components.process.domain.service import exactness
from taktus.components.process.domain.service.takeover import untried
from taktus.components.reporting.domain.model import (
    DecisionFacts,
    HealFacts,
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
    StateCount,
    Statement,
    StepFacts,
    TakeoverFacts,
    VersionRef,
    Wait,
)
from taktus.components.reporting.ports.levels import OPEN_RUNS, RunPage
from taktus.components.run.domain.model import WAITING, WORKING, Run, RunState, StepRun, StepState
from taktus.components.value.application.query import CorrectionRates
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import (
    ProvenanceStore,
    Queried,
    Repository,
    Tenant,
    TenantStore,
    UnitOfWork,
)
from taktus.shared.v1 import DecisionStatus, LedgerEntry, Provenance

HEALED = "step.healed"
"""The run component's kind of a self-healing action (ADR-0160)."""
FINISHED = "step.finished"


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
        trials: Repository[TakeoverTrial] | None = None,
        tenants: TenantStore | None = None,
        rates: CorrectionRates | None = None,
        ledger: Ledger | None = None,
        objects: ObjectStore | None = None,
    ) -> None:
        self._ledger = ledger
        self._objects = objects
        """The ledger and the object store the run's heals are read from (UC-4.6). None: the
        run level shows no heal."""
        self._rates = rates
        """The value ledger's correction rates (ADR-0226). None: the statement says the rate is
        not yet measured."""
        self._trials = trials
        """The trials of takeover instructions (ADR-0180 §3). None: none is recorded, and a
        version at level 3 or 4 is untried."""
        self._work = work
        self._runs = runs
        self._processes = processes
        self._versions = versions
        self._provenance = provenance
        self._requests = requests
        self._tenants = tenants

    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            if run is None:
                return None
            raised = [r for s in run.step_runs if s.anchoring for r in s.anchoring.requests]
            found = [await self._requests.get(tenant, r) for r in raised]
            version = await self._versions.get(tenant, run.process_version)
            own: Sequence[LedgerEntry] = (
                () if self._ledger is None else await self._ledger.entries(tenant, run_id)
            )
        statuses = {r.id: r.status for r in found if r is not None}
        facts = facts_of(run, statuses, await self._heals(own))
        measured = await measured_of(self._rates, tenant, version)
        return facts.model_copy(update={"exactness": statement_of(version, measured)})

    async def _heals(self, own: Sequence[LedgerEntry]) -> dict[str, tuple[HealFacts, ...]]:
        """Every heal of the run by step, each with the failure it answered, read from the
        object store by its digest, and the outcome of the step's next `step.finished`."""
        if self._objects is None:
            return {}
        heals: dict[str, list[HealFacts]] = {}
        for number, entry in enumerate(own):
            if entry.kind != HEALED or entry.refs.step_id is None or entry.content_digest is None:
                continue
            stored = await self._objects.get(entry.content_digest)
            if stored is None:
                continue
            answered = json.loads(stored)
            outcome = next(
                (
                    later.outcome
                    for later in own[number + 1 :]
                    if later.kind == FINISHED and later.refs.step_id == entry.refs.step_id
                ),
                None,
            )
            heals.setdefault(entry.refs.step_id, []).append(
                HealFacts(
                    failure=str(answered.get("failure") or "a failure without a reason"),
                    action=str(answered.get("action") or entry.outcome or "retry"),
                    attempt=int(answered.get("attempt") or 1),
                    outcome=outcome,
                )
            )
        return {step: tuple(found) for step, found in heals.items()}

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
        self,
        tenant: Tenant,
        process_id: str,
        version: str | None,
        page: RunPage | None = None,
    ) -> ProcessFacts | None:
        runs: list[Run] = []
        counted: Mapping[tuple[Any, ...], int] = {}
        older: Run | None = None
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            known = [v for v in await self._versions.list(tenant) if v.process_id == process_id]
            active = None if process is None else process.active_version
            chosen = version or active
            found = next((v for v in known if v.version == chosen), None)
            if found is None:
                return None
            if page is not None:
                runs, older = await self._runs_of(tenant, found.ref, page)
                counted = await self._runs.count(
                    tenant, ("state",), where={"process_version": (found.ref,)}
                )
            trials = await self._tried(tenant)
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
                    role=step.role,
                    expertise=step.expertise
                    or (() if step.fallback is None else step.fallback.expertise or ()),
                    fallback_role=None if step.fallback is None else step.fallback.role,
                )
                for step in found.steps
            ),
            versions=tuple(
                VersionRef(version=v.version, active=v.version == active)
                for v in sorted(known, key=lambda v: v.version)
            ),
            runs=tuple(at_version(r) for r in runs),
            counts=tuple(
                StateCount(state=str(state), runs=n) for (state,), n in sorted(counted.items())
            ),
            older=None if older is None else at_version(older),
            exactness=statement_of(found, await measured_of(self._rates, tenant, found)),
            untried=untried(found.autonomy.level, trials, found.ref),
        )

    async def _runs_of(
        self, tenant: Tenant, version: str, page: RunPage
    ) -> tuple[list[Run], Run | None]:
        """The runs of the version not yet ended — on the first page only — and a page of the
        newest ended ones, with the last of them where more follow (ADR-0319 §3)."""
        of_version = {"process_version": (version,)}
        open_runs: list[Run] = []
        if page.after is None:
            open_runs = list(
                await self._runs.newest(
                    tenant, limit=OPEN_RUNS, where={**of_version, "state": NOT_ENDED}
                )
            )
        ended = list(
            await self._runs.newest(
                tenant,
                limit=page.limit + 1,
                after=page.after,
                where={**of_version, "state": ENDED},
            )
        )
        shown = ended[: page.limit]
        return open_runs + shown, shown[-1] if len(ended) > page.limit and shown else None

    async def _tried(self, tenant: Tenant) -> list[TakeoverTrial]:
        return [] if self._trials is None else list(await self._trials.list(tenant))

    async def overview(self, tenant: Tenant) -> OverviewFacts:
        async with self._work.transaction(tenant):
            processes = list(await self._processes.list(tenant))
            versions = {v.ref: v for v in await self._versions.list(tenant)}
            counted = await self._runs.count(tenant, ("process_version", "state"))
            running = await self._runs.having(tenant, "step_runs.state", str(StepState.RUNNING))
            trials = await self._tried(tenant)
            entry = None if self._tenants is None else await self._tenants.get(tenant)
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
                    exactness=statement_of(active, await measured_of(self._rates, tenant, active)),
                    untried=active is not None
                    and untried(active.autonomy.level, trials, active.ref),
                )
            )
        return OverviewFacts(
            tenant=tenant,
            tenant_name=None if entry is None else entry.name,
            processes=tuple(summaries),
            counts=counts_of(tenant, counted),
            runs=tuple(activity_of(run) for run in running),
        )


async def measured_of(
    rates: CorrectionRates | None, tenant: Tenant, version: ProcessVersion | None
) -> tuple[int, int] | None:
    """The value ledger's figure for a version: corrected and counted results of the steps that
    declare a check (ADR-0226). None where no value ledger is wired."""
    if rates is None or version is None:
        return None
    checked = [step.id for step in version.steps if step.checks]
    found = await rates.of(tenant, version.ref, checked)
    return (found.corrected, found.counted)


def statement_of(
    version: ProcessVersion | None, measured: tuple[int, int] | None = None
) -> Statement | None:
    """The exactness statement of a version, generated by the process component and handed over
    as it is (UC-6.9), with the value ledger's measured rate where it is given (ADR-0226); None
    without a version, or for one written before a statement could be generated from it."""
    if version is None:
        return None
    try:
        generated = exactness.statement(version.ref, version.name, version.steps, measured)
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


NOT_ENDED: tuple[str, ...] = tuple(sorted(str(s) for s in WORKING | WAITING))
"""The states of a run that has not ended, by the run component's own definitions."""
ENDED: tuple[str, ...] = tuple(sorted(str(s) for s in RunState if s not in WORKING | WAITING))
"""The states of a run that has ended."""


def at_version(run: Run) -> RunAtVersion:
    """A run as the process level draws it: its state and the steps running in it now."""
    return RunAtVersion(
        id=run.id,
        tenant=run.tenant,
        state=str(run.state),
        rehearsal=run.rehearsal,
        running=tuple(s.step_id for s in run.step_runs if s.state is StepState.RUNNING),
        created_at=run.created_at,
        ended=run.state not in WORKING | WAITING,
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


def facts_of(
    run: Run,
    statuses: Mapping[str, DecisionStatus] | None = None,
    heals: Mapping[str, tuple[HealFacts, ...]] | None = None,
) -> RunFacts:
    """The facts of a run as reporting reads them, with the status of each decision request a
    step raised as the decision component records it, and every heal of each step (UC-4.6)."""
    statuses = statuses or {}
    heals = heals or {}
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
                heals=heals.get(step.id, ()),
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

    def __init__(
        self,
        work: UnitOfWork,
        versions: Repository[ProcessVersion],
        rates: CorrectionRates | None = None,
    ) -> None:
        self._work = work
        self._versions = versions
        self._rates = rates

    async def rendered(self, tenant: Tenant, process_version: str) -> str | None:
        async with self._work.transaction(tenant):
            version = await self._versions.get(tenant, process_version)
        if version is None:
            return None
        measured = await measured_of(self._rates, tenant, version)
        try:
            return exactness.statement(version.ref, version.name, version.steps, measured).render()
        except (InvalidStatement, InvalidProcess):
            return None
