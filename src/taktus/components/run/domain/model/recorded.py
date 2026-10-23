"""Which state a ledger entry of the run leads to, published beside the state machine.

Every change of a run's or a step's state is recorded in the ledger in the same transaction as
the change itself (`docs/architecture/control-plane.md` §6). An entry carries a kind and an
outcome token, never the state. This table says which state each kind and outcome lead to, so
that whoever reads the ledger — the stream of changes of ADR-0055, every representation drawn
from it — reads it from one place and never derives it a second time.

An entry of a kind this table does not name changes no state: `step.assigned`,
`step.reserved`, `step.waited`, `budget.set`, `run.triggered`, `run.ended`, `run.lowered` and
every kind outside the run component. A step a person rejected (`step.declined`) is planned
again: resuming its run proposes it again (ADR-0110). Such an entry is not a change of state.
A take-over asked or refused (`step.takeover_asked`, `step.takeover_refused`) changes nothing
either; one served leads the step to wait for the person (`step.taken_over`), and one whose
lease lapsed gives it back to its worker at the checkpoint (`step.takeover_lapsed`, ADR-0128).
"""

from __future__ import annotations

from taktus.components.run.domain.model.run import DECLINE, RunState, StepState
from taktus.shared.v1 import Value


class Led(Value):
    """What one entry did to a run and to the step it names, if it names one."""

    run: RunState | None = None
    step: StepState | None = None


RUN_KINDS: dict[str, RunState] = {
    "run.created": RunState.PLANNED,
    "run.started": RunState.RUNNING,
    "run.resumed": RunState.RUNNING,
    "run.recovered": RunState.RUNNING,
    "run.waiting_human": RunState.WAITING_HUMAN,
    "run.halted": RunState.HALTED,
    "run.escalated": RunState.ESCALATED,
    "run.finished": RunState.FINISHED,
}
"""A run's entries: the kind alone says the state. `run.halted` and `run.escalated` carry the
cause as their outcome; the state is the same whatever the cause."""

STEP_KINDS: dict[str, StepState] = {
    "step.admitted": StepState.ADMITTED,
    "step.rejected": StepState.REJECTED,
    "step.started": StepState.RUNNING,
    "step.adopted": StepState.RUNNING,
    "step.failed": StepState.FAILED,
    "step.waiting": StepState.STOPPED,
    "step.awaiting": StepState.WAITING_HUMAN,
    "step.anchored": StepState.WAITING_HUMAN,
    "step.confirmed": StepState.PLANNED,
    "step.performed": StepState.SUCCEEDED,
    "step.declined": StepState.PLANNED,
    "step.taken_over": StepState.WAITING_HUMAN,
    "step.takeover_lapsed": StepState.STOPPED,
}
"""A step's entries whose kind alone says the state. `step.finished` and `step.decided` need
their outcome as well (`led_to`)."""

FINISHED_SUCCEEDED = frozenset({"succeeded", "rehearsed"})
"""The outcomes of `step.finished` of a step that succeeded; `rehearsed` is a step of a
rehearsal that answered from its recording (ADR-0030)."""
FINISHED_STOPPED = "stopped"
"""The outcome of `step.finished` of a step that stopped at its boundary. Every other outcome —
`failed`, `at_capacity`, `at_provider_limit` — is a step that failed."""

RECOVERED_STEP = StepState.STOPPED
"""`run.recovered` that names a step: the step the stopped instance was inside went back to its
last boundary."""


def led_to(kind: str, outcome: str | None) -> Led | None:
    """The state the entry of this kind and outcome led to, or None for an entry that changed
    no state of a run or a step."""
    if kind == "run.recovered":
        return Led(run=RunState.RUNNING, step=RECOVERED_STEP)
    if kind in RUN_KINDS:
        return Led(run=RUN_KINDS[kind])
    if kind in STEP_KINDS:
        return Led(step=STEP_KINDS[kind])
    if kind == "step.finished":
        if outcome in FINISHED_SUCCEEDED:
            return Led(step=StepState.SUCCEEDED)
        if outcome == FINISHED_STOPPED:
            return Led(step=StepState.STOPPED)
        return Led(step=StepState.FAILED)
    if kind == "step.decided":
        # Declined: the step is not run. Proceed: it is planned again, and runs at its level.
        return Led(step=StepState.REJECTED if outcome == DECLINE else StepState.PLANNED)
    return None


RECORDED_KINDS: frozenset[str] = frozenset(
    {*RUN_KINDS, *STEP_KINDS, "step.finished", "step.decided"}
)
"""Every kind of the run component that records a change of state."""
