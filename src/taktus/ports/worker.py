"""CONTRACT 1, the client side: how the core hands work to an execution unit.

The shapes are those of contracts/worker/v1/Worker.json, bound the same way the shared kernel is
(frozen, closed, checked against the contract's examples by tests/contract). The protocol at
the end is what the core calls; adapters/driven/workers implements it over the wire. The core
never sees a URL, a status code or a credential value.

Workers execute. They do not decide. The frame is a ceiling; the limits are checked by the
worker against its own estimate as well, but the core checks first and never posts an
assignment it cannot afford (ADR-0005).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from taktus.shared.v1 import (
    Artifact,
    AutonomyLevel,
    Capability,
    CapabilityPattern,
    ConsumptionQuantities,
    CurrencyAmounts,
    Digest,
    ResourceClass,
    Value,
)

type AssignmentId = Annotated[str, StringConstraints(pattern=r"^asg_[A-Za-z0-9_-]{4,}$")]
type WorkerStepId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
type CheckpointRef = Annotated[str, StringConstraints(min_length=1)]


class ConsumptionKind(StrEnum):
    CURRENCY = "currency"
    QUOTA = "quota"
    COMPUTE = "compute"


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    REJECTED = "rejected"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- declarations ------------------------------------------------------------------------------


class ConsumptionDeclaration(Value):
    kinds: tuple[ConsumptionKind, ...] = Field(min_length=1)
    window_seconds: int | None = Field(default=None, ge=1)
    unit: str | None = Field(default=None, min_length=1)
    resource_classes: tuple[ResourceClass, ...] | None = Field(default=None, min_length=1)
    currencies: tuple[Annotated[str, StringConstraints(pattern=r"^[a-z]{3}$")], ...] | None = Field(
        default=None, min_length=1
    )

    @model_validator(mode="after")
    def _each_kind_brings_its_detail(self) -> ConsumptionDeclaration:
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("kinds lists a kind twice")
        if ConsumptionKind.QUOTA in self.kinds and (
            self.window_seconds is None or self.unit is None
        ):
            raise ValueError("kind quota needs window_seconds and unit")
        if ConsumptionKind.COMPUTE in self.kinds and self.resource_classes is None:
            raise ValueError("kind compute needs resource_classes")
        if ConsumptionKind.CURRENCY in self.kinds and self.currencies is None:
            raise ValueError("kind currency needs currencies")
        return self


class Supports(Value):
    native_pause: bool
    step_boundary_signal: Literal[True]
    streaming_events: Literal[True]
    estimate: Literal[True]


class Capabilities(Value):
    contract: Literal["worker/v1"]
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    consumption: ConsumptionDeclaration
    supports: Supports
    max_concurrent_assignments: int = Field(ge=1)


class Health(Value):
    status: Literal["ready", "not_ready"]
    detail: str | None = None


# --- the assignment -----------------------------------------------------------------------------


class Task(Value):
    goal: str = Field(min_length=1)
    acceptance: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = Field(min_length=1)
    # The inputs' shape belongs to the task; the contract says `type: object` and no more.
    inputs: dict[str, Any] | None = None


class Workspace(Value):
    kind: Literal["git", "directory", "none"]
    ref: str | None = None
    location: str | None = None


class Context(Value):
    workspace: Workspace | None = None
    documents: tuple[Artifact, ...] | None = None
    checkpoint_ref: CheckpointRef | None = None


class Frame(Value):
    autonomy_level: AutonomyLevel
    allowed_tools: tuple[Capability, ...] = Field(min_length=1)
    forbidden: tuple[CapabilityPattern, ...] | None = None
    max_steps: int = Field(ge=1)
    deadline: datetime | None = None

    @model_validator(mode="after")
    def _unique(self) -> Frame:
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("allowed_tools lists a tool twice")
        if self.forbidden is not None and len(set(self.forbidden)) != len(self.forbidden):
            raise ValueError("forbidden lists a pattern twice")
        return self


class QuotaLimit(Value):
    units: float = Field(gt=0)


class ComputeLimit(Value):
    seconds: float = Field(gt=0)
    resource_class: ResourceClass


class Limits(Value):
    """What an assignment may consume, per consumption kind; at least one kind."""

    currency: CurrencyAmounts | None = None
    quota: QuotaLimit | None = None
    compute: ComputeLimit | None = None

    @model_validator(mode="after")
    def _at_least_one_kind(self) -> Limits:
        if self.currency is None and self.quota is None and self.compute is None:
            raise ValueError("limits name at least one consumption kind")
        return self


class CredentialReference(Value):
    """A secret by name only. The value never travels through the contract."""

    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    injected_as: Literal["env", "file"]
    path: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _path_only_for_files(self) -> CredentialReference:
        if (self.injected_as == "file") != (self.path is not None):
            raise ValueError("path is given exactly when the credential is injected as a file")
        return self


class Callback(Value):
    events: Literal["sse"]


class Assignment(Value):
    assignment_id: AssignmentId
    task: Task
    context: Context
    frame: Frame
    limits: Limits
    credentials: tuple[CredentialReference, ...] | None = None
    callback: Callback

    def estimate_request(self) -> EstimateRequest:
        """The same assignment without credentials and callback: an estimate needs no secret."""
        return EstimateRequest(
            assignment_id=self.assignment_id,
            task=self.task,
            context=self.context,
            frame=self.frame,
            limits=self.limits,
        )


class EstimateRequest(Value):
    assignment_id: AssignmentId | None = None
    task: Task
    context: Context
    frame: Frame
    limits: Limits | None = None


class Estimate(ConsumptionQuantities):
    """May be rough; must exist. The quantities are those the worker's consumption kinds cover."""

    confidence: Confidence
    wall_seconds: int = Field(ge=0)
    steps: int = Field(ge=0)


