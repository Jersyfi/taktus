"""What a repository does, the same for every implementation of the port."""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.ports.persistence import WrongTenant
from taktus.shared.v1 import Command, Plan

AGGREGATES: list[tuple[type[Any], Any]] = [
    (Process, samples.process),
    (ProcessVersion, samples.process_version),
    (Command, samples.command),
    (IntakeEvent, samples.intake_event),
    (Plan, samples.plan),
    (Run, samples.run),
    (AdapterMaturity, samples.adapter_maturity),
]


@pytest.mark.parametrize(("kind", "make"), AGGREGATES, ids=lambda x: getattr(x, "__name__", ""))
async def test_an_aggregate_round_trips_unchanged(
    backend: Backend, kind: type[Any], make: Any
) -> None:
    tenant = await backend.tenant()
    repository = backend.repository(kind)
    item = make(tenant=tenant)
    async with backend.work.transaction(tenant):
        await repository.put(tenant, item)
    async with backend.work.transaction(tenant):
        stored = await repository.get(tenant, item.id)
        assert stored == item, "every field, including the nested ones, comes back as it went"
        assert stored is not None and stored.document() == item.document()
        assert await repository.list(tenant) == [item]


async def test_a_run_comes_back_with_its_step_runs_checkpoints_and_artifacts(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    run = samples.run(tenant=tenant)
    async with backend.work.transaction(tenant):
        await runs.put(tenant, run)
    async with backend.work.transaction(tenant):
        stored = await runs.get(tenant, run.id)
    assert stored is not None
    assert [s.state for s in stored.step_runs] == [
        StepState.SUCCEEDED,
        StepState.RUNNING,
        StepState.PLANNED,
        StepState.PLANNED,
        StepState.PLANNED,
    ]
    compute = stored.step_run("compute")
    assert compute.checkpoint == run.step_run("compute").checkpoint
    assert compute.artifacts == run.step_run("compute").artifacts
    assert compute.consumption == run.step_run("compute").consumption
    assert compute.estimate == run.step_run("compute").estimate
    assert stored.step_run("prepare-commands").checkpoint is not None
    assert stored.step_run("prepare-commands").checkpoint.result_digest == samples.DIGEST
    assert stored.next_step_run() is not None and stored.next_step_run().step_id == "compute"


async def test_put_replaces_what_was_there(backend: Backend) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    run = samples.run(tenant=tenant)
    async with backend.work.transaction(tenant):
        await runs.put(tenant, run)
    # The running step finishes and the run halts: fewer artifacts on one step, a new state.
    compute = run.step_run("compute").to(StepState.STOPPED, artifacts=(), checkpoint=None)
    later = run.with_step_run(compute).to(RunState.HALTED)
    async with backend.work.transaction(tenant):
        await runs.put(tenant, later)
    async with backend.work.transaction(tenant):
        stored = await runs.get(tenant, run.id)
        assert stored == later
        assert stored is not None and stored.step_run("compute").artifacts == ()
        assert len(await runs.list(tenant)) == 1


async def test_a_missing_id_is_none(backend: Backend) -> None:
    tenant = await backend.tenant()
    async with backend.work.transaction(tenant):
        assert await backend.repository(Run).get(tenant, "run_nope") is None
        assert await backend.repository(ProcessVersion).get(tenant, "nope@1") is None
        assert await backend.repository(Plan).list(tenant) == []


async def test_a_process_version_keeps_its_step_order(backend: Backend) -> None:
    tenant = await backend.tenant()
    versions = backend.repository(ProcessVersion)
    version = samples.process_version()
    async with backend.work.transaction(tenant):
        await versions.put(tenant, version)
    async with backend.work.transaction(tenant):
        stored = await versions.get(tenant, version.id)
    assert stored is not None
    assert [s.id for s in stored.steps] == [s.id for s in version.steps]
    assert stored.ordered() == version.ordered()
    assert stored.work == version.work and stored.limits == version.limits


async def test_an_aggregate_carrying_another_tenant_is_refused(backend: Backend) -> None:
    tenant = await backend.tenant()
    runs = backend.repository(Run)
    async with backend.work.transaction(tenant):
        with pytest.raises(WrongTenant):
            await runs.put(tenant, samples.run(tenant="somebody-else"))
        assert await runs.list(tenant) == []


async def test_tenants_see_only_their_own(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    runs = backend.repository(Run)
    async with backend.work.transaction(a):
        await runs.put(a, samples.run("run_a", tenant=a))
    async with backend.work.transaction(b):
        await runs.put(b, samples.run("run_b", tenant=b))
        await runs.put(b, samples.run("run_shared_id", tenant=b))
    async with backend.work.transaction(a):
        await runs.put(a, samples.run("run_shared_id", tenant=a))
    async with backend.work.transaction(a):
        assert {r.id for r in await runs.list(a)} == {"run_a", "run_shared_id"}
        assert await runs.get(a, "run_b") is None
        shared = await runs.get(a, "run_shared_id")
        assert shared is not None and shared.tenant == a
    async with backend.work.transaction(b):
        assert {r.id for r in await runs.list(b)} == {"run_b", "run_shared_id"}
        assert await runs.get(b, "run_a") is None
