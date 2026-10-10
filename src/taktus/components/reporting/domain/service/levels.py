"""The run level and the process level of a live representation, drawn from their facts (UC-6.10
§1, ADR-0063, ADR-0064).

`run_level` turns the facts of one run into what a representation draws: the run and each of
its steps, every fact again, each with its glyph with motion and without, and its text
equivalent (ADR-0059). The figures are the run component's, flattened into named numbers and
never computed again here (ADR-0029).

`process_level` turns one version of a process into its graph: each step with how it works — its
method kind, exactness class, why that method, what was not chosen, where it falls back — and
whether a run of the version runs it right now; the autonomy statement in words (ADR-0026); and
the runs of the version the reader may see.

Pure: facts in, elements out.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from taktus.components.reporting.domain.model.levels import (
    Figure,
    ProcessFacts,
    ProcessStepFacts,
    RunAtVersion,
    RunFacts,
    StepFacts,
    VersionRef,
    Wait,
)
from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, glyph
from taktus.shared.v1 import Autonomy, ConsumptionQuantities, ExactnessClass, Method, Value

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


class ProcessStepElement(Value):
    id: str
    method: Method
    exactness: ExactnessClass | None
    reason: str
    rejected: tuple[Method, ...] = ()
    fallback: Method | None = None
    depends_on: tuple[str, ...] = ()
    running_in: tuple[str, ...] = ()
    """The runs this step is running in right now; empty at rest."""
    drawn: Drawn
    text: str = Field(min_length=1)


class RunAtVersionElement(Value):
    id: str
    state: str
    rehearsal: bool
    running: tuple[str, ...] = ()
    created_at: datetime
    drawn: Drawn
    text: str = Field(min_length=1)


class ProcessElement(Value):
    id: str
    name: str
    version: str
    versions: tuple[VersionRef, ...]
    autonomy: Autonomy
    """The autonomy statement, as the version states it (ADR-0026)."""
    autonomy_text: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ProcessLevel(Value):
    """The process level of UC-6.10: the steps of a process version as a graph, each showing how
    it works, with the autonomy statement and the runs of the version."""

    process: ProcessElement
    steps: tuple[ProcessStepElement, ...]
    runs: tuple[RunAtVersionElement, ...]


AT_REST = "planned"
"""The state a step of a process version is drawn in while no run of the version runs it. The
graph is the version's plan; the vocabulary's `planned` is the still form of a step that is part
of it and is not doing work (ADR-0064)."""


def _counted(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def autonomy_text(autonomy: Autonomy) -> str:
    """The autonomy statement in words: the level, why, and what is missing to go higher."""
    parts = [f"Runs at autonomy level {autonomy.level}: {autonomy.reason}."]
    if autonomy.toward_next is not None:
        parts.append(f"Toward level {autonomy.level + 1}: {autonomy.toward_next}.")
    for action, statement in sorted((autonomy.actions or {}).items()):
        parts.append(f"The action {action} runs at level {statement.level}: {statement.reason}.")
    return " ".join(parts)


def _process_step(step: ProcessStepFacts, runs: tuple[RunAtVersion, ...]) -> ProcessStepElement:
    running_in = tuple(r.id for r in runs if step.id in r.running)
    state = "running" if running_in else AT_REST
    drawn = _drawn(Step(name=step.id, method=step.method, exactness=step.exactness, state=state))
    text = [drawn.moving.text, f"Why this method: {step.reason}."]
    if step.rejected:
        text.append(f"Considered and not chosen: {', '.join(str(m) for m in step.rejected)}.")
    if step.fallback is not None:
        text.append(f"Falls back to {step.fallback}.")
    if step.depends_on:
        text.append(f"After {', '.join(step.depends_on)}.")
    text.append(f"Running in {', '.join(running_in)}." if running_in else "At rest.")
    return ProcessStepElement(
        id=step.id,
        method=step.method,
        exactness=step.exactness,
        reason=step.reason,
        rejected=step.rejected,
        fallback=step.fallback,
        depends_on=step.depends_on,
        running_in=running_in,
        drawn=drawn,
        text=" ".join(text),
    )


def _run_at_version(run: RunAtVersion) -> RunAtVersionElement:
    drawn = _drawn(Run(name=run.id, state=run.state))
    text = drawn.moving.text
    if run.running:
        text += f" Running {', '.join(run.running)}."
    return RunAtVersionElement(
        id=run.id,
        state=run.state,
        rehearsal=run.rehearsal,
        running=run.running,
        created_at=run.created_at,
        drawn=drawn,
        text=text,
    )


def process_level(facts: ProcessFacts) -> ProcessLevel:
    """The process level of one version, from its facts and the runs handed with them. The runs
    are the ones the reader may see; which those are is the query's (`may_see`)."""
    runs = tuple(sorted(facts.runs, key=lambda r: r.created_at, reverse=True))
    statement = autonomy_text(facts.autonomy)
    active = next((v.version for v in facts.versions if v.active), None)
    standing = "the active version" if active == facts.version else "not the active version"
    return ProcessLevel(
        process=ProcessElement(
            id=facts.id,
            name=facts.name,
            version=facts.version,
            versions=facts.versions,
            autonomy=facts.autonomy,
            autonomy_text=statement,
            text=f"Process {facts.name} ({facts.ref}), {standing}, with "
            f"{_counted(len(facts.steps), 'step')} and {_counted(len(runs), 'run')}. {statement}",
        ),
        steps=tuple(_process_step(step, runs) for step in facts.steps),
        runs=tuple(_run_at_version(run) for run in runs),
    )
