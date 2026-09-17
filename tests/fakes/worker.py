"""A worker behind the port that does what its script says, in memory.

The script is a list of inner steps; each produces artifacts, reports consumption and ends
with a boundary. A stop requested before a boundary ends the assignment `stopped` at that
boundary with a checkpoint naming the index; an assignment that resumes from such a checkpoint
continues after it and produces nothing it produced before. `reject_with` makes the worker
refuse every assignment before starting, as W-10 describes.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from taktus.ports.worker import (
    ArtifactList,
    ArtifactProduced,
    Assignment,
    AssignmentFinished,
    AssignmentId,
    AssignmentState,
    Capabilities,
    Confidence,
    ConsumptionDeclaration,
    ConsumptionReported,
    Estimate,
    EstimateRequest,
    Event,
    Outcome,
    StepBoundary,
    StepStarted,
    StopRequest,
    Supports,
    WorkerError,
)
from taktus.shared.v1 import Artifact


@dataclass(frozen=True)
class InnerStep:
    step_id: str
    compute_seconds: float = 1.0
    artifacts: tuple[tuple[str, bytes], ...] = ()


@dataclass
class FakeWorker:
    capabilities_offered: tuple[str, ...] = ("shell.script",)
    version: str | None = "0.9.0"
    script: tuple[InnerStep, ...] = (InnerStep("one", artifacts=(("out-1", b"42\n"),)),)
    estimate_seconds: float = 1.0
    resource_class: str = "cpu.small"
    reject_with: str | None = None
    fail_at: str | None = None  # the inner step at which the assignment fails
    unreachable: str | None = None  # every call fails with this WorkerError, as a dead unit does
    on_event: Callable[[Event], Awaitable[None]] | None = None
    assignments: list[Assignment] = field(default_factory=list)
    estimates: list[EstimateRequest] = field(default_factory=list)
    stops: list[tuple[str, StopRequest]] = field(default_factory=list)
    _stop_requested: set[str] = field(default_factory=set)
    _states: dict[str, AssignmentState] = field(default_factory=dict)
    _bytes: dict[str, bytes] = field(default_factory=dict)

    async def capabilities(self) -> Capabilities:
        return Capabilities(
            contract="worker/v1",
            version=self.version,
            capabilities=self.capabilities_offered,
            consumption=ConsumptionDeclaration(
                kinds=("compute",), resource_classes=(self.resource_class,)
            ),
            supports=Supports(
                native_pause=False,
                step_boundary_signal=True,
                streaming_events=True,
                estimate=True,
            ),
            max_concurrent_assignments=1,
        )

    async def estimate(self, request: EstimateRequest) -> Estimate:
        if self.unreachable is not None:
            raise WorkerError(self.unreachable)
        self.estimates.append(request)
        start = self._start_index(request.context.checkpoint_ref)
        return Estimate(
            confidence=Confidence.LOW,
            compute_seconds=self.estimate_seconds * (len(self.script) - start),
            resource_class=self.resource_class,
            wall_seconds=1,
            steps=len(self.script) - start,
        )

    async def assign(self, assignment: Assignment) -> AssignmentState:
        self.assignments.append(assignment)
        now = datetime.now(UTC)
        if self.reject_with is not None:
            state = AssignmentState(
                assignment_id=assignment.assignment_id,
                status="finished",
                outcome=Outcome.REJECTED,
                last_seq=1,
                reason=self.reject_with,
                accepted_at=now,
                finished_at=now,
            )
        else:
            state = AssignmentState(
                assignment_id=assignment.assignment_id,
                status="accepted",
                last_seq=0,
                accepted_at=now,
            )
        self._states[assignment.assignment_id] = state
        return state

    async def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        assignment = next(a for a in self.assignments if a.assignment_id == assignment_id)
        seq = 0
        ts = datetime.now(UTC)

        def base() -> dict[str, object]:
            nonlocal seq
            seq += 1
            return {"assignment_id": assignment_id, "seq": seq, "ts": ts}

        async def emit(event: Event) -> Event:
            if self.on_event is not None:
                await self.on_event(event)
            return event

        start = self._start_index(assignment.context.checkpoint_ref)
        for index in range(start, len(self.script)):
            inner = self.script[index]
            yield await emit(
                StepStarted(
                    **base(),
                    type="step.started",
                    step_id=inner.step_id,
                    kind="shell",
                    summary=inner.step_id,
                )
            )
            if self.fail_at == inner.step_id:
                yield await emit(
                    AssignmentFinished(
                        **base(),
                        type="assignment.finished",
                        outcome=Outcome.FAILED,
                        reason="failed as scripted",
                    )
                )
                return
            for artifact_id, content in inner.artifacts:
                self._bytes[artifact_id] = content
                yield await emit(
                    ArtifactProduced(
                        **base(),
                        type="artifact.produced",
                        step_id=inner.step_id,
                        artifact_id=artifact_id,
                        kind="log",
                        digest="sha256:" + hashlib.sha256(content).hexdigest(),
                        media_type="text/plain",
                        size_bytes=len(content),
                    )
                )
            yield await emit(
                ConsumptionReported(
                    **base(),
                    type="consumption.reported",
                    step_id=inner.step_id,
                    compute_seconds=inner.compute_seconds,
                    resource_class=self.resource_class,
                )
            )
            checkpoint = f"ckpt/{assignment_id}/{index}"
            yield await emit(
                StepBoundary(
                    **base(), type="step.boundary", step_id=inner.step_id, checkpoint_ref=checkpoint
                )
            )
            if assignment_id in self._stop_requested and index < len(self.script) - 1:
                yield await emit(
                    AssignmentFinished(
                        **base(),
                        type="assignment.finished",
                        outcome=Outcome.STOPPED,
                        checkpoint_ref=checkpoint,
                        reason="stop requested",
                    )
                )
                return
        yield await emit(
            AssignmentFinished(**base(), type="assignment.finished", outcome=Outcome.SUCCEEDED)
        )

    async def state(self, assignment_id: AssignmentId) -> AssignmentState:
        return self._states[assignment_id]

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        self.stops.append((assignment_id, request))
        self._stop_requested.add(assignment_id)
        return self._states[assignment_id].model_copy(update={"status": "stopping"})

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList:
        return ArtifactList(assignment_id=assignment_id, artifacts=())

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes:
        return self._bytes[artifact.id]

    def _start_index(self, checkpoint_ref: str | None) -> int:
        if checkpoint_ref is None:
            return 0
        return int(checkpoint_ref.rsplit("/", 1)[1]) + 1
