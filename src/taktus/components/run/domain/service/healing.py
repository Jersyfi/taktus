"""Whether Taktus heals a failed step on its own: level 4 within its frame (ADR-0160, UC-4.6).

At level 4 a person sets frame and goals and is drawn in only when the frame is exceeded
(UC-7.1 §1). A failure of a kind Taktus knows to heal, inside the frame, is therefore not a
person's: Taktus admits the step again — a retry — and reports it. Every other failure escalates
at the boundary, as it does at every level (UC-4.5).

A failure is healed when all of this holds, and escalates otherwise:

- the step runs at **level 4**: the process's level, and no action of the step set lower. A
  level-3 step's failure reaches the person on the loop, as before;
- the run is **no rehearsal**: a rehearsal is asked no level (NTC-0079);
- the failure is **of a kind Taktus knows**: the adapter classified it as one the same call
  may be repeated after (`retryable`). A failure nobody classified — a rule that failed, a check
  that disagreed, a worker's own failure — is not known, and is not healed;
- the step is **not blocked for want of an adapter**: a configuration that is missing is not
  healed by asking again (ADR-0046);
- a repeat **acts at most once**: an outward operation that cannot recognise a repeat
  (`idempotency: none`) is never repeated by Taktus on its own (ADR-0024);
- **no stop was requested**: a stop takes effect at the boundary, a heal does not pass it;
- the step was healed **fewer than `HEALS` times** in the run. Past it the failure escalates,
  and the escalation says what was tried.

A heal is admitted against the run's budget like any step (ADR-0005), so a heal that does not
fit is refused there and the run halts with cause `limit`. A failed step has produced nothing
that left the system, so a heal changes nothing outside it (ADR-0022).

Pure: the facts of one failure in, a verdict out.
"""

from __future__ import annotations

from pydantic import Field

from taktus.shared.v1 import AutonomyLevel, Value

HEALS = 2
"""How often one step is healed in one run before its failure escalates: the frame of a heal
(ADR-0160 §2)."""

UNATTENDED: AutonomyLevel = 4
"""The level at which Taktus heals on its own."""

HEALED = "step.healed"
"""The ledger kind of a heal: the step admitted again after a failure, by Taktus, with the
failure it answered by digest and `retry` as outcome."""

RETRY = "retry"


class Healing(Value):
    """Whether a failed step is healed, and why not where it is not."""

    heals: bool
    why_not: str | None = Field(default=None, min_length=1)
    """Why the failure escalates instead; None when it heals, and when the level asks no heal."""


def healing(
    level: AutonomyLevel,
    *,
    rehearsal: bool,
    retryable: bool | None,
    blocked: bool,
    repeatable: bool,
    stop_requested: bool,
    healed: int,
) -> Healing:
    """Whether a step that failed at `level` is healed by Taktus. `healed` is how often it was
    healed in the run already; `repeatable` whether its call may be made again without a second
    effect (always true for a step that calls nothing outward)."""
    if level < UNATTENDED or rehearsal:
        return Healing(heals=False)
    if stop_requested:
        return Healing(heals=False, why_not="a stop was requested, and a heal does not pass it")
    if retryable is not True:
        return Healing(
            heals=False,
            why_not="the failure is not of a kind Taktus knows to heal: no adapter classified "
            "it as one the same call may be repeated after",
        )
    if blocked:
        return Healing(
            heals=False,
            why_not="the step lacks an adapter, and asking again does not configure one",
        )
    if not repeatable:
        return Healing(
            heals=False,
            why_not="the operation cannot recognise a repeat (idempotency: none), and Taktus "
            "never repeats it on its own",
        )
    if healed >= HEALS:
        return Healing(
            heals=False,
            why_not=f"healed {healed} time(s) within the frame, and it failed again: the "
            "frame is exceeded",
        )
    return Healing(heals=True)
