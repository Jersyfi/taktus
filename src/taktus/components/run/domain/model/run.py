"""Run, step run and checkpoint, with the state machine of control-plane.md §5.2."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

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
    Value,
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
    STOP = "stop"
    FAILURE = "failure"
    CEILING = "ceiling"


# Every transition the run knows. Anything not listed is illegal. `self-healed` of §5.2 is a
# running → running transition and arrives with retries; `waiting_human` arrives with anchors.
RUN_TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    {
        (RunState.PLANNED, RunState.ADMITTED),
        (RunState.ADMITTED, RunState.RUNNING),
        (RunState.RUNNING, RunState.WAITING_HUMAN),
        (RunState.WAITING_HUMAN, RunState.RUNNING),
        (RunState.RUNNING, RunState.HALTED),
        (RunState.RUNNING, RunState.ESCALATED),
        (RunState.RUNNING, RunState.FINISHED),
        (RunState.HALTED, RunState.RUNNING),
        (RunState.ESCALATED, RunState.RUNNING),
    }
)

RESUMABLE: frozenset[RunState] = frozenset({RunState.HALTED, RunState.ESCALATED})
"""States a run leaves by `resume`: it stopped at a boundary and waits."""

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


STEP_TRANSITIONS: frozenset[tuple[StepState, StepState]] = frozenset(
    {
        (StepState.PLANNED, StepState.ADMITTED),
        (StepState.PLANNED, StepState.REJECTED),
        (StepState.REJECTED, StepState.ADMITTED),  # after a limit change, on resume
        (StepState.REJECTED, StepState.REJECTED),  # rejected again on resume
        (StepState.ADMITTED, StepState.RUNNING),
        (StepState.ADMITTED, StepState.REJECTED),  # the worker rejected what the core admitted
        (StepState.ADMITTED, StepState.STOPPED),  # the instance stopped before the step ran
        (StepState.RUNNING, StepState.SUCCEEDED),
        (StepState.RUNNING, StepState.FAILED),
        (StepState.RUNNING, StepState.STOPPED),
        (StepState.STOPPED, StepState.ADMITTED),  # resume from the checkpoint
        (StepState.FAILED, StepState.ADMITTED),  # retry from the boundary before it
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
    adapter: str | None = None
    assignment_id: AssignmentId | None = None
    estimate: ConsumptionQuantities | None = None
    consumption: Consumption | None = None
    artifacts: tuple[Artifact, ...] = ()
    checkpoint: Checkpoint | None = None
    reason: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

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
    autonomy_level: AutonomyLevel
    budget: Limits
    steps: tuple[Step, ...] = Field(min_length=1)
    work: Mapping[StepId, Mapping[str, Any]] = Field(default_factory=dict)
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
        """The first step that has not succeeded: where execution continues."""
        for step_run in self.step_runs:
            if not step_run.done:
                return step_run
        return None

    def in_flight(self) -> StepRun | None:
        """The step run the executing instance was inside, if any: at most one, since steps
        run one at a time."""
        for step_run in self.step_runs:
            if step_run.state in IN_FLIGHT:
                return step_run
        return None

    def consumed(self) -> ConsumptionQuantities:
        """What every step so far used, summed per quantity. Compute seconds sum within the
        budget's resource class only; a step in another class never passed admission."""
        totals: dict[str, float | int] = {}
        currency: dict[str, float] = {}
        resource_class = self.budget.compute.resource_class if self.budget.compute else None
        for step_run in self.step_runs:
            used = step_run.consumption
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
        return ConsumptionQuantities.model_validate(
            {
                **totals,
                "currency": currency or None,
                "resource_class": resource_class if "compute_seconds" in totals else None,
            }
        )
