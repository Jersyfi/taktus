"""The facts the levels of a live representation read, from the run's records (ADR-0063).

`reporting` draws a level and never imports the run component (ADR-0003); this module reads a
run from the run's repository and hands its facts over in reporting's own shape. Every figure is
the run component's own: what a step recorded it used, and the run's sum, `Run.consumed`
(ADR-0029).
"""

from __future__ import annotations

from taktus.components.reporting.domain.model import RunFacts, StepFacts, Wait
from taktus.components.run.domain.model import Run, StepRun
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class RunLevelRecords:
    """`reporting.ports.LevelRecords` over the run's repository."""

    def __init__(self, work: UnitOfWork, runs: Repository[Run]) -> None:
        self._work = work
        self._runs = runs

    async def run(self, tenant: Tenant, run_id: str) -> RunFacts | None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
        return None if run is None else facts_of(run)


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
