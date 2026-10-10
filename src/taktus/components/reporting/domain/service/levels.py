"""The run level of a live representation, drawn from the run's facts (UC-6.10 §1, ADR-0063).

`run_level` turns the facts of one run into what a representation draws: the run and each of
its steps, every fact again, each with its glyph with motion and without, and its text
equivalent (ADR-0059). The figures are the run component's, flattened into named numbers and
never computed again here (ADR-0029).

Pure: facts in, elements out.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from taktus.components.reporting.domain.model.levels import Figure, RunFacts, StepFacts, Wait
from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, glyph
from taktus.shared.v1 import ConsumptionQuantities, ExactnessClass, Method, Value

ACCOUNTS: dict[str, str] = {
    "limit.provider": "the provider's rate limit",
    "limit.quota": "a quota",
    "limit.budget": "the run's budget",
    "limit.compute": "compute capacity",
    "wait.human": "a person",
    "wait.external": "an external state",
    "wait.dependency": "something it depends on",
}
"""What each of the seven accounts of ADR-0015 says a step waits on, in words. A test holds the
keys equal to the run component's accounts."""


class Drawn(Value):
    """An element's glyph with motion allowed, and without (UC-6.10 *calm on request*)."""

    moving: Glyph
    still: Glyph


class StepElement(Value):
    id: str
    method: Method
    exactness: ExactnessClass | None
    state: str
    depends_on: tuple[str, ...] = ()
    attempt: int
    wait: Wait | None = None
    consumption: tuple[Figure, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    drawn: Drawn
    text: str = Field(min_length=1)
    """The text equivalent: method, family, class and state, what it waits on, what it used."""


class RunElement(Value):
    id: str
    process_version: str
    state: str
    rehearsal: bool
    consumed: tuple[Figure, ...] = ()
    created_at: datetime
    updated_at: datetime
    drawn: Drawn
    text: str = Field(min_length=1)


class RunLevel(Value):
    """The run level of UC-6.10: where one run stands."""

    run: RunElement
    steps: tuple[StepElement, ...]


def figures(quantities: ConsumptionQuantities | None) -> tuple[Figure, ...]:
    """The quantities as named numbers, in the record's order; the resource class of compute
    seconds is part of the name, and tokens by model are named by model and price kind."""
    if quantities is None:
        return ()
    found: list[Figure] = []
    for name, value in quantities.quantities().items():
        if name == "currency":
            found.extend(Figure(name=f"currency.{code}", value=v) for code, v in value.items())
        elif name == "tokens_by_model":
            for model, kinds in value.items():
                found.extend(
                    Figure(name=f"tokens_by_model.{model}.{kind}", value=count)
                    for kind, count in kinds.document().items()
                )
        elif name == "compute_seconds":
            found.append(Figure(name=f"compute_seconds.{quantities.resource_class}", value=value))
        else:
            found.append(Figure(name=name, value=value))
    return tuple(found)


def _figures_text(found: tuple[Figure, ...]) -> str:
    return ", ".join(f"{f.name} {_number(f.value)}" for f in found)


def _number(value: float | int) -> str:
    return str(value) if isinstance(value, int) else f"{value:g}"


def _wait_text(wait: Wait) -> str:
    on = ACCOUNTS.get(wait.account, wait.account)
    parts = [f"waits on {on} ({wait.account}, {wait.cause}) since {wait.since.isoformat()}"]
    if wait.role is not None:
        parts.append(f"addressed to the role {wait.role}")
    if wait.on is not None:
        parts.append(f"held by step {wait.on}")
    if wait.requests:
        parts.append(f"decision requests {', '.join(wait.requests)}")
    return "; ".join(parts) + "."


def _drawn(element: Step | Run) -> Drawn:
    return Drawn(moving=glyph(element, motion=True), still=glyph(element, motion=False))


def _step(facts: StepFacts) -> StepElement:
    drawn = _drawn(
        Step(name=facts.id, method=facts.method, exactness=facts.exactness, state=facts.state)
    )
    used = figures(facts.consumption)
    text = [drawn.moving.text]
    if facts.wait is not None:
        text.append(_wait_text(facts.wait))
    if used:
        text.append(f"Used {_figures_text(used)}.")
    return StepElement(
        id=facts.id,
        method=facts.method,
        exactness=facts.exactness,
        state=facts.state,
        depends_on=facts.depends_on,
        attempt=facts.attempt,
        wait=facts.wait,
        consumption=used,
        started_at=facts.started_at,
        finished_at=facts.finished_at,
        drawn=drawn,
        text=" ".join(text),
    )


def run_level(facts: RunFacts) -> RunLevel:
    """The run level of one run, from its facts and nothing else."""
    drawn = _drawn(Run(name=facts.id, state=facts.state))
    consumed = figures(facts.consumed)
    text: list[str] = [drawn.moving.text, f"Process {facts.process_version}."]
    if facts.rehearsal:
        text.append("A rehearsal: no outward operation acts.")
    text.append(
        f"Consumed so far: {_figures_text(consumed)}." if consumed else "Consumed: nothing."
    )
    return RunLevel(
        run=RunElement(
            id=facts.id,
            process_version=facts.process_version,
            state=facts.state,
            rehearsal=facts.rehearsal,
            consumed=consumed,
            created_at=facts.created_at,
            updated_at=facts.updated_at,
            drawn=drawn,
            text=" ".join(text),
        ),
        steps=tuple(_step(step) for step in facts.steps),
    )


def drawn_glyphs(level: RunLevel, *, motion: bool) -> list[tuple[Step | Run, Glyph]]:
    """Every element of the level with the glyph it hands over, for the vocabulary's check."""

    def pick(d: Drawn) -> Glyph:
        return d.moving if motion else d.still

    drawn: list[tuple[Step | Run, Glyph]] = [
        (Run(name=level.run.id, state=level.run.state), pick(level.run.drawn))
    ]
    drawn.extend(
        (Step(name=s.id, method=s.method, exactness=s.exactness, state=s.state), pick(s.drawn))
        for s in level.steps
    )
    return drawn
