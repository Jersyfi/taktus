"""The stage view of a run, for a participant who has no use for the step graph (UC-6.15).

A stage is read from the run's own steps, one for each: nobody draws or maintains stages apart
from the process. Each is done, current or ahead; a stage that waits for a person names the role,
never the person, and the owner where the wait names none. The view shows no method, exactness
class or glyph of the run level; it links to the run level instead.

Pure: the facts of the run level in, the stages out. Nothing is stored.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from taktus.components.reporting.domain.model.levels import RunFacts, StepFacts
from taktus.shared.v1 import Value

OWNER = "owner"
"""The role a wait that names none is shown as waiting for: never for nobody."""

RUN_WORDS: dict[str, str] = {
    "planned": "The run is planned.",
    "admitted": "The run is admitted and about to start.",
    "running": "The run is under way.",
    "waiting_human": "The run waits for a person.",
    "halted": "The run was halted.",
    "escalated": "The run failed and was handed to a person.",
    "finished": "The run is finished.",
}
"""The state of the run in words a participant knows, for every state of the run component."""

type StageState = Literal["done", "current", "ahead"]


class Stage(Value):
    name: str = Field(min_length=1)
    state: StageState
    waiting_for: str | None = None
    """The role the stage waits for. Never a person."""
    text: str = Field(min_length=1)
    """The text equivalent: name, state and, where it waits, the role."""


class StageView(Value):
    run_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    """The state of the run in words."""
    stages: tuple[Stage, ...]
    summary: str = Field(min_length=1)
    link: str = Field(min_length=1)
    """Where the run level shows the steps, for a reader who may see them."""


def _name(step: StepFacts) -> str:
    return step.id.replace("_", " ").replace("-", " ")


def _waiting_for(step: StepFacts) -> str | None:
    pending = any(d.status == "open" for d in step.decisions)
    human = step.state == "waiting_human" or (
        step.wait is not None and step.wait.account == "wait.human"
    )
    if not (human or pending):
        return None
    return step.wait.role if step.wait is not None and step.wait.role else OWNER


def stage_view(facts: RunFacts) -> StageView:
    """The stages of one run, from its facts and nothing else."""
    steps = facts.steps
    if facts.state == "finished":
        states: list[StageState] = ["done"] * len(steps)
    else:
        states = ["done" if s.state == "succeeded" else "ahead" for s in steps]
        current = [
            i for i, s in enumerate(steps) if s.state in ("running", "waiting_human", "admitted")
        ] or [i for i, s in enumerate(steps) if s.state in ("failed", "stopped", "rejected")]
        for i in current or [i for i, st in enumerate(states) if st == "ahead"][:1]:
            states[i] = "current"
    words = RUN_WORDS.get(facts.state, f"The run is {facts.state}.")
    stages: list[Stage] = []
    for step, state in zip(steps, states, strict=True):
        role = _waiting_for(step) if state == "current" else None
        text = f"{_name(step)}: {state}."
        if role is not None:
            text += f" Waiting for the role {role}."
        stages.append(Stage(name=_name(step), state=state, waiting_for=role, text=text))
    done = sum(1 for s in stages if s.state == "done")
    summary = f"{done} of {len(stages)} stages done. {words}"
    waiting = [s for s in stages if s.waiting_for]
    if waiting:
        roles = sorted({s.waiting_for for s in waiting if s.waiting_for})
        summary += f" Waiting for the role {', '.join(roles)}."
    return StageView(
        run_id=facts.id,
        state=words,
        stages=tuple(stages),
        summary=summary,
        link=f"/levels/runs/{facts.id}",
    )
