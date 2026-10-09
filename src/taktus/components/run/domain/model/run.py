"""Run, step run and checkpoint, with the state machine of control-plane.md §5.2."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from taktus.components.run.domain.model.block import OpenBlock
from taktus.components.run.domain.model.errors import IllegalTransition, UnsupportedWork
from taktus.ports.worker import AssignmentId, Limits
from taktus.shared.v1 import (
    Artifact,
    AutonomyLevel,
    Consumption,
    ConsumptionQuantities,
    Digest,
    Method,
    Step,
    StepId,
    TokensByModel,
    Value,
    add_tokens_by_model,
)


class RunState(StrEnum):
    PLANNED = "planned"
    ADMITTED = "admitted"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    HALTED = "halted"
    ESCALATED = "escalated"
    FINISHED = "finished"


class Cause(StrEnum):
    """Why a run halted or escalated. Tokens, so that the ledger can carry them."""

    LIMIT = "limit"
    NO_ESTIMATE = "no_estimate"
    """A step could not be estimated and was refused, not admitted (ADR-0005)."""
    STOP = "stop"
    FAILURE = "failure"
    CEILING = "ceiling"
    CAPACITY = "capacity"
    """A step's worker was at its declared capacity, or its model's provider at its rate limit.
    A run halted with this cause waits at the step's boundary and its runner tries again later;
    one whose step waited beyond its ceiling escalates with it (ADR-0037, ADR-0043)."""
    PERSON = "person"
    """A step waits for a person: to confirm it before it starts (level 2), or to perform the act
    Taktus only proposes and report it done (level 1). The run waits in `waiting_human` once
    nothing else can run (ADR-0039)."""
    MATURITY = "maturity"
    """A step at level 3 or above would run on an adapter below *verified*, and was not run on
    it (NTC-0051, ADR-0039)."""


# Every transition the run knows. Anything not listed is illegal. `self-healed` of §5.2 is a
# running → running transition and arrives with retries. `waiting_human` is where a run waits
# once nothing runs but steps that wait for a person (ADR-0039); anchors will halt there too.
RUN_TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    {
        (RunState.PLANNED, RunState.ADMITTED),
        (RunState.ADMITTED, RunState.RUNNING),
        (RunState.RUNNING, RunState.WAITING_HUMAN),
        (RunState.WAITING_HUMAN, RunState.RUNNING),
        (RunState.WAITING_HUMAN, RunState.HALTED),  # an emergency stop while it waits
        (RunState.RUNNING, RunState.HALTED),
        (RunState.RUNNING, RunState.ESCALATED),
        (RunState.RUNNING, RunState.FINISHED),
        (RunState.HALTED, RunState.RUNNING),
        (RunState.ESCALATED, RunState.RUNNING),
    }
)

RESUMABLE: frozenset[RunState] = frozenset(
    {RunState.HALTED, RunState.ESCALATED, RunState.WAITING_HUMAN}
)
"""States a run leaves by `resume`: it stopped at a boundary and waits. A run waiting for a person
resumes into the same wait unless a step it waited for was answered (`RunEngine.confirm`)."""

INTERRUPTIBLE: frozenset[RunState] = frozenset(
    {RunState.PLANNED, RunState.ADMITTED, RunState.RUNNING}
)
"""States a run is found in when the instance executing it stopped without a chance to halt
it. Such a run is *recovered*: the step that was in flight is set back to its boundary and the
run continues from there (ADR-0013 A)."""


class StepState(StrEnum):
    PLANNED = "planned"
    REJECTED = "rejected"
    ADMITTED = "admitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    WAITING_HUMAN = "waiting_human"
    """The step waits for a person before anything of it starts: a confirmation at level 2, the
    act performed by the person at level 1 (ADR-0039). Steps that do not depend on it run on."""


STEP_TRANSITIONS: frozenset[tuple[StepState, StepState]] = frozenset(
    {
        (StepState.PLANNED, StepState.ADMITTED),
        (StepState.PLANNED, StepState.REJECTED),
        (StepState.REJECTED, StepState.ADMITTED),  # after a limit change, on resume
        (StepState.REJECTED, StepState.REJECTED),  # rejected again on resume
        (StepState.FAILED, StepState.REJECTED),  # on retry, the estimate no longer fits
        (StepState.STOPPED, StepState.REJECTED),  # on resume, the rest no longer fits
        (StepState.ADMITTED, StepState.RUNNING),
        (StepState.ADMITTED, StepState.REJECTED),  # the worker rejected what the core admitted
        (StepState.ADMITTED, StepState.STOPPED),  # the instance stopped before the step ran
        (StepState.RUNNING, StepState.SUCCEEDED),
        (StepState.RUNNING, StepState.FAILED),
        (StepState.RUNNING, StepState.STOPPED),
        (StepState.STOPPED, StepState.ADMITTED),  # resume from the checkpoint
        (StepState.FAILED, StepState.ADMITTED),  # retry from the boundary before it
        # The worker could not be reached or started — before admission (the estimate), from
        # whichever state the step is asked in, or after it (the assignment).
        (StepState.PLANNED, StepState.FAILED),
        (StepState.REJECTED, StepState.FAILED),
        (StepState.STOPPED, StepState.FAILED),
        (StepState.FAILED, StepState.FAILED),
        (StepState.ADMITTED, StepState.FAILED),
        # Adopted: the assignment an earlier attempt handed over is still the worker's, and the
        # step continues it instead of handing over another (ADR-0038).
        (StepState.STOPPED, StepState.RUNNING),
        (StepState.FAILED, StepState.RUNNING),
        (StepState.REJECTED, StepState.RUNNING),
        # A person's answer (ADR-0039): the step waits before anything of it starts; a
        # confirmation lets it start, a report that the person performed the act ends it.
        (StepState.PLANNED, StepState.WAITING_HUMAN),
        (StepState.WAITING_HUMAN, StepState.PLANNED),
        (StepState.WAITING_HUMAN, StepState.SUCCEEDED),
    }
)

DONE: frozenset[StepState] = frozenset({StepState.SUCCEEDED})

IN_FLIGHT: frozenset[StepState] = frozenset({StepState.ADMITTED, StepState.RUNNING})
"""States a step run is in while its instance is executing it."""


class Checkpoint(Value):
    """A point the run can resume from: the step's boundary, what the step had produced by
    then, and the digest of its result if it has one."""

    ref: str = Field(min_length=1)
    step_id: StepId
    taken_at: datetime
    artifact_ids: tuple[str, ...] = ()
    result_digest: Digest | None = None


class StepRun(Value):
    step_id: StepId
    index: int = Field(ge=0)
    method: Method
    state: StepState = StepState.PLANNED
    attempt: int = Field(default=1, ge=1)
    """How many times the step has been started afresh. A resume from a stop or a recovery
    after a crash continues the same attempt — and derives the same idempotency key for a
    connector call — while a retry after a failure the connector said was not retryable
    starts a new one."""
    retryable: bool | None = None
    """After a failure: whether the same call with the same key may be repeated without a
    second effect, as the connector said. None for a failure that was not a connector's."""
    adapter: str | None = None
    assignment_id: AssignmentId | None = None
    assignment_open: bool = False
    """Whether the assignment `assignment_id` names was handed to the worker and the run has
    not read its end. Set and committed before the assignment is posted, cleared when its
    `assignment.finished` or its rejection is read. An open assignment may be running in the
    worker without anyone following it, so a step never hands over another while one is open:
    it asks the worker first, and adopts it, or posts it again under the same id (ADR-0038)."""
    assignment_seq: int = Field(default=0, ge=0)
    """The `seq` of the last event of the open assignment whose effect the step run holds: the
    worker's last boundary persisted. Whoever adopts the assignment reads its stream after it."""
    estimate: ConsumptionQuantities | None = None
    """What the step was estimated to use, as the adapter or the method said."""
    reservation: ConsumptionQuantities | None = None
    """What admission debited from the budget for the step: the estimate scaled by the measured
    error of its adapter (ADR-0005). While the step runs the budget counts it as spent; when
    the step ends its actual replaces it."""
    consumption: Consumption | None = None
    artifacts: tuple[Artifact, ...] = ()
    checkpoint: Checkpoint | None = None
    reason: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    waiting_since: datetime | None = None
    """When the step's worker first answered that it was at capacity, or its model's provider
    that it was at its rate limit, in a wait that has not ended yet; None while the step is not
    waiting so (ADR-0037, ADR-0043)."""
    waits: int = Field(default=0, ge=0)
    """How many times the worker answered so in that wait: what the next delay grows with."""
    block: OpenBlock | None = None
    """The block the step is in, while it waits: its account, its cause and when it began. The
    record of the block is written when it ends (ADR-0015, ADR-0043)."""
    confirmed_by: str | None = Field(default=None, min_length=1)
    """The person who confirmed the step before it started (level 2), or who performed its act
    and reported it (level 1); None for a step no person had to answer (ADR-0039)."""

    def to(self, state: StepState, **changes: Any) -> StepRun:
        if (self.state, state) not in STEP_TRANSITIONS:
            raise IllegalTransition(f"step {self.step_id!r}", self.state, state)
        return self.model_copy(update={"state": state, **changes})

    @property
    def done(self) -> bool:
        return self.state in DONE

    def artifact(self, artifact_id: str) -> Artifact | None:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None


