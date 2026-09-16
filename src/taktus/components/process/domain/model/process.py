"""Process, process version, edge, trigger and service level (control-plane.md §4)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from pydantic import Field, model_validator

from taktus.components.process.domain.model.errors import InvalidProcess
from taktus.components.process.domain.service.validation import topological_order, validate_graph
from taktus.shared.v1 import AutonomyLevel, ExactnessClass, Step, StepId, Value

# What a step does when it runs — the task for a worker, the rule to evaluate, what to wait for.
# Its shape belongs to the process bundle format, which arrives at 0.3.0 (ADR-0011,
# docs/roadmap.md); until then it is carried as data and interpreted by the component that
# executes it. That is why it is not typed here.
type Work = Mapping[str, Any]

STRICTNESS = (
    ExactnessClass.EXACT,
    ExactnessClass.SOURCED,
    ExactnessClass.TOLERANT,
    ExactnessClass.FREE,
)


class Process(Value):
    """A named process. The version that runs is `active_version`; the versions are bundles."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    description: str | None = None
    active_version: str | None = None


class Edge(Value):
    """A dependency: `to_step` starts only after `from_step` has finished."""

    from_step: StepId
    to_step: StepId


class Trigger(Value):
    """What starts a run: a schedule or an event. A process without triggers starts by hand."""

    schedule: str | None = Field(default=None, min_length=1)
    event: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]*$")
    filter: str | None = Field(default=None, min_length=1)
    condition: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _one_source(self) -> Trigger:
        if (self.schedule is None) == (self.event is None):
            raise ValueError("a trigger names either a schedule or an event")
        return self


class Slo(Value):
    """The service level a process promises: how fresh its result is, how long a run may take."""

    freshness: timedelta | None = None
    latency: timedelta | None = None


class ProcessVersion(Value):
    """One version of a process: the graph, its triggers and service level, and who changed
    what and why. Every invariant of the graph is checked here; an instance is valid or does
    not exist."""

    process_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1)
    autonomy_level: AutonomyLevel
    steps: tuple[Step, ...] = Field(min_length=1)
    triggers: tuple[Trigger, ...] = ()
    slo: Slo | None = None
    work: Mapping[StepId, Work] = Field(default_factory=dict)
    limits: Work | None = None
    author: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _valid_graph(self) -> ProcessVersion:
        findings = validate_graph(self.steps)
        ids = {step.id for step in self.steps}
        findings.extend(
            f"work is given for {step_id!r}, which is not a step of this process"
            for step_id in self.work
            if step_id not in ids
        )
        if findings:
            raise InvalidProcess(tuple(findings))
        return self

    @property
    def ref(self) -> str:
        """How the ledger names this version."""
        return f"{self.process_id}@{self.version}"

    @property
    def id(self) -> str:
        """The repository key: a version is identified by its process and its version."""
        return self.ref

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(
            Edge(from_step=dependency, to_step=step.id)
            for step in self.steps
            for dependency in step.dependencies
        )

    @property
    def exactness(self) -> ExactnessClass | None:
        """The class of the strictest result the process produces; None when it produces none."""
        classes = [step.exactness for step in self.steps if step.exactness is not None]
        if not classes:
            return None
        return min(classes, key=STRICTNESS.index)

    def step(self, step_id: StepId) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def ordered(self) -> tuple[Step, ...]:
        """The steps in execution order: every dependency first, ties in declared order."""
        return topological_order(self.steps)
