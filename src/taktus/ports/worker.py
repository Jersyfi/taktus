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
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from taktus.shared.v1 import (
    Artifact,
    AutonomyLevel,
    Capability,
    ConsumptionQuantities,
    CurrencyAmounts,
    Digest,
    ResourceClass,
    Value,
)

type AssignmentId = Annotated[str, StringConstraints(pattern=r"^asg_[A-Za-z0-9_-]{4,}$")]
type WorkerStepId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
type CheckpointRef = Annotated[str, StringConstraints(min_length=1)]
type Host = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?$",
        max_length=253,
    ),
]
"""A host the frame allows: a lowercase host name or an IPv4 address, optionally with a port.
No wildcard — least privilege names what is allowed."""


class ConsumptionKind(StrEnum):
    CURRENCY = "currency"
    QUOTA = "quota"
    COMPUTE = "compute"


type LimitKind = Literal["currency", "quota", "compute", "tokens"]
"""The kind of one ceiling in `limits`: the consumption kinds, and tokens. An assignment halted
by a running total names it (W-14)."""


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    REJECTED = "rejected"


type EventType = Literal[
    "reach.stated",
    "step.started",
    "step.progress",
    "tool.called",
    "decision.made",
    "consumption.reported",
    "step.boundary",
    "artifact.produced",
    "message.received",
    "model.called",
    "assignment.finished",
]

type MessageId = Annotated[str, StringConstraints(pattern=r"^msg_[A-Za-z0-9_-]{4,}$")]
"""A steering message's identifier, chosen by the control plane: a message posted again under
it is received once (W-19)."""


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
    steering: bool | None = None
    """The worker receives a message to a running assignment at its next boundary (W-19).
    Absent means it does not (ADR-0139 §3)."""
    handover: bool | None = None
    """The worker hands an assignment over at its next boundary, as a document another worker
    or a person continues from (W-20). Absent means it does not (ADR-0139 §4)."""
    step_boundary_signal: Literal[True]
    streaming_events: Literal[True]
    estimate: Literal[True]


type DataLocation = Literal["own", "eu", "elsewhere"]
"""Where a worker keeps what an assignment sends it, as its operator declares it: the
organisation's own infrastructure, inside the European Union, or anywhere else — the locations
of a model (ADR-0116 §2, ADR-0157)."""


class Capabilities(Value):
    contract: Literal["worker/v1"]
    version: str | None = Field(default=None, min_length=1)
    data_location: Literal["own", "eu", "elsewhere"] | None = None
    """Where the worker stores what it is sent. None — declared by nobody — counts as
    `elsewhere`: outside every residency rule narrower than `anywhere` (ADR-0157 §1)."""
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    consumption: ConsumptionDeclaration
    supports: Supports
    max_concurrent_assignments: int = Field(ge=1)
    estimator: Estimator | None = None
    """How the worker's estimate follows from an assignment without asking the worker, where it
    declares one. A launched worker is estimated by it alone, so that no unit starts before
    admission (ADR-0115); a worker reached by endpoint is still asked."""


class Health(Value):
    status: Literal["ready", "not_ready"]
    detail: str | None = None


# --- the assignment -----------------------------------------------------------------------------


class AfterCommand(Value):
    """A command the worker runs in its workspace once the work is done. Its standard output
    becomes the artifact `artifact` names, byte for byte; an exit status other than 0 fails the
    assignment (contracts/worker/v1 §3, W-18). A program and its arguments, run without a shell,
    given no credential."""

    command: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = Field(min_length=1)
    artifact: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")


class BeforeCommand(Value):
    """A command the worker runs in its prepared workspace before the work starts, as the
    assignment's first step. What it writes to its standard output and error output becomes the
    artifact `artifact` names, whether it succeeds or not; an exit status other than 0 fails the
    assignment before the work starts (contracts/worker/v1 §3, W-18, ADR-0100). A program and
    its arguments, run without a shell, given no credential; it reaches the frame's hosts."""

    command: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = Field(min_length=1)
    artifact: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")


class Task(Value):
    goal: str = Field(min_length=1)
    acceptance: tuple[Annotated[str, StringConstraints(min_length=1)], ...] = Field(min_length=1)
    # The inputs' shape belongs to the task; the contract says `type: object` and no more.
    inputs: dict[str, Any] | None = None
    before: BeforeCommand | None = None
    after: AfterCommand | None = None


class Workspace(Value):
    kind: Literal["git", "directory", "none"]
    ref: str | None = None
    location: str | None = None


