"""Which autonomy level holds for a step, and what it asks of a person (ADR-0039).

The level is set per process and per tool action (`Autonomy.actions`); where more than one
applies to a step, the lowest holds. The tool actions of a step are the capabilities it
requires and, for a connector call or a wait on one, the operation and its capability.

What a level asks before a step starts, at the step boundary:

- **level 1** — observe and propose: a step that *acts* is not executed. Taktus records what it
  proposes, and the step waits until a person performed the act and reported it. A step acts
  when it hands work to a worker or calls an outward connector operation. Every other step —
  a rule, a read, a model's text, a wait — is the analysis Taktus supplies, and runs;
- **level 2** — execute after approval: no step starts before a person confirmed it;
- **level 3** and above — autonomous under supervision: no confirmation, and a step runs only on
  an adapter whose maturity is *verified* or above (NTC-0051);
- **level 4** asks the same before a step starts. After a step failed, Taktus heals a known
  failure inside the frame on its own (`healing.py`, ADR-0160).

A rehearsal acts on nothing outside (ADR-0030) and is asked none of this: it exists to observe
where a run comes to (NTC-0079).

This rule belongs to governance, which owns autonomy levels; it is the run's until the
enforcement at the step boundary moves there, as admission did (`admission.py`).

Pure: the levels and the step's work in, a verdict out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field

from taktus.components.run.domain.model.work import ConnectorRule, WaitWork, Work, WorkerWork
from taktus.shared.v1 import AutonomyLevel, ClassAutonomy, Step, Value
from taktus.shared.v1.autonomy import depending_on

type Awaits = Literal["confirmation", "performance"]

CONFIRMATION: Awaits = "confirmation"
PERFORMANCE: Awaits = "performance"

VERIFIED_FROM: AutonomyLevel = 3
"""From this level a step runs only on an adapter at *verified* or above."""


class Held(Value):
    """The level a step runs at, and what holds it there."""

    level: AutonomyLevel
    action: str | None = Field(default=None, min_length=1)
    """The tool action whose level holds; None when the process's own level does."""
    case_class: str | None = Field(default=None, min_length=1)
    """The class of request whose level holds (ADR-0215); None when none does."""

    def describe(self) -> str:
        if self.case_class is not None:
            held = f"the class {self.case_class}"
        else:
            held = "the process" if self.action is None else f"the action {self.action}"
        return f"level {self.level}, held by {held}"


def actions_of(step: Step, work: Work) -> tuple[str, ...]:
    """The tool actions a step uses: the capabilities it requires, and the operation it calls
    or waits on with that operation's capability."""
    found: list[str] = list(step.required_capabilities)
    if isinstance(work, ConnectorRule):
        found += [work.capability, work.operation]
    elif isinstance(work, WaitWork) and work.until is not None:
        found += [work.until.capability, work.until.operation]
    return tuple(dict.fromkeys(found))


def held(
    process: AutonomyLevel,
    actions: Mapping[str, AutonomyLevel],
    used: Sequence[str],
    klass: tuple[str | None, AutonomyLevel] | None = None,
) -> Held:
    """The lowest level that applies to a step: the process's, or a lower one of an action the
    step uses, or of the class of request it depends on (`klass`: the class named, None for one
    the statement does not name, and its level). Between two actions at the same level, the
    first named holds. A class named holds where its level equals the process's, so that its
    decisions count for the class (ADR-0215 §3); an action lower than the class holds over it."""
    verdict = Held(level=process)
    for action in used:
        level = actions.get(action)
        if level is not None and level < verdict.level:
            verdict = Held(level=level, action=action)
    if klass is not None:
        name, level = klass
        if level < verdict.level or (
            level == verdict.level and verdict.action is None and name is not None
        ):
            verdict = Held(level=level, case_class=name)
    return verdict


def class_of(
    classes: ClassAutonomy | None, steps: Sequence[Step], step_id: str, named: str | None
) -> tuple[str | None, AutonomyLevel] | None:
    """The class of request that holds a step, with its level: None where the step does not
    depend on the class's step (ADR-0215 §2). `named` is the class the run's class step named,
    None before it did and where it named none the statement knows."""
    if classes is None or step_id not in depending_on(steps, classes.step):
        return None
    return named, classes.level_of(named)


def class_named(classes: ClassAutonomy, value: object) -> str | None:
    """The class a result names, as the statement knows it: the text, or the value at
    `select`, stripped of space and closing punctuation and in lower case. None where it names
    no class the statement lists (ADR-0215 §2)."""
    found = value
    if classes.select is not None:
        for part in classes.select.split("."):
            if isinstance(found, Mapping):
                found = found.get(part)
            elif isinstance(found, list) and part.isdigit() and int(part) < len(found):
                found = found[int(part)]
            else:
                return None
    elif isinstance(found, Mapping):
        found = found.get("text")
    if not isinstance(found, str):
        return None
    word = found.strip().strip(".!:;,'\"`").strip().lower()
    return word if word in classes.levels else None


def acts(work: Work, outward: bool | None) -> bool:
    """Whether a step acts: hands work to a worker, or calls a connector operation that is
    declared outward. `outward` is the declaration of a connector call's operation; None when
    it cannot be read, and an operation that cannot be read counts as acting."""
    if isinstance(work, WorkerWork):
        return True
    if isinstance(work, ConnectorRule):
        return outward is None or outward
    return False


def awaits(level: AutonomyLevel, *, acting: bool, confirmed: bool) -> Awaits | None:
    """What a step waits for before it starts at its level, or None when it starts."""
    if level == 1 and acting:
        return PERFORMANCE
    if level == 2 and not confirmed:
        return CONFIRMATION
    return None


def needs_verified(level: AutonomyLevel) -> bool:
    """Whether a step at this level runs only on a verified adapter."""
    return level >= VERIFIED_FROM
