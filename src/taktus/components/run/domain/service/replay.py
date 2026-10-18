"""Replay (ADR-0108): whether a replayed run came where its recording came. Pure, no I/O.

A replay runs a process again as a rehearsal whose every step that would leave the engine is
answered by the recorded result of the same step. Whether the bundle, the engine's handling of
it and the recorded answers still hold together is then read from the step states: every step
must reach the state it reached in the recorded run.

Two things are not a difference. A step that waited for a person in the recorded run — an
anchor, its own `ask`, its level — and waits for one in the replay has reached its boundary as
recorded. A replay does not decide for that person, so the steps that depend on such a step are
not reached, and are not compared. Everything else is: a step the recording does not know, a
recorded step the bundle no longer has, a state that differs, and the state the run ended in.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from taktus.components.run.domain.model.run import Cause, Run, RunState, StepState
from taktus.shared.v1 import StepId, Value


class RecordedStep(Value):
    """One step of the recorded run, as far as the comparison needs it."""

    step_id: StepId
    state: StepState
    met_a_person: bool = False
    """Whether the step waited for a person at its boundary in the recorded run."""


class RecordedEnd(Value):
    """Where the recorded run ended."""

    state: RunState
    cause: Cause | None = None


def differences(
    recorded: Sequence[RecordedStep], end: RecordedEnd, replayed: Run
) -> tuple[str, ...]:
    """Every way the replayed run did not come where the recorded run came, one line each and
    each naming its step; empty when it came there."""
    by_id = {step.step_id: step for step in recorded}
    found: list[str] = []
    at_a_person: list[StepId] = []
    for step_run in replayed.step_runs:
        known = by_id.get(step_run.step_id)
        if known is None:
            found.append(
                f"{step_run.step_id}: the recording has no such step; the bundle changed since "
                "it was recorded, and the run must be recorded again"
            )
            continue
        if step_run.state is StepState.WAITING_HUMAN and known.met_a_person:
            at_a_person.append(step_run.step_id)
    beyond = _dependents(replayed, at_a_person)
    for step_run in replayed.step_runs:
        known = by_id.get(step_run.step_id)
        if known is None or step_run.step_id in at_a_person:
            continue
        if step_run.step_id in beyond and step_run.state is StepState.PLANNED:
            continue
        if step_run.state is not known.state:
            line = f"{step_run.step_id}: recorded {known.state}, replayed {step_run.state}"
            if step_run.reason:
                line += f": {step_run.reason}"
            found.append(line)
    present = {step_run.step_id for step_run in replayed.step_runs}
    found.extend(
        f"{step.step_id}: recorded {step.state}, and the bundle no longer has the step"
        for step in recorded
        if step.step_id not in present
    )
    if at_a_person:
        if replayed.state is not RunState.WAITING_HUMAN:
            found.append(
                f"the run: {', '.join(at_a_person)} waits for a person as recorded, and the run "
                f"ended {replayed.state}"
            )
    elif (replayed.state, replayed.cause) != (end.state, end.cause):
        found.append(
            f"the run: recorded {_ended(end.state, end.cause)}, replayed "
            f"{_ended(replayed.state, replayed.cause)}"
            + (f": {replayed.reason}" if replayed.reason else "")
        )
    return tuple(found)


def _ended(state: RunState, cause: Cause | None) -> str:
    return str(state) if cause is None else f"{state} ({cause})"


def _dependents(run: Run, roots: Iterable[StepId]) -> set[StepId]:
    """Every step that depends on one of the roots, directly or through another step."""
    reached: set[StepId] = set(roots)
    found: set[StepId] = set()
    for step in run.steps:  # in execution order: a dependency always comes first
        if any(d in reached for d in step.dependencies):
            reached.add(step.id)
            found.add(step.id)
    return found