class Run(Value):
    """One execution of a plan. The run carries what it executes — the steps in their order and
    the work of each — so that it can be resumed and replayed from its own record."""

    id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    """On whose behalf the run acts: the identity of the command that commissioned the plan.
    Every connector call carries it, and the target system's permissions for it stand."""
    autonomy_level: AutonomyLevel
    actions: Mapping[str, AutonomyLevel] = Field(default_factory=dict)
    """The level of each tool action of the process that runs below the process's level: a
    capability or a connector operation. A step that uses one runs at the lowest level that
    applies to it (ADR-0039)."""
    budget: Limits
    margin: float = Field(default=0.0, ge=0.0, le=0.9)
    """The share of every limit held back from the first step on; the run is held to the
    budget less the margin (ADR-0005)."""
    steps: tuple[Step, ...] = Field(min_length=1)
    work: Mapping[StepId, Mapping[str, Any]] = Field(default_factory=dict)
    inputs: Mapping[str, Any] = Field(default_factory=dict)
    """What the run was given when it started — an issue number, a repository — and what
    `$input` references in the work resolve to."""
    rehearsal: bool = False
    """A rehearsal (ADR-0030): no outward connector operation acts; each answers with the
    recorded response of an earlier real call, and every ledger entry of the run says so."""
    state: RunState = RunState.PLANNED
    cause: Cause | None = None
    reason: str | None = None
    step_runs: tuple[StepRun, ...] = ()
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _steps_are_in_execution_order(self) -> Run:
        seen: set[StepId] = set()
        for step in self.steps:
            for dependency in step.dependencies:
                if dependency not in seen:
                    raise UnsupportedWork(
                        step.id, f"depends on {dependency!r}, which does not come before it"
                    )
            seen.add(step.id)
        if not self.step_runs:
            object.__setattr__(
                self,
                "step_runs",
                tuple(
                    StepRun(step_id=step.id, index=index, method=step.method)
                    for index, step in enumerate(self.steps)
                ),
            )
        return self

    def to(self, state: RunState, cause: Cause | None = None, reason: str | None = None) -> Run:
        if (self.state, state) not in RUN_TRANSITIONS:
            raise IllegalTransition(f"run {self.id!r}", self.state, state)
        return self.model_copy(update={"state": state, "cause": cause, "reason": reason})

    def step(self, step_id: StepId) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def step_run(self, step_id: StepId) -> StepRun:
        for step_run in self.step_runs:
            if step_run.step_id == step_id:
                return step_run
        raise KeyError(step_id)

    def with_step_run(self, step_run: StepRun) -> Run:
        return self.model_copy(
            update={
                "step_runs": tuple(
                    step_run if s.step_id == step_run.step_id else s for s in self.step_runs
                )
            }
        )

    def next_step_run(self) -> StepRun | None:
        """The first step that has not succeeded."""
        for step_run in self.step_runs:
            if not step_run.done:
                return step_run
        return None

    def runnable(self) -> StepRun | None:
        """Where execution continues: the first step that has not succeeded, does not wait for
        a person, and whose dependencies have all succeeded. A step waiting for a person holds
        back only the steps that depend on it (ADR-0039)."""
        done = {s.step_id for s in self.step_runs if s.done}
        for step_run in self.step_runs:
            if step_run.done or step_run.state is StepState.WAITING_HUMAN:
                continue
            if all(d in done for d in self.step(step_run.step_id).dependencies):
                return step_run
        return None

    def waiting(self) -> tuple[StepRun, ...]:
        """The steps that wait for a person."""
        return tuple(s for s in self.step_runs if s.state is StepState.WAITING_HUMAN)

    def in_flight(self) -> StepRun | None:
        """The step run the executing instance was inside, if any: at most one, since steps
        run one at a time."""
        for step_run in self.step_runs:
            if step_run.state in IN_FLIGHT:
                return step_run
        return None

    def consumed(self) -> ConsumptionQuantities:
        """What every step so far used, and every running step reserved, summed per quantity:
        reserve, do not reconcile (ADR-0005). A step in flight counts as the larger of its
        reservation and what it has reported so far; a step that ended counts as what it used.
        Compute seconds sum within the budget's resource class only; a step in another class
        never passed admission."""
        totals: dict[str, float | int] = {}
        currency: dict[str, float] = {}
        by_model: TokensByModel | None = None
        resource_class = self.budget.compute.resource_class if self.budget.compute else None
        for step_run in self.step_runs:
            used = _counted(step_run)
            if used is None:
                continue
            for name in ("tokens_in", "tokens_out", "quota_units", "storage_bytes"):
                value = getattr(used, name)
                if value is not None:
                    totals[name] = totals.get(name, 0) + value
            for code, amount in (used.currency or {}).items():
                currency[code] = currency.get(code, 0.0) + amount
            if used.compute_seconds is not None and used.resource_class == resource_class:
                totals["compute_seconds"] = (
                    totals.get("compute_seconds", 0.0) + used.compute_seconds
                )
            by_model = add_tokens_by_model(by_model, used.tokens_by_model)
        return ConsumptionQuantities.model_validate(
            {
                **totals,
                "tokens_by_model": by_model,
                "currency": currency or None,
                "resource_class": resource_class if "compute_seconds" in totals else None,
            }
        )


def _counted(step_run: StepRun) -> ConsumptionQuantities | None:
    """What a step counts against the budget: its actual once it ended; the larger of its
    reservation and its actual so far while it is in flight."""
    used = step_run.consumption
    reserved = step_run.reservation
    if step_run.state not in IN_FLIGHT or reserved is None:
        return used
    if used is None:
        return reserved
    larger: dict[str, object] = {}
    for name in ("tokens_in", "tokens_out", "quota_units", "storage_bytes", "compute_seconds"):
        values = [v for v in (getattr(used, name), getattr(reserved, name)) if v is not None]
        if values:
            larger[name] = max(values)
    codes = set(used.currency or {}) | set(reserved.currency or {})
    if codes:
        larger["currency"] = {
            code: max(
                (used.currency or {}).get(code, 0.0), (reserved.currency or {}).get(code, 0.0)
            )
            for code in codes
        }
    if "compute_seconds" in larger:
        larger["resource_class"] = used.resource_class or reserved.resource_class
    larger["tokens_by_model"] = used.tokens_by_model
    return ConsumptionQuantities.model_validate(larger)
