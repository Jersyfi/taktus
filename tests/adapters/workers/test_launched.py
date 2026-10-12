"""What a launched worker asks the execution port for: the hosts of each job (ADR-0089).

A fake execution adapter records every job request and starts nothing, so that each call ends
in a `WorkerError` after its request was made. An assignment's job reaches the frame's hosts and
the worker's service hosts; a probe — capabilities, estimate — reaches none of them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest

from taktus.adapters.driven.workers.launched import LaunchedWorker
from taktus.ports.execution import (
    ExecutionAtCapacity,
    ExecutionRefused,
    ExecutionUnit,
    Isolation,
    Job,
    JobRequest,
    ResourceLimits,
)
from taktus.ports.worker import (
    Assignment,
    Callback,
    ComputeLimit,
    Context,
    Frame,
    Limits,
    Task,
    WorkerAtCapacity,
    WorkerError,
)

UNIT = ExecutionUnit(
    name="coding",
    program="worker:1",
    limits=ResourceLimits(cpus=1, memory_bytes=256 * 1024 * 1024, wall_seconds=120),
    service_hosts=("model.example.net", "repo.example.org"),
)


class RecordingExecution:
    """Records each request and refuses it, so that nothing is started."""

    def __init__(self) -> None:
        self.requests: list[JobRequest] = []

    @property
    def isolation(self) -> Isolation:
        return Isolation.CLUSTER

    def launch(self, request: JobRequest) -> AbstractAsyncContextManager[Job]:
        self.requests.append(request)
        return self._refused()

    @asynccontextmanager
    async def _refused(self) -> AsyncIterator[Job]:
        raise ExecutionRefused("recorded, not started")
        yield  # pragma: no cover


class FullExecution(RecordingExecution):
    """A platform without room: every unit waits to be placed."""

    @asynccontextmanager
    async def _refused(self) -> AsyncIterator[Job]:
        raise ExecutionAtCapacity("not scheduled: 0/1 nodes are available: 1 Insufficient memory")
        yield  # pragma: no cover


def assignment(hosts: tuple[str, ...]) -> Assignment:
    return Assignment(
        assignment_id="asg_hosts01",
        task=Task(goal="change the code", acceptance=["done"]),
        context=Context(),
        frame=Frame(
            autonomy_level=2, allowed_tools=("shell.script",), allowed_hosts=hosts, max_steps=5
        ),
        limits=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
        callback=Callback(events="sse"),
    )


async def test_an_assignments_job_reaches_the_frames_hosts_and_the_service_hosts() -> None:
    execution = RecordingExecution()
    given = assignment(("repo.example.org",))
    async with LaunchedWorker(execution, UNIT) as worker:
        with pytest.raises(WorkerError):
            await worker.assign(given)
    (request,) = execution.requests
    assert request.allowed_hosts == ("repo.example.org", "model.example.net"), (
        "the frame's hosts first, then the service hosts, each once"
    )
    assert given.frame.allowed_hosts == ("repo.example.org",), "the frame stays the step's"


async def test_a_frame_without_hosts_still_reaches_the_service_hosts() -> None:
    execution = RecordingExecution()
    async with LaunchedWorker(execution, UNIT) as worker:
        with pytest.raises(WorkerError):
            await worker.assign(assignment(()))
    assert execution.requests[0].allowed_hosts == UNIT.service_hosts


async def test_a_probe_reaches_no_host() -> None:
    execution = RecordingExecution()
    async with LaunchedWorker(execution, UNIT) as worker:
        with pytest.raises(WorkerError):
            await worker.capabilities()
        with pytest.raises(WorkerError):
            await worker.estimate(assignment(("repo.example.org",)).estimate_request())
    assert [r.allowed_hosts for r in execution.requests] == [(), ()]
    assert [r.credentials for r in execution.requests] == [(), ()]


async def test_without_service_hosts_a_job_reaches_the_frames_hosts_alone() -> None:
    execution = RecordingExecution()
    unit = UNIT.model_copy(update={"service_hosts": ()})
    async with LaunchedWorker(execution, unit) as worker:
        with pytest.raises(WorkerError):
            await worker.assign(assignment(("repo.example.org",)))
    assert execution.requests[0].allowed_hosts == ("repo.example.org",)


async def test_a_platform_without_room_is_the_worker_at_capacity() -> None:
    """A unit the platform cannot place is a full worker, not a broken one: the step waits
    (ADR-0037 §6, #358). It holds for the probe as for the assignment."""
    execution = FullExecution()
    async with LaunchedWorker(execution, UNIT) as worker:
        with pytest.raises(WorkerAtCapacity, match="Insufficient memory"):
            await worker.estimate(assignment(()).estimate_request())
        with pytest.raises(WorkerAtCapacity, match="Insufficient memory"):
            await worker.assign(assignment(()))
