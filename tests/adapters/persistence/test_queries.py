"""The queries of a repository: newest first a page at a time, counted, found by a field
(ADR-0094, issue #310). The same answers from both implementations."""

from __future__ import annotations

from datetime import timedelta

import pytest

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.components.process.domain.model import Process
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.persistence import Mark, NotQueryable


def at(n: int, *, tenant: str, created: int, state: RunState = RunState.RUNNING) -> Run:
    run = samples.run(f"run_{n:02}", tenant=tenant)
    return run.model_copy(
        update={"created_at": samples.AT + timedelta(seconds=created), "state": state}
    )


async def stored(backend: Backend, tenant: str, *runs: Run) -> None:
    async with backend.work.transaction(tenant):
        for run in runs:
            await backend.queried(Run).put(tenant, run)


async def test_newest_pages_through_every_run_once_newest_first_ties_by_id(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    # Two runs share each moment: the order is the moment, newest first, then the id.
    runs = [at(n, tenant=tenant, created=n // 2) for n in range(7)]
    await stored(backend, tenant, *reversed(runs))
    queried = backend.queried(Run)
    seen: list[str] = []
    after: Mark | None = None
    async with backend.work.transaction(tenant):
        for _ in range(10):
            page = await queried.newest(tenant, limit=3, after=after)
            if not page:
                break
            seen.extend(r.id for r in page)
            after = Mark(created_at=page[-1].created_at, id=page[-1].id)
        everything = {r.id: r for r in await queried.list(tenant)}
        first = await queried.newest(tenant, limit=7)
    assert seen == ["run_06", "run_04", "run_05", "run_02", "run_03", "run_00", "run_01"]
    assert [r.document() for r in first] == [everything[i].document() for i in seen], (
        "a page holds the same documents as the whole list"
    )


async def test_runs_are_counted_by_fields_without_being_read(backend: Backend) -> None:
    tenant = await backend.tenant()
    await stored(
        backend,
        tenant,
        at(1, tenant=tenant, created=1),
        at(2, tenant=tenant, created=2),
        at(3, tenant=tenant, created=3, state=RunState.WAITING_HUMAN),
        at(4, tenant=tenant, created=4, state=RunState.FINISHED).model_copy(
            update={"process_version": "other@2"}
        ),
    )
    async with backend.work.transaction(tenant):
        counted = await backend.queried(Run).count(tenant, ("process_version", "state"))
    version = samples.process_version().ref
    assert dict(counted) == {
        (version, "running"): 2,
        (version, "waiting_human"): 1,
        ("other@2", "finished"): 1,
    }


async def test_runs_are_found_by_a_field_and_by_a_field_of_their_steps(backend: Backend) -> None:
    tenant = await backend.tenant()
    running = at(1, tenant=tenant, created=1)  # its second step runs
    done = at(2, tenant=tenant, created=2)
    done = done.with_step_run(
        done.step_run("compute").to(StepState.SUCCEEDED, finished_at=samples.AT)
    ).model_copy(update={"process_version": "other@2"})
    await stored(backend, tenant, running, done)
    queried = backend.queried(Run)
    async with backend.work.transaction(tenant):
        by_step = await queried.having(tenant, "step_runs.state", "running")
        by_version = await queried.having(tenant, "process_version", "other@2")
        assert await queried.having(tenant, "step_runs.state", "stopped") == []
    assert [r.id for r in by_step] == ["run_01"] and by_step[0] == running
    assert [r.id for r in by_version] == ["run_02"] and by_version[0] == done


async def test_a_field_the_storage_cannot_query_is_refused(backend: Backend) -> None:
    tenant = await backend.tenant()
    async with backend.work.transaction(tenant):
        with pytest.raises(NotQueryable):
            await backend.queried(Run).count(tenant, ("step_runs.state",))
        await backend.queried(Process).put(tenant, samples.process(tenant=tenant))
        with pytest.raises(NotQueryable):
            await backend.queried(Process).newest(tenant, limit=1)