class AssignmentState(Value):
    assignment_id: AssignmentId
    status: Literal["accepted", "running", "stopping", "finished"]
    outcome: Outcome | None = None
    last_seq: int = Field(ge=0)
    checkpoint_ref: CheckpointRef | None = None
    reason: str | None = None
    accepted_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _finished_has_an_outcome(self) -> AssignmentState:
        finished = self.status == "finished"
        if finished and (self.outcome is None or self.finished_at is None):
            raise ValueError("a finished assignment carries its outcome and finished_at")
        if not finished and self.outcome is not None:
            raise ValueError("only a finished assignment carries an outcome")
        return self


class StopRequest(Value):
    reason: str | None = None
    ceiling_seconds: int | None = Field(default=None, ge=1)


class ArtifactList(Value):
    assignment_id: AssignmentId
    artifacts: tuple[Artifact, ...]


# --- events ---------------------------------------------------------------------------------------


class EventBase(Value):
    assignment_id: AssignmentId
    seq: int = Field(ge=1)
    ts: datetime


class StepStarted(EventBase):
    type: Literal["step.started"]
    step_id: WorkerStepId
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    summary: str


class Progress(Value):
    current: float = Field(ge=0)
    total: float = Field(gt=0)
    unit: str = Field(min_length=1)


class StepProgress(EventBase):
    type: Literal["step.progress"]
    step_id: WorkerStepId
    message: str = Field(min_length=1)
    progress: Progress | None = None


class ToolCalled(EventBase):
    type: Literal["tool.called"]
    step_id: WorkerStepId | None = None
    tool: Capability
    arguments_digest: Digest
    refused: bool | None = None
    reason: str | None = None


class DecisionMade(EventBase):
    type: Literal["decision.made"]
    step_id: WorkerStepId | None = None
    chosen: str | None = None
    rationale: str


class ConsumptionReported(EventBase, ConsumptionQuantities):
    type: Literal["consumption.reported"]
    step_id: WorkerStepId


class StepBoundary(EventBase):
    type: Literal["step.boundary"]
    step_id: WorkerStepId
    checkpoint_ref: CheckpointRef


class ArtifactProduced(EventBase):
    type: Literal["artifact.produced"]
    step_id: WorkerStepId | None = None
    artifact_id: str = Field(min_length=1)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    digest: Digest
    media_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    uri: str | None = Field(default=None, min_length=1)

    def artifact(self) -> Artifact:
        return Artifact(
            id=self.artifact_id,
            kind=self.kind,
            digest=self.digest,
            media_type=self.media_type,
            size_bytes=self.size_bytes,
            uri=self.uri,
            created_at=self.ts,
        )


class AssignmentFinished(EventBase):
    type: Literal["assignment.finished"]
    outcome: Outcome
    checkpoint_ref: CheckpointRef | None = None
    reason: str | None = Field(default=None, min_length=1)
    summary: str | None = None

    @model_validator(mode="after")
    def _outcome_brings_its_detail(self) -> AssignmentFinished:
        if self.outcome is Outcome.STOPPED and self.checkpoint_ref is None:
            raise ValueError("a stopped assignment names the checkpoint to resume from")
        if self.outcome in (Outcome.FAILED, Outcome.REJECTED) and self.reason is None:
            raise ValueError(f"a {self.outcome} assignment gives a reason")
        return self


type Event = Annotated[
    StepStarted
    | StepProgress
    | ToolCalled
    | DecisionMade
    | ConsumptionReported
    | StepBoundary
    | ArtifactProduced
    | AssignmentFinished,
    Field(discriminator="type"),
]

EVENT: TypeAdapter[Event] = TypeAdapter(Event)


# --- the port -------------------------------------------------------------------------------------


class WorkerError(Exception):
    """The worker could not be used as the contract says: unreachable, an answer that does not
    validate, a stream that broke off. The message names what happened, never a secret."""


class Worker(Protocol):
    """One execution unit behind the worker contract, as the core uses it."""

    async def capabilities(self) -> Capabilities: ...

    async def estimate(self, request: EstimateRequest) -> Estimate: ...

    async def assign(self, assignment: Assignment) -> AssignmentState:
        """Hand over an assignment. A rejection is a state, not an error: the state comes back
        finished with outcome rejected, and the stream carries one event."""
        ...

    def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        """The event stream from `after` onwards, until assignment.finished."""
        ...

    async def state(self, assignment_id: AssignmentId) -> AssignmentState: ...

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        """Request a stop at the next step boundary."""
        ...

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList: ...

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes: ...