class HandoverStep(Value):
    """One step of the worker's own plan that was done when the assignment was handed over."""

    step_id: WorkerStepId
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    summary: str = Field(min_length=1)


class Handover(Value):
    """An assignment handed over at a boundary, as a document that stands on its own: what a
    person needs to continue the work — the summary, the steps done, the artifacts so far —
    and `resume`, the worker's own, from which a worker of the same kind continues anywhere
    (ADR-0139 §4, W-20). It is the content of a `handover.state` artifact."""

    contract: Literal["worker/v1"]
    assignment_id: AssignmentId
    checkpoint_ref: CheckpointRef
    task: Task
    summary: str = Field(min_length=1)
    steps: tuple[HandoverStep, ...]
    artifacts: tuple[Artifact, ...]
    messages: tuple[MessageId, ...] | None = None
    resume: dict[str, Any]

    @model_validator(mode="after")
    def _unique(self) -> Handover:
        if self.messages is not None and len(set(self.messages)) != len(self.messages):
            raise ValueError("messages lists a message twice")
        return self


class Context(Value):
    workspace: Workspace | None = None
    documents: tuple[Artifact, ...] | None = None
    checkpoint_ref: CheckpointRef | None = None
    handover: Handover | None = None
    """The document of a handover this assignment continues; never with `checkpoint_ref`."""

    @model_validator(mode="after")
    def _one_way_to_continue(self) -> Context:
        if self.checkpoint_ref is not None and self.handover is not None:
            raise ValueError("an assignment continues from a checkpoint or a handover, not both")
        return self


class Frame(Value):
    """Two affirmative lists: the tools the worker may use and the hosts it may reach. Nothing
    is forbidden by pattern; everything outside the lists is refused. An empty `allowed_hosts`
    is the default and means no outbound access at all."""

    autonomy_level: AutonomyLevel
    allowed_tools: tuple[Capability, ...] = Field(min_length=1)
    allowed_hosts: tuple[Host, ...] = ()
    max_steps: int = Field(ge=1)
    deadline: datetime | None = None

    @model_validator(mode="after")
    def _unique(self) -> Frame:
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("allowed_tools lists a tool twice")
        if len(set(self.allowed_hosts)) != len(self.allowed_hosts):
            raise ValueError("allowed_hosts lists a host twice")
        return self


class QuotaLimit(Value):
    units: float = Field(gt=0)


class ComputeLimit(Value):
    seconds: float = Field(gt=0)
    resource_class: ResourceClass


class TokenLimit(Value):
    """Language-model tokens, input and output apart — the quantities `tokens_in` and
    `tokens_out` of a consumption report, named `in` and `out` on the wire. At least one."""

    tokens_in: int | None = Field(default=None, ge=1, alias="in")
    tokens_out: int | None = Field(default=None, ge=1, alias="out")

    @model_validator(mode="after")
    def _at_least_one(self) -> TokenLimit:
        if self.tokens_in is None and self.tokens_out is None:
            raise ValueError("a token limit names in, out or both")
        return self

    @classmethod
    def of(cls, tokens_in: int | None, tokens_out: int | None) -> TokenLimit:
        """By the Python names, whatever the wire calls them."""
        return cls.model_validate({"in": tokens_in, "out": tokens_out})


class Limits(Value):
    """What an assignment may consume, per consumption kind; at least one kind. The worker's
    hard ceiling: checked against the estimate before the first step (W-10), and against the
    running total before every further step (W-14)."""

    currency: CurrencyAmounts | None = None
    quota: QuotaLimit | None = None
    compute: ComputeLimit | None = None
    tokens: TokenLimit | None = None

    @model_validator(mode="after")
    def _at_least_one_kind(self) -> Limits:
        if all(k is None for k in (self.currency, self.quota, self.compute, self.tokens)):
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


class FixedEstimator(Value):
    """Every assignment is estimated the same: `estimate`."""

    kind: Literal["fixed"]
    estimate: Estimate

    def of(self, request: EstimateRequest) -> Estimate:
        return self.estimate


class PerItemEstimator(Value):
    """An assignment is estimated by the items of one list in its task's inputs: `each` once
    for every item of `task.inputs[input]`, and `otherwise` where the task carries no such
    list or an empty one."""

    kind: Literal["per_item"]
    input: str = Field(min_length=1)
    each: Estimate
    otherwise: Estimate

    def of(self, request: EstimateRequest) -> Estimate:
        items = (request.task.inputs or {}).get(self.input)
        if not isinstance(items, list) or not items:
            return self.otherwise
        return Estimate.model_validate(_times(self.each.model_dump(exclude_none=True), len(items)))


