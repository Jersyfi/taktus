"""A connector, a model and a worker that answer from a recording, and the pools that offer
them (ADR-0108).

Each answers a step with the recorded answer of the same step, and only when the step sends
what the recorded step sent: the same operation, or prompt, or task, digest for digest. A step
whose answer is missing, or whose request differs, fails, with a reason that names the step and
the parts of the request that differ. Nothing is sent anywhere.

A connector call carries its step, and is matched by it. A model call and a worker's assignment
carry no step: they are matched by their request among the recorded steps of their kind, and
a request no recorded step sent fails, naming the recorded steps and where each differs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from taktus.adapters.driven.replay import requests
from taktus.adapters.driven.replay.recording import Answer, Recording, Request, Step
from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Error,
    ResolvedConnector,
    Result,
)
from taktus.ports.connector import Cause as ConnectorCause
from taktus.ports.model import Calculability, Completion, ModelError, Prompt, ResolvedModel
from taktus.ports.worker import (
    ArtifactList,
    ArtifactProduced,
    AssignmentFinished,
    AssignmentState,
    ConsumptionDeclaration,
    ConsumptionReported,
    Estimate,
    EstimateRequest,
    Event,
    HandoverRefused,
    HandoverRequest,
    Outcome,
    ResolvedWorker,
    SteeringMessage,
    SteeringRefused,
    StopRequest,
    Supports,
    Task,
    UnknownAssignment,
    WorkerError,
)
from taktus.ports.worker import Assignment as WorkerAssignment
from taktus.ports.worker import Capabilities as WorkerCapabilities
from taktus.shared.v1 import Artifact, Capability, PriceKinds

PREFIX = "replay"
"""Every reason a replay gives starts so, to tell it from the reason a real adapter gives."""


def _now() -> datetime:
    return datetime.now(UTC)


def _differs(step: Step, answer: Answer, given: Request) -> str:
    parts = requests.differing(answer.request, given)
    return f"{step.id} (in {', '.join(parts) or 'its whole request'})"


# --- connector ------------------------------------------------------------------------------


class ReplayConnector:
    """Every operation the recording names, answered by step."""

    def __init__(self, recording: Recording, directory: Path) -> None:
        self._recording = recording
        self._directory = directory
        self._calls: dict[str, int] = {}

    async def capabilities(self) -> Capabilities:
        operations = self._recording.operations
        return Capabilities(
            contract="connector/v1",
            version=None,
            capabilities=tuple(sorted({op.capability for op in operations})) or ("replay",),
            operations=operations,
            credentials=(),
            consumption=ConsumptionDeclaration(
                kinds=("quota",),  # type: ignore[arg-type]  # the enum's value
                window_seconds=3600,
                unit="request",
            ),
            permissions="passthrough",
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        step = self._recording.step(context.step_id)
        answer = None if step is None else step.answer
        if step is None or answer is None or answer.kind not in ("connector", "wait"):
            raise _refused(
                operation,
                f"{PREFIX}: the recording holds no answer of a connector for step "
                f"{context.step_id}",
            )
        if answer.operation != operation:
            raise _refused(
                operation,
                f"{PREFIX}: step {step.id} calls {operation}; the recorded step called "
                f"{answer.operation}",
            )
        given = requests.request(requests.connector(operation, input))
        if given.digest != answer.request.digest:
            raise _refused(
                operation,
                f"{PREFIX}: step {step.id} sends other input than the recorded step: "
                f"{', '.join(requests.differing(answer.request, given)) or 'the input'} differs",
            )
        calls = self._calls.get(step.id, 0)
        self._calls[step.id] = calls + 1
        if answer.kind == "wait":
            return _waited(answer, first=calls == 0)
        if answer.outcome != "succeeded" or answer.result is None:
            raise _refused(operation, f"{PREFIX}: step {step.id} failed in the recording")
        document = _json(self._directory / answer.result)
        return Result.model_validate(
            {key: document[key] for key in ("output", "effect", "consumption")}
        )


def _refused(operation: str, detail: str) -> CallFailed:
    return CallFailed(
        operation,
        Error.model_validate(
            {
                "class": "failure",
                "cause": ConnectorCause.INVALID,
                "effect": "none",
                "retryable": False,
                "detail": detail,
            }
        ),
    )


def _waited(answer: Answer, *, first: bool) -> Result:
    """A wait that ended as expected sees the first value it expected at once; a wait that did
    not sees nothing it expected, and runs to its timeout. What the recorded wait used is
    counted once."""
    output: dict[str, Any] = {}
    if answer.outcome == "succeeded" and answer.observed is not None:
        cursor = output
        parts = answer.observed.select.split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = answer.observed.value
    consumption = answer.consumption if first and answer.consumption else {"quota_units": 0}
    return Result.model_validate(
        {"output": output, "effect": {"kind": "read"}, "consumption": consumption}
    )


class ReplayConnectorPool:
    def __init__(self, recording: Recording, directory: Path) -> None:
        self._connector = ReplayConnector(recording, directory)
        self._recording = recording
        self._declaration: Capabilities | None = None

    async def resolve(self, capability: Capability) -> ResolvedConnector | None:
        if self._declaration is None:
            self._declaration = await self._connector.capabilities()
        if capability not in self._declaration.capabilities:
            return None
        adapters = [
            answer.adapter
            for _, answer in (
                *self._recording.answers("connector"),
                *self._recording.answers("wait"),
            )
            if answer.operation is not None and answer.operation.startswith(capability + ".")
        ]
        return ResolvedConnector(
            adapter=adapters[0] if adapters else f"connector.{PREFIX}",
            connector=self._connector,
            declaration=self._declaration,
        )


# --- model ----------------------------------------------------------------------------------


class ReplayModel:
    """Every model call the recording holds for one purpose, answered by its prompt."""

    def __init__(self, recording: Recording, directory: Path, purpose: str) -> None:
        self._answers = [
            (step, answer)
            for step, answer in recording.answers("model")
            if answer.purpose == purpose
        ]
        self._directory = directory

    def calculability(self) -> Calculability:
        return Calculability(
            input_count="exact", output_cap="hard", usage_kinds=("input", "output"),
            billing="per_token",
        )  # fmt: skip

    def _matching(self, prompt: Prompt) -> tuple[Step, Answer] | None:
        given = requests.request(requests.model(prompt))
        for step, answer in self._answers:
            if answer.request.digest == given.digest:
                return step, answer
        return None

    async def count(self, prompt: Prompt) -> int | None:
        found = self._matching(prompt)
        if found is not None and found[1].estimate and found[1].estimate.get("tokens_in"):
            return int(found[1].estimate["tokens_in"])
        # Unmatched, the call fails and names why; the count only lets it be admitted first.
        return len(prompt.user.split()) + len((prompt.system or "").split())

    async def complete(self, prompt: Prompt) -> Completion:
        found = self._matching(prompt)
        if found is None:
            given = requests.request(requests.model(prompt))
            recorded = "; ".join(_differs(s, a, given) for s, a in self._answers) or "none"
            raise ModelError(
                f"{PREFIX}: no recorded model step was asked this prompt; the recorded steps "
                f"of its purpose differ: {recorded}"
            )
        step, answer = found
        if answer.outcome != "succeeded" or answer.result is None:
            raise ModelError(f"{PREFIX}: step {step.id} failed in the recording")
        document = _json(self._directory / answer.result)
        used = answer.consumption or {}
        model = str(document.get("model") or answer.version or "replay")
        by_model = used.get("tokens_by_model") or {}
        kinds = by_model.get(model)
        return Completion(
            text=str(document["text"]),
            model=model,
            tokens_in=int(used.get("tokens_in") or 0),
            tokens_out=int(used.get("tokens_out") or 0),
            by_kind=None if kinds is None else PriceKinds.model_validate(kinds),
            finish="stop",
        )


class ReplayModelPool:
    def __init__(self, recording: Recording, directory: Path) -> None:
        self._recording = recording
        self._directory = directory

    async def resolve(self, purpose: str) -> ResolvedModel | None:
        for _, answer in self._recording.answers("model"):
            if answer.purpose == purpose:
                return ResolvedModel(
                    adapter=answer.adapter,
                    model=ReplayModel(self._recording, self._directory, purpose),
                    version=answer.version,
                    location="own",
                )
        return None

    async def chain(self, purpose: str) -> list[ResolvedModel]:
        """The recorded model alone: a replay answers from its recording, which leaves the
        instance for no location (ADR-0116, where the promise ends)."""
        resolved = await self.resolve(purpose)
        return [] if resolved is None else [resolved]


# --- worker ---------------------------------------------------------------------------------


class ReplayWorker:
    """Every worker step the recording holds, answered by its task: the recorded estimate,
    then the recorded consumption, artifacts and outcome as the worker's stream."""

    def __init__(self, recording: Recording, directory: Path) -> None:
        self._answers = recording.answers("worker")
        self._directory = directory
        self._assigned: dict[str, tuple[Step, Answer]] = {}

    def _matching(self, task: Task) -> tuple[Step, Answer]:
        given = requests.request(requests.worker(task))
        for step, answer in self._answers:
            if answer.request.digest == given.digest:
                return step, answer
        recorded = "; ".join(_differs(s, a, given) for s, a in self._answers) or "none"
        raise WorkerError(
            f"{PREFIX}: no recorded worker step was given this task; the recorded worker steps "
            f"differ: {recorded}"
        )

    async def capabilities(self) -> WorkerCapabilities:
        served = sorted({c for _, answer in self._answers for c in answer.capabilities})
        kinds: list[str] = []
        currencies: set[str] = set()
        classes: set[str] = set()
        for _, answer in self._answers:
            estimate = answer.estimate or {}
            if estimate.get("currency"):
                currencies |= set(estimate["currency"])
            if estimate.get("resource_class"):
                classes.add(str(estimate["resource_class"]))
        if currencies:
            kinds.append("currency")
        if classes:
            kinds.append("compute")
        declaration: dict[str, Any] = {"kinds": kinds or ["quota"]}
        if currencies:
            declaration["currencies"] = sorted(currencies)
        if classes:
            declaration["resource_classes"] = sorted(classes)
        if not kinds:
            declaration.update(window_seconds=3600, unit="step")
        return WorkerCapabilities.model_validate(
            {
                "contract": "worker/v1",
                "capabilities": served or [PREFIX],
                "consumption": declaration,
                "supports": Supports(
                    native_pause=False,
                    step_boundary_signal=True,
                    streaming_events=True,
                    estimate=True,
                ).document(),
                "max_concurrent_assignments": 1,
            }
        )

    async def estimate(self, request: EstimateRequest) -> Estimate:
        step, answer = self._matching(request.task)
        recorded = dict(answer.estimate or {})
        if not recorded:
            raise WorkerError(f"{PREFIX}: step {step.id} was never estimated in the recording")
        return Estimate.model_validate(
            {**recorded, "confidence": "medium", "wall_seconds": 0, "steps": 1}
        )

    async def assign(self, assignment: WorkerAssignment) -> AssignmentState:
        self._assigned[assignment.assignment_id] = self._matching(assignment.task)
        return AssignmentState(
            assignment_id=assignment.assignment_id,
            status="accepted",
            last_seq=0,
            accepted_at=_now(),
        )

    def _held(self, assignment_id: str) -> tuple[Step, Answer]:
        held = self._assigned.get(assignment_id)
        if held is None:
            raise UnknownAssignment(f"{PREFIX}: no assignment {assignment_id}")
        return held

    async def events(self, assignment_id: str, *, after: int = 0) -> AsyncIterator[Event]:
        step, answer = self._held(assignment_id)
        events: list[Event] = []
        seq = 0

        def base(kind: str) -> dict[str, Any]:
            nonlocal seq
            seq += 1
            return {"assignment_id": assignment_id, "seq": seq, "ts": _now(), "type": kind}

        if answer.consumption:
            events.append(
                ConsumptionReported.model_validate(
                    {**base("consumption.reported"), "step_id": "s1", **answer.consumption}
                )
            )
        for artifact in answer.artifacts:
            content = (self._directory / artifact.file).read_bytes()
            events.append(
                ArtifactProduced.model_validate(
                    {
                        **base("artifact.produced"),
                        "artifact_id": artifact.id,
                        "kind": artifact.kind,
                        "digest": _bytes_digest(content),
                        "media_type": artifact.media_type,
                        "size_bytes": len(content),
                    }
                )
            )
        finished: dict[str, Any] = {**base("assignment.finished"), "outcome": answer.outcome}
        if answer.outcome == "failed":
            finished["reason"] = f"{PREFIX}: step {step.id} failed in the recording"
        if answer.outcome == "stopped":
            finished["checkpoint_ref"] = f"{PREFIX}/{step.id}"
        events.append(AssignmentFinished.model_validate(finished))
        for event in events:
            if event.seq > after:
                yield event

    async def state(self, assignment_id: str) -> AssignmentState:
        _, answer = self._held(assignment_id)
        return AssignmentState(
            assignment_id=assignment_id,
            status="finished",
            outcome=Outcome(answer.outcome),
            last_seq=0,
            finished_at=_now(),
        )

    async def stop(self, assignment_id: str, request: StopRequest) -> AssignmentState:
        return await self.state(assignment_id)

    async def steer(self, assignment_id: str, message: SteeringMessage) -> AssignmentState:
        raise SteeringRefused(f"{PREFIX}: a recording answers as it was recorded, unsteered")

    async def hand_over(self, assignment_id: str, request: HandoverRequest) -> AssignmentState:
        raise HandoverRefused(f"{PREFIX}: a recording hands nothing over")

    async def artifacts(self, assignment_id: str) -> ArtifactList:
        _, answer = self._held(assignment_id)
        return ArtifactList(
            assignment_id=assignment_id,
            artifacts=tuple(
                Artifact(
                    id=a.id,
                    kind=a.kind,
                    digest=_bytes_digest((self._directory / a.file).read_bytes()),
                    media_type=a.media_type,
                )
                for a in answer.artifacts
            ),
        )

    async def artifact_bytes(self, assignment_id: str, artifact: Artifact) -> bytes:
        _, answer = self._held(assignment_id)
        for recorded in answer.artifacts:
            if recorded.id == artifact.id:
                return (self._directory / recorded.file).read_bytes()
        raise WorkerError(f"{PREFIX}: no artifact {artifact.id} in the recording")


def _bytes_digest(content: bytes) -> str:
    """The digest of bytes as the object store names them."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


class ReplayWorkerPool:
    def __init__(self, recording: Recording, directory: Path) -> None:
        self._recording = recording
        self._worker = ReplayWorker(recording, directory)

    async def resolve(self, required: Sequence[Capability]) -> ResolvedWorker | None:
        for _, answer in self._recording.answers("worker"):
            if set(required) <= set(answer.capabilities):
                return ResolvedWorker(
                    adapter=answer.adapter, worker=self._worker, version=answer.version
                )
        return None


# --- the pools ------------------------------------------------------------------------------


class ReplayPools:
    """The three pools a replay offers the engine (`components/run/ports/replay.py`)."""

    def __init__(self, recording: Recording, directory: Path) -> None:
        self._workers = ReplayWorkerPool(recording, directory)
        self._connectors = ReplayConnectorPool(recording, directory)
        self._models = ReplayModelPool(recording, directory)

    @property
    def workers(self) -> ReplayWorkerPool:
        return self._workers

    @property
    def connectors(self) -> ReplayConnectorPool:
        return self._connectors

    @property
    def models(self) -> ReplayModelPool:
        return self._models


def _json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} holds no result document")
    return document
