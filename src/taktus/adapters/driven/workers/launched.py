"""A worker the control plane starts itself: the worker port over the execution port.

An endpoint worker (`http/`) is already running somewhere; a launched worker exists only while
a job does. This adapter starts one execution unit per assignment through an `Execution`
adapter — process, container, a pod — with the credentials and the autonomy level the
assignment carries, and with the hosts of the assignment's frame and those the worker's own
service needs (`reach`, ADR-0089). It talks to the unit over HTTP and SSE as to any worker, and
ends the unit when the assignment's stream has ended. The unit's checkpoints live in its state,
which the execution adapter keeps across jobs, so that a resumed assignment finds them in a new
unit.

One call needs a unit before there is an assignment: `capabilities`, which the pool asks once.
It is answered by a *probe*: a unit started at autonomy level 1 with no credential and no host,
not even the service hosts, asked, and ended. The answer is kept for the adapter's life, so
that a probe starts once.

The estimate the engine asks before every worker step starts no unit (ADR-0115). It is what the
estimator the worker declares in its capabilities yields for the request; the engine calibrates
it from the ledger as it calibrates any estimate (ADR-0005). A worker that declares no estimator
cannot be estimated without a unit before admission, and the estimate is refused with
`NoEstimator`: the step is refused for want of an estimate, and nothing started.

A unit that the execution adapter killed — memory, wall clock — is reported as a failed step
with that cause, not as a broken stream: the stream's error is replaced by the job's exit.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from taktus.adapters.driven.workers.http import HttpWorker
from taktus.ports.execution import (
    Execution,
    ExecutionAtCapacity,
    ExecutionError,
    ExecutionRefused,
    ExecutionUnit,
    Job,
    JobRequest,
    reach,
)
from taktus.ports.worker import (
    ArtifactList,
    Assignment,
    AssignmentId,
    AssignmentState,
    Capabilities,
    Estimate,
    EstimateRequest,
    Event,
    NoEstimator,
    StopRequest,
    WorkerAtCapacity,
    WorkerError,
)
from taktus.shared.v1 import Artifact, AutonomyLevel

PROBE_LEVEL: AutonomyLevel = 1


@dataclass
class _Running:
    context: AbstractAsyncContextManager[Job]
    job: Job
    worker: HttpWorker


class LaunchedWorker:
    def __init__(
        self,
        execution: Execution,
        unit: ExecutionUnit,
        *,
        idle_timeout: float = 60.0,
        stream_timeout: float = 3600.0,
    ) -> None:
        self._execution = execution
        self._unit = unit
        self._idle_timeout = idle_timeout
        self._stream_timeout = stream_timeout
        self._running: dict[str, _Running] = {}
        self._lock = asyncio.Lock()
        self._capabilities: Capabilities | None = None
        self._asked = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        for assignment_id in list(self._running):
            await self._end(assignment_id)
        await self._execution.close()

    # --- the port ---------------------------------------------------------------------------

    async def capabilities(self) -> Capabilities:
        async with self._asked:
            if self._capabilities is None:
                async with self._probe("probe-capabilities", PROBE_LEVEL) as worker:
                    self._capabilities = await worker.capabilities()
            return self._capabilities

    async def estimate(self, request: EstimateRequest) -> Estimate:
        estimator = (await self.capabilities()).estimator
        if estimator is None:
            raise NoEstimator(
                "the worker declares no estimator in its capabilities, and a launched worker "
                "is not started to be asked before admission (ADR-0115)"
            )
        return estimator.of(request)

    async def assign(self, assignment: Assignment) -> AssignmentState:
        request = JobRequest(
            job_id=assignment.assignment_id,
            unit=self._unit,
            autonomy_level=assignment.frame.autonomy_level,
            allowed_hosts=reach(self._unit, assignment.frame.allowed_hosts),
            credentials=assignment.credentials or (),
            wall_seconds=_until(assignment.frame.deadline),
        )
        running = await self._start(request)
        async with self._lock:
            self._running[assignment.assignment_id] = running
        try:
            state = await running.worker.assign(assignment)
        except WorkerError:
            await self._end(assignment.assignment_id)
            raise
        if state.status == "finished":
            # Rejected before starting: there is no stream to follow, and no unit to keep.
            await self._end(assignment.assignment_id)
        return state

    async def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        running = self._of(assignment_id)
        try:
            async for event in running.worker.events(assignment_id, after=after):
                yield event
        except WorkerError as error:
            exit = await running.job.exit()
            if exit is not None and exit.killed is not None:
                raise WorkerError(f"the execution unit was killed: {exit.reason}") from error
            if exit is not None:
                raise WorkerError(f"the execution unit ended: {exit.reason}") from error
            raise
        finally:
            await self._end(assignment_id)

    async def state(self, assignment_id: AssignmentId) -> AssignmentState:
        return await self._of(assignment_id).worker.state(assignment_id)

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        return await self._of(assignment_id).worker.stop(assignment_id, request)

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList:
        return await self._of(assignment_id).worker.artifacts(assignment_id)

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes:
        return await self._of(assignment_id).worker.artifact_bytes(assignment_id, artifact)

    # --- jobs ---------------------------------------------------------------------------------

    def _probe(self, job_id: str, level: AutonomyLevel) -> AbstractAsyncContextManager[HttpWorker]:
        return _Probe(self, JobRequest(job_id=job_id, unit=self._unit, autonomy_level=level))

    async def _start(self, request: JobRequest) -> _Running:
        context = self._execution.launch(request)
        try:
            job = await context.__aenter__()
        except ExecutionAtCapacity as error:
            # The platform is the launched worker's capacity: without room it is full, and
            # the step waits as for any worker at capacity (ADR-0037 §6).
            raise WorkerAtCapacity(f"the execution unit could not be placed: {error}") from error
        except (ExecutionRefused, ExecutionError) as error:
            raise WorkerError(f"the execution unit could not be started: {error}") from error
        worker = HttpWorker(
            job.endpoint, idle_timeout=self._idle_timeout, stream_timeout=self._stream_timeout
        )
        return _Running(context, job, worker)

    def _of(self, assignment_id: str) -> _Running:
        running = self._running.get(assignment_id)
        if running is None:
            raise WorkerError(f"no execution unit is running for assignment {assignment_id}")
        return running

    async def _end(self, assignment_id: str) -> None:
        async with self._lock:
            running = self._running.pop(assignment_id, None)
        if running is not None:
            await _close(running)


class _Probe:
    def __init__(self, owner: LaunchedWorker, request: JobRequest) -> None:
        self._owner = owner
        self._request = request
        self._running: _Running | None = None

    async def __aenter__(self) -> HttpWorker:
        self._running = await self._owner._start(self._request)
        return self._running.worker

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._running is not None:
            await _close(self._running)


async def _close(running: _Running) -> None:
    await running.worker.close()
    await running.context.__aexit__(None, None, None)


def _until(deadline: datetime | None) -> int | None:
    """Seconds until the frame's deadline, at least one; None without a deadline."""
    if deadline is None:
        return None
    now = datetime.now(UTC)
    return max(1, int((deadline - now).total_seconds()))
