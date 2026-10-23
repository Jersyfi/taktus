"""What a launched worker asks the execution port for: the hosts of each job (ADR-0089).

A fake execution adapter records every job request and starts nothing, so that each call ends
in a `WorkerError` after its request was made. An assignment's job reaches the frame's hosts and
the worker's service hosts; the probe that answers the capabilities reaches none of them, and an
estimate starts no unit at all (ADR-0115)."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.launched import LaunchedWorker, _Running
from taktus.ports.execution import (
    ExecutionAtCapacity,
    ExecutionRefused,
    ExecutionUnit,
    Isolation,
    Job,
    JobExit,
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
    NoEstimator,
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

    async def close(self) -> None:
        pass

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


ESTIMATOR = {
    "kind": "per_item",
    "input": "commands",
    "each": {
        "confidence": "low",
        "compute_seconds": 0.5,
        "resource_class": "cpu.small",
        "wall_seconds": 1,
        "steps": 1,
    },
    "otherwise": {
        "confidence": "low",
        "compute_seconds": 3.0,
        "resource_class": "cpu.small",
        "wall_seconds": 4,
        "steps": 4,
    },
}


def capabilities(estimator: dict[str, Any] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract": "worker/v1",
        "capabilities": ["shell.script"],
        "consumption": {"kinds": ["compute"], "resource_classes": ["cpu.small"]},
        "supports": {
            "native_pause": False,
            "step_boundary_signal": True,
            "streaming_events": True,
            "estimate": True,
        },
        "max_concurrent_assignments": 1,
    }
    if estimator is not None:
        body["estimator"] = estimator
    return body


@dataclass
class _Job:
    id: str
    endpoint: str

    async def exit(self) -> JobExit | None:
        return None


class ServingExecution(RecordingExecution):
    """Every unit it starts is one small server that answers the capabilities."""

    def __init__(self, endpoint: str) -> None:
        super().__init__()
        self.endpoint = endpoint

    def launch(self, request: JobRequest) -> AbstractAsyncContextManager[Job]:
        self.requests.append(request)
        return self._serving(request)

    @asynccontextmanager
    async def _serving(self, request: JobRequest) -> AsyncIterator[Job]:
        yield _Job(request.job_id, self.endpoint)


@asynccontextmanager
async def serving(body: dict[str, Any]) -> AsyncIterator[ServingExecution]:
    payload = json.dumps(body).encode()

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
            + f"Content-Length: {len(payload)}\r\n\r\n".encode()
            + payload
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield ServingExecution(f"http://127.0.0.1:{port}")


def assignment(hosts: tuple[str, ...], *, commands: list[str] | None = None) -> Assignment:
    return Assignment(
        assignment_id="asg_hosts01",
        task=Task(
            goal="change the code",
            acceptance=["done"],
            inputs=None if commands is None else {"commands": commands},
        ),
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
    assert [r.allowed_hosts for r in execution.requests] == [()]
    assert [r.credentials for r in execution.requests] == [()]


async def test_the_estimate_starts_no_unit_and_is_what_the_declared_estimator_yields() -> None:
    """ADR-0115: one probe answers the capabilities, once; every estimate after it is the
    declared estimator's, and no unit starts for it."""
    async with serving(capabilities(ESTIMATOR)) as execution:
        async with LaunchedWorker(execution, UNIT) as worker:
            await worker.capabilities()
            few = await worker.estimate(assignment((), commands=["a", "b"]).estimate_request())
            none = await worker.estimate(assignment(()).estimate_request())
    assert len(execution.requests) == 1, "the capabilities' probe and nothing else"
    assert execution.requests[0].job_id == "probe-capabilities"
    assert few.compute_seconds == 1.0 and few.steps == 2 and few.wall_seconds == 2
    assert none.compute_seconds == 3.0 and none.steps == 4


async def test_a_worker_that_declares_no_estimator_is_not_started_to_be_asked() -> None:
    async with serving(capabilities(None)) as execution:
        async with LaunchedWorker(execution, UNIT) as worker:
            with pytest.raises(NoEstimator, match="declares no estimator"):
                await worker.estimate(assignment(()).estimate_request())
    assert [r.job_id for r in execution.requests] == ["probe-capabilities"]


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


# --- a fetch cut by the unit's own end (#587) ---------------------------------------------------


@dataclass
class _EndedJob:
    id: str
    endpoint: str
    ended: JobExit | None

    async def exit(self) -> JobExit | None:
        return self.ended


def _unreachable() -> str:
    """An endpoint nothing listens at: every fetch from it fails to connect."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def _fetch_artifact() -> Any:
    from taktus.shared.v1 import Artifact

    return Artifact(
        id="output-1",
        kind="file",
        digest="sha256:" + "0" * 64,
        media_type="text/plain",
        size_bytes=1,
        created_at="2026-10-23T10:00:00Z",
    )


async def _fetch_from_unit_that(ended: JobExit | None) -> tuple[WorkerError, WorkerError]:
    endpoint = _unreachable()
    job = _EndedJob("asg_fetch01", endpoint, ended)
    http = HttpWorker(endpoint)
    async with LaunchedWorker(RecordingExecution(), UNIT) as worker:
        worker._running["asg_fetch01"] = _Running(_NoContext(), job, http)  # type: ignore[arg-type]
        with pytest.raises(WorkerError) as raised:
            await worker.artifact_bytes("asg_fetch01", _fetch_artifact())
        with pytest.raises(WorkerError) as listed:
            await worker.artifacts("asg_fetch01")
        return raised.value, listed.value


class _NoContext:
    async def __aexit__(self, *_: object) -> None:
        return None


async def test_a_fetch_cut_by_the_wall_clock_kill_names_the_kill() -> None:
    killed = JobExit(killed="wall", reason="the wall-clock limit of 6s was exceeded")
    for error in await _fetch_from_unit_that(killed):
        assert str(error) == (
            "the execution unit was killed: the wall-clock limit of 6s was exceeded"
        )


async def test_a_fetch_that_fails_while_the_unit_lives_names_the_connection_error() -> None:
    for error in await _fetch_from_unit_that(None):
        assert "ConnectError" in str(error) and "killed" not in str(error)