type Estimator = Annotated[FixedEstimator | PerItemEstimator, Field(discriminator="kind")]
"""What a worker declares in its capabilities so that its estimate can be had without it
(contracts/worker/v1 §2, ADR-0115). The engine calibrates what it yields from the ledger, as it
calibrates an answer of `POST /v1/estimate` (ADR-0005)."""


def _times(value: Any, n: int) -> Any:
    """Every quantity of a dumped estimate `n` times; names, classes and the confidence as
    they are."""
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return value * n
    if isinstance(value, dict):
        return {key: _times(item, n) for key, item in value.items()}
    return value


Capabilities.model_rebuild()


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


class HandoverRequest(Value):
    """A handover takes effect at the next boundary, as a stop does (W-20)."""

    reason: str | None = None
    ceiling_seconds: int | None = Field(default=None, ge=1)


class SteeringMessage(Value):
    """A message to a running assignment: received at the worker's next boundary, an input of
    the steps after it, never a change of the frame or the limits (ADR-0139 §3, W-19)."""

    message_id: MessageId
    text: str = Field(min_length=1, max_length=8000)


type RelayedHeader = Literal["Accept", "Content-Type", "Last-Event-ID"]


class RelayRequest(Value):
    """One request of the contract as a host hands it to a worker connected over the outbound
    binding; the worker answers it exactly once (contracts/worker/v1 §8, W-21)."""

    request_id: str = Field(pattern=r"^rly_[A-Za-z0-9_-]{4,}$")
    method: Literal["GET", "POST"]
    path: str = Field(pattern=r"^/v1/")
    headers: dict[RelayedHeader, str] | None = None
    body: str | None = None


class ArtifactList(Value):
    assignment_id: AssignmentId
    artifacts: tuple[Artifact, ...]


# --- events ---------------------------------------------------------------------------------------


class EventBase(Value):
    assignment_id: AssignmentId
    seq: int = Field(ge=1)
    ts: datetime
    type: EventType


class ReachStated(EventBase):
    """What the worker put within reach of the assignment's work, stated once before the first
    step: every capability a call can be made under, and, where the worker bounds them in
    advance, every host a call can name. Optional; a call outside it makes it false (ADR-0098).
    """

    type: Literal["reach.stated"]
    tools: tuple[Capability, ...]
    hosts: tuple[Host, ...] | None = None

    @model_validator(mode="after")
    def _unique(self) -> ReachStated:
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("tools lists a capability twice")
        if self.hosts is not None and len(set(self.hosts)) != len(self.hosts):
            raise ValueError("hosts lists a host twice")
        return self


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
    host: Host | None = None
    refused: bool | None = None
    reason: str | None = None
    effect: Literal["local", "outward"] | None = None
    """What the call acts on, where the worker says so: `local` changes nothing outside the
    assignment's workspace, `outward` changes something outside it (ADR-0139 §5). Absent says
    nothing."""


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


class MessageReceived(EventBase):
    """A steering message received at a boundary, once; the steps after it have it (W-19)."""

    type: Literal["message.received"]
    step_id: WorkerStepId | None = None
    message_id: MessageId


class ModelCalled(EventBase):
    """An answer of a language model the worker received inside a step (ADR-0139 §5)."""

    type: Literal["model.called"]
    step_id: WorkerStepId


class AssignmentFinished(EventBase):
    type: Literal["assignment.finished"]
    outcome: Outcome
    checkpoint_ref: CheckpointRef | None = None
    limit: LimitKind | None = None
    """The ceiling whose running total halted the assignment; absent for a requested stop."""
    reason: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    handover: str | None = Field(default=None, min_length=1)
    """The `handover.state` artifact of an assignment handed over (W-20)."""

    @model_validator(mode="after")
    def _outcome_brings_its_detail(self) -> AssignmentFinished:
        if self.outcome is Outcome.STOPPED and self.checkpoint_ref is None:
            raise ValueError("a stopped assignment names the checkpoint to resume from")
        if self.limit is not None and self.outcome is not Outcome.STOPPED:
            raise ValueError("only a stopped assignment names the limit that halted it")
        if self.handover is not None and self.outcome is not Outcome.STOPPED:
            raise ValueError("only a stopped assignment names a handover")
        if self.outcome in (Outcome.FAILED, Outcome.REJECTED) and self.reason is None:
            raise ValueError(f"a {self.outcome} assignment gives a reason")
        return self


