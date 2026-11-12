"""A plan worked out in dialogue, before it is commissioned (ADR-0237, UC-1.2).

A **plan draft** is the record a person and Taktus change back and forth. It names the four
parts a commissioned plan must have — what is to be done, the processes, methods and
capabilities it uses, the date it is due, and the autonomy level with its reason (ADR-0026) —
and an estimate of effort for every step, each naming what it was computed from.

Every change makes a new version of the draft. Commissioning is an act of its own: it takes one
version, and only that version, into a `Plan` of the shared kernel, whose identifier names the
draft and the version (`<draft>@v<version>`). A draft changed after it was commissioned is a
new version that nobody commissioned: what runs is the version that was, until the new one is
commissioned again.

Pure: what the draft lacks is computed here; nothing reads a store.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import AutonomyLevel, Commissioned, PlanResult, Step, Value

PARTS: tuple[str, ...] = (
    "what is to be done",
    "the processes, methods and capabilities it uses",
    "the date it is due",
    "the autonomy level with its reason",
)
"""The four parts of a plan, in the words a refusal names them by (ADR-0026)."""

AGENT_PARTS: tuple[str, ...] = (
    "the agent's name",
    "its instructions",
    "the model purpose it asks",
    "the tools it may use",
    "the knowledge it reads",
    "the process it runs",
)
"""What an agent draft lacks besides the four parts, in the order the guided mode asks for them
(ADR-0292 §1). The agent's role is the goal, its autonomy level and reason the plan's."""

Unit = Literal["seconds", "tokens", "minor_units", "takte", "turns"]


class Estimate(Value):
    """The effort of one step as the plan states it. A figure without a basis is a guess and is
    shown as one; a step without a figure cannot be estimated, and the plan is refused before
    anything runs (ADR-0005)."""

    step_id: str = Field(min_length=1)
    figure: float | None = Field(default=None, ge=0)
    """None: the step cannot be estimated before it starts."""
    unit: Unit = "seconds"
    basis: str | None = Field(default=None, min_length=1, max_length=300)
    """What the figure was computed from: the median of a process's last runs, the worker's
    own estimate, a price table. None: a guess."""

    @property
    def guess(self) -> bool:
        return self.figure is not None and self.basis is None

    def shown(self) -> str:
        """The estimate as a person reads it: a figure with its basis, or a guess said as one."""
        if self.figure is None:
            return f"step {self.step_id}: cannot be estimated before it starts"
        amount = f"{self.figure:g} {self.unit.replace('_', ' ')}"
        if self.basis is None:
            return f"step {self.step_id}: a guess of about {amount}, computed from nothing"
        return f"step {self.step_id}: {amount}, computed from {self.basis}"


class AgentPart(Value):
    """The agent a draft works out, beside the plan's own parts (ADR-0292, UC-8.7). Named by
    capability: what a tool, source or connector is called is checked by the catalogue when the
    agent is registered (ADR-0287)."""

    name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(default="1", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    instructions: str | None = Field(default=None, min_length=1, max_length=20000)
    model: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    """The model purpose the agent asks, as a step names one."""
    tools: tuple[str, ...] | None = None
    """None: never stated. An empty tuple is stated: the agent may use no tool."""
    sources: tuple[str, ...] | None = None
    """The knowledge it reads. None: never stated; empty: it reads none."""
    connectors: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    approval_limit: Decimal | None = Field(default=None, ge=0)

    def missing(self) -> tuple[str, ...]:
        """The agent's own parts it lacks, in their order; the process it runs is the draft's."""
        lacking: list[str] = []
        if self.name is None:
            lacking.append(AGENT_PARTS[0])
        if self.instructions is None:
            lacking.append(AGENT_PARTS[1])
        if self.model is None:
            lacking.append(AGENT_PARTS[2])
        if self.tools is None:
            lacking.append(AGENT_PARTS[3])
        if self.sources is None:
            lacking.append(AGENT_PARTS[4])
        return tuple(lacking)


class DomainPart(Value):
    """The domain blueprint a draft instantiates (ADR-0289, UC-15.1). The questions are the
    instance's, which the catalogue keeps; the draft carries the ones open, in the words they
    ask, and each is a part it lacks."""

    instance: str = Field(min_length=1)
    blueprint: str = Field(min_length=1)
    open: tuple[str, ...] = ()


class PlanDraft(Value):
    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    """The command the dialogue answers."""
    version: int = Field(ge=1)
    goal: str | None = Field(default=None, min_length=1)
    steps: tuple[Step, ...] = ()
    """The steps in execution order: each carries its method, its reason and the capabilities
    it needs. Long work is broken into steps here, each ending at a persisted boundary."""
    process_version: str | None = Field(default=None, min_length=1)
    """The process version the plan runs, or None for a plan that results in a new one."""
    due: datetime | None = None
    autonomy_level: AutonomyLevel | None = None
    autonomy_reason: str | None = Field(default=None, min_length=1, max_length=500)
    estimates: tuple[Estimate, ...] = ()
    results_in: PlanResult = PlanResult.RUN
    agent: AgentPart | None = None
    """The agent the draft works out, or None for a plan that is no agent (ADR-0292)."""
    domain: DomainPart | None = None
    """The domain the draft instantiates, or None for a plan that is no domain (ADR-0289)."""
    describes: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]*$")
    """The process the goal describes, which commissioning hands to the describe process; None
    for a plan that describes none (ADR-0290)."""
    changed_by: str = Field(min_length=1)
    changed_at: datetime
    commissioned_version: int | None = Field(default=None, ge=1)
    """The version commissioned last, if any. A later version is not commissioned."""
    commissioned: Commissioned | None = None
    """Who commissioned `commissioned_version`, and when."""

    @property
    def plan_id(self) -> str:
        """The identifier of the shared kernel's plan this version becomes when commissioned."""
        return f"{self.id}@v{self.version}"

    @property
    def is_commissioned(self) -> bool:
        """Whether the current version is the one commissioned."""
        return self.commissioned_version == self.version

    def missing(self) -> tuple[str, ...]:
        """The parts of the four the draft lacks, in their order; empty when it has them all."""
        lacking: list[str] = []
        if self.goal is None:
            lacking.append(PARTS[0])
        if not self.steps:
            lacking.append(PARTS[1])
        if self.due is None:
            lacking.append(PARTS[2])
        if self.autonomy_level is None or self.autonomy_reason is None:
            lacking.append(PARTS[3])
        if self.agent is not None:
            lacking.extend(self.agent.missing())
            if self.process_version is None:
                lacking.append(AGENT_PARTS[5])
        if self.domain is not None:
            lacking.extend(self.domain.open)
        if self.describes is not None and self.results_in is not PlanResult.PROCESS_VERSION:
            lacking.append("a new process version as its result, which a description makes")
        return tuple(lacking)

    def unestimable(self) -> tuple[str, ...]:
        """The steps that cannot be estimated before they start: no estimate, or one without
        a figure."""
        figured = {e.step_id for e in self.estimates if e.figure is not None}
        return tuple(s.id for s in self.steps if s.id not in figured)
