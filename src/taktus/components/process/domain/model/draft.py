"""A plan draft: what a process model in an interchange format says, never a process version
(UC-4.23, ADR-0168 §3).

A draft names every task of the model as a proposed step, with the dependencies the model's
flows give it, the role its lane suggests and the condition its branch carries. No step has a
method chosen: each names the method kinds its kind of task suggests as `candidates`, and the
draft names every question that must be answered before it can become a bundle. The person
answers them by filling in the draft — `method`, `reason`, `rejected`, `exactness`, `checks`,
`fallback`, `model`, `requires`, `expertise`, `work` — and `drafts.complete` turns the filled
draft into a bundle, which then goes the road every bundle goes (ADR-0168 §4).

A draft is a document of its own, with `kind: draft`. It is never stored and never registered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import (
    Capability,
    Check,
    ExactnessClass,
    Fallback,
    Method,
    Rejected,
    StepId,
    Value,
)
from taktus.shared.v1.step import Expertise, Role


class DraftStep(Value):
    """A task of the model, proposed as a step. Every field below `candidates` is the
    person's to fill in; empty means still to choose."""

    id: StepId
    name: str = Field(min_length=1)
    """The task's name in the model, or its identifier where it has none."""
    element: str = Field(min_length=1)
    """What the model says the task is: `userTask`, `serviceTask`, …"""
    depends_on: tuple[StepId, ...] = ()
    role: Role | None = None
    """The role the task's lane suggests. It becomes the step's own role at a human step, or
    its fallback's at a fallback to a person, once the draft's `confirmed` names it."""
    condition: str | None = None
    """The branch condition the model gives the task, in the model's own words."""
    when: tuple[Mapping[str, Any], ...] | None = None
    """The condition as machine checks in the shape of ADR-0088's `when`: given where the model
    already carried one, otherwise the person's to state."""
    candidates: tuple[Method, ...] = Field(min_length=1)
    """The method kinds the task's kind suggests. A suggestion, never a choice."""
    suggested: Method | None = None
    """The method a model Taktus wrote carried for the step; still to be chosen."""
    method: Method | None = None
    reason: str | None = None
    rejected: tuple[Rejected, ...] | None = None
    exactness: ExactnessClass | None = None
    checks: tuple[Check, ...] | None = None
    fallback: Fallback | None = None
    model: str | None = None
    requires: tuple[Capability, ...] | None = None
    expertise: tuple[Expertise, ...] | None = None
    work: Mapping[str, Any] | None = None


class DraftGateway(Value):
    """A gateway of the model: where the path splits or joins, between which steps."""

    id: str = Field(min_length=1)
    kind: Literal["exclusive", "inclusive", "parallel", "event", "complex"]
    before: tuple[StepId, ...] = ()
    """The nearest steps before it."""
    after: tuple[StepId, ...] = ()
    """The nearest steps after it."""


class Question(Value):
    """One thing to be answered before the draft can become a bundle."""

    about: str = Field(min_length=1)
    """The step, lane or gateway it concerns, by identifier; `process` for the whole."""
    asks: str = Field(min_length=1)


class Draft(Value):
    kind: Literal["draft"] = "draft"
    source: str = Field(min_length=1)
    """The format the model came in, and its process's identifier there."""
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    """The process identifier the draft proposes."""
    name: str = Field(min_length=1)
    steps: tuple[DraftStep, ...] = Field(min_length=1)
    gateways: tuple[DraftGateway, ...] = ()
    roles: Mapping[str, Role] = Field(default_factory=dict)
    """Each lane of the model, by its name, and the role it suggests."""
    confirmed: tuple[Role, ...] = ()
    """The roles a person confirmed name a role and not a person (principle 14). Only a
    confirmed role reaches the bundle."""
    level: Literal[1, 2] = 1
    """The autonomy level the draft proposes to start at: a model's process starts as a
    discovered one does (UC-9.4)."""
    questions: tuple[Question, ...] = ()
    not_imported: tuple[str, ...] = ()
    """What the model held that the draft does not carry, one line each."""

    def step(self, step_id: str) -> DraftStep:
        return next(s for s in self.steps if s.id == step_id)