type Event = Annotated[
    ReachStated
    | StepStarted
    | StepProgress
    | ToolCalled
    | DecisionMade
    | ConsumptionReported
    | StepBoundary
    | ArtifactProduced
    | MessageReceived
    | ModelCalled
    | AssignmentFinished,
    Field(discriminator="type"),
]

EVENT: TypeAdapter[Event] = TypeAdapter(Event)


# --- the port -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedWorker:
    """A configured worker, as the run receives it from its pool: the worker, the identifier
    of its adapter configuration — what the ledger and the provenance record carry, never a
    product name — and the version the worker declares for itself, where it declares one."""

    adapter: str
    worker: Worker
    version: str | None = None
    location: DataLocation = "elsewhere"
    """Where the worker declares it stores; `elsewhere` where it declares nothing (ADR-0157)."""


class WorkerError(Exception):
    """The worker could not be used as the contract says: unreachable, an answer that does not
    validate, a stream that broke off. The message names what happened, never a secret."""


class WorkerAtCapacity(WorkerError):
    """The worker holds as many assignments as it declares (`max_concurrent_assignments`) and
    did not take this one: the contract's 503 on `POST /v1/assignments`. Nothing started, so the
    same work may be handed over again later. The worker is the one party that sees every
    assignment it holds, from every runner and every instance, so its answer is what decides
    whether there is a free place (ADR-0037)."""


class NoEstimator(WorkerError):
    """The worker declares no estimator, and asking it would start a unit before admission: a
    launched worker is not started to be asked (ADR-0115). The step has no estimate, and a step
    without one is refused (ADR-0005, third amendment)."""


class UnknownAssignment(WorkerError):
    """The worker holds no assignment of this id: the contract's 404. Asked about an assignment
    the run handed over, it means the assignment never reached the worker, or the worker no
    longer keeps it (ADR-0038)."""


class AssignmentExists(WorkerError):
    """The worker already holds an assignment of this id and did not take this one: the
    contract's 409 on `POST /v1/assignments`. An assignment's id is the run's record of one
    handover, so the worker's answer is what keeps two runners from both handing it over
    (ADR-0038)."""


class SteeringRefused(WorkerError):
    """The worker took no message: it declares no steering, or the assignment had finished.
    Nothing reached the work (W-19)."""


class HandoverRefused(WorkerError):
    """The worker hands nothing over: it declares no handover. The assignment runs on (W-20)."""


class UnaskedWorker(WorkerError):
    """A configured worker could not be asked what it offers, so its pool could not tell
    whether it serves a step: its endpoint did not answer, or its execution unit did not start.
    It names the worker's adapter configuration and keeps what went wrong as `cause`; a cause
    of WorkerAtCapacity is a platform without room for the unit that would answer (#589)."""

    def __init__(self, adapter: str, cause: WorkerError) -> None:
        super().__init__(f"the worker {adapter} could not be asked what it offers: {cause}")
        self.adapter = adapter
        self.cause = cause


class Worker(Protocol):
    """One execution unit behind the worker contract, as the core uses it."""

    async def capabilities(self) -> Capabilities: ...

    async def estimate(self, request: EstimateRequest) -> Estimate: ...

    async def assign(self, assignment: Assignment) -> AssignmentState:
        """Hand over an assignment. A rejection is a state, not an error: the state comes back
        finished with outcome rejected, and the stream carries one event. A worker at its
        declared capacity raises WorkerAtCapacity; nothing was recorded. A worker that already
        holds an assignment of this id raises AssignmentExists; it took nothing new."""
        ...

    def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        """The event stream from `after` onwards, until assignment.finished."""
        ...

    async def state(self, assignment_id: AssignmentId) -> AssignmentState:
        """The assignment's state; UnknownAssignment when the worker holds none of this id."""
        ...

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        """Request a stop at the next step boundary."""
        ...

    async def steer(self, assignment_id: AssignmentId, message: SteeringMessage) -> AssignmentState:
        """Send a message, received at the next step boundary. A worker that does not declare
        `supports.steering` refuses it: SteeringRefused (W-19)."""
        ...

    async def hand_over(
        self, assignment_id: AssignmentId, request: HandoverRequest
    ) -> AssignmentState:
        """Request a handover at the next step boundary: a stop that leaves a `handover.state`
        artifact. A worker that does not declare `supports.handover` refuses it:
        HandoverRefused (W-20)."""
        ...

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList: ...

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes: ...
