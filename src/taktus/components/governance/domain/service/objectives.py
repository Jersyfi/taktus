"""A process's service-level objectives, and a failure healed again and again (UC-4.6,
ADR-0254). Pure rules over what the ledger recorded; no I/O, never a model.

**Objectives.** A process may promise how long a run takes (`slo.latency`) and the least share
of its ended runs that finish (`slo.completion`). Every ended run is measured against both: its
duration from `run.created` to its end against the first, and the share of the process's last
`COMPLETION_WINDOW` ended runs, itself included, that finished against the second. A run that
misses one is recorded with the objectives it missed.

**Recurrence.** A heal answers a failure of a known kind (ADR-0160). The same failure — the same
step of the same process, answered for the same reason — healed `limit` times is a design fault,
and Taktus says so. The limit is the process's, at least one: it cannot be switched off.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta

COMPLETION_WINDOW = 20
"""How many of a process's most recent ended runs its share of completed runs is taken over."""
HEAL_LIMIT = 3
"""How often the same failure is healed before Taktus says it is a design fault, by default."""
MET = "met"


def missed(
    duration: timedelta | None,
    recent: Sequence[bool],
    *,
    latency: timedelta | None,
    completion: float | None,
) -> tuple[str, ...]:
    """The objectives a run missed: `latency` when it took longer than promised, `completion`
    when the share of finished runs among `recent` — the process's last ended runs, this one
    included, True for a run that finished — fell below the promise. A run whose duration
    cannot be read is measured on completion only."""
    found: list[str] = []
    if latency is not None and duration is not None and duration > latency:
        found.append("latency")
    if completion is not None and recent:
        window = recent[-COMPLETION_WINDOW:]
        if sum(window) / len(window) < completion:
            found.append("completion")
    return tuple(found)


def outcome(objectives: Sequence[str]) -> str:
    """The token `slo.measured` records: `met`, or `missed_` with the objectives missed."""
    return MET if not objectives else "missed_" + "_".join(objectives)


@dataclass(frozen=True)
class Heal:
    """One `step.healed`: the process, the step, and the failure it answered by digest."""

    process: str
    step: str
    failure: str


@dataclass(frozen=True)
class Recurring:
    process: str
    step: str
    failure: str
    count: int


def recurring(heals: Iterable[Heal], limits: dict[str, int]) -> list[Recurring]:
    """Every failure healed at least its process's limit of times, in the order its limit was
    reached. A process without a limit of its own holds `HEAL_LIMIT`."""
    counts: dict[tuple[str, str, str], int] = {}
    reached: list[tuple[str, str, str]] = []
    for heal in heals:
        key = (heal.process, heal.step, heal.failure)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] == max(1, limits.get(heal.process, HEAL_LIMIT)):
            reached.append(key)
    return [Recurring(p, s, f, counts[(p, s, f)]) for p, s, f in reached]
