"""Which processes Taktus proposes, in which order and why (UC-4.4, ADR-0270). Pure.

Two kinds of recurring work are found, each by a rule over records:

- **started by hand** — the same identity started the same process without a trigger at least
  `MINIMUM` times in the last `WINDOW`, at a regular cadence: every gap between two starts lies
  within `SPREAD` of the median gap from it. The proposal takes over the starting;
- **healed again and again** — a process whose same failure was healed its limit of times
  (`heal.recurred`, ADR-0254). The proposal takes over the fault's removal.

A proposal says the work it would take over, what it would cost to run, why it is proposed now,
and the words its acceptance hands on — nothing else. The list is ordered by how often the work
recurs per 30 days, most often first, and each proposal says so. A proposal drawn from runs a
person started is that person's alone (principle 14): `visible` shows it to nobody else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from statistics import median
from typing import Literal

MINIMUM = 3
"""The fewest starts by hand that make a cadence."""
WINDOW = timedelta(days=90)
"""How far back starts by hand are read."""
SPREAD = 0.5
"""How far a gap may lie from the median gap, as a share of it, for the cadence to be regular."""
MONTH = timedelta(days=30)

type Kind = Literal["by_hand", "healed"]


@dataclass(frozen=True)
class Start:
    """A run started without a trigger: by whom, of which process, and when. What it consumed is
    not held here, beside a person: the cost is the process's (`costs`), over all its runs."""

    process_id: str
    process_name: str
    identity: str
    at: datetime


@dataclass(frozen=True)
class Recurrence:
    """A failure of a step healed its process's limit of times (ADR-0254 §2)."""

    process_id: str
    process_name: str
    step: str
    failure: str
    """The failure's reason, as a heal recorded it."""
    healed: int
    """How often it was healed in all."""
    recent: int
    """How often it was healed in the last 30 days: how often it recurs per 30 days."""
    at: datetime
    used: Mapping[str, float] = field(default_factory=dict)
    """What a run of the process consumed, on average, by quantity name."""


@dataclass(frozen=True)
class ProcessProposal:
    id: str
    kind: Kind
    process_id: str
    takes_over: str
    """The work it would take over, in words."""
    cost: str
    """What it would cost to run: per run, and per 30 days."""
    why_now: str
    """The evidence, in words: how often, at which cadence, the newest when."""
    per_month: float
    """How often the work recurs per 30 days: what the list is ordered by."""
    order: str
    """The order's reason, in words."""
    words: str
    """What accepting hands to the request path of ADR-0251 §1."""
    reader: str | None
    """The only identity that reads it: the person whose starts it is drawn from. None for a
    proposal that concerns no person, which every identity of the tenant reads."""


def proposals(
    starts: Iterable[Start],
    recurrences: Iterable[Recurrence],
    now: datetime,
    costs: Mapping[str, Mapping[str, float]] | None = None,
) -> list[ProcessProposal]:
    """Every proposal, most often recurring first. `costs` is what a run of each process
    consumed on average, by quantity name, over all its runs: a process's cost, never a
    person's."""
    found = [*_by_hand(starts, now, costs or {}), *(_healed(r) for r in recurrences)]
    return sorted(found, key=lambda p: (-p.per_month, p.id))


def visible(found: Iterable[ProcessProposal], viewer: str) -> list[ProcessProposal]:
    """What `viewer` is shown: every proposal that concerns no person, and the viewer's own."""
    return [p for p in found if p.reader is None or p.reader == viewer]


def identifier(*about: str) -> str:
    """A proposal's identifier, derived from what it is about: the same work, the same id."""
    return "pp_" + hashlib.sha256("\n".join(about).encode("utf-8")).hexdigest()[:16]


def _by_hand(
    starts: Iterable[Start], now: datetime, costs: Mapping[str, Mapping[str, float]]
) -> list[ProcessProposal]:
    grouped: dict[tuple[str, str], list[Start]] = {}
    for start in starts:
        if now - start.at <= WINDOW:
            grouped.setdefault((start.identity, start.process_id), []).append(start)
    found: list[ProcessProposal] = []
    for (identity, process_id), group in sorted(grouped.items()):
        if len(group) < MINIMUM:
            continue
        group.sort(key=lambda s: s.at)
        gaps = [(b.at - a.at).total_seconds() for a, b in pairwise(group)]
        typical = median(gaps)
        if typical <= 0 or any(abs(g - typical) > SPREAD * typical for g in gaps):
            continue
        cadence = timedelta(seconds=typical)
        per_month = MONTH / cadence
        name = group[-1].process_name
        found.append(
            ProcessProposal(
                id=identifier("by_hand", identity, process_id),
                kind="by_hand",
                process_id=process_id,
                takes_over=f"starting {name} by hand, about {_every(cadence)}",
                cost=_cost([costs[process_id]] if process_id in costs else [], per_month),
                why_now=(
                    f"started by hand {len(group)} times in the last {WINDOW.days} days, "
                    f"about {_every(cadence)}, the newest on {group[-1].at.date().isoformat()}"
                ),
                per_month=per_month,
                order=_order(per_month),
                words=(
                    f"Start {name} on a schedule, {_every(cadence)}, with the inputs of its "
                    "newest run, instead of by hand."
                ),
                reader=identity,
            )
        )
    return found


def _healed(recurrence: Recurrence) -> ProcessProposal:
    per_month = float(recurrence.recent)
    return ProcessProposal(
        id=identifier("healed", recurrence.process_id, recurrence.step, recurrence.failure),
        kind="healed",
        process_id=recurrence.process_id,
        takes_over=(
            f"removing the cause of a failure of step {recurrence.step} of "
            f"{recurrence.process_name} that Taktus heals again and again"
        ),
        cost=_cost([recurrence.used], 1.0, unit="a run of the changed process"),
        why_now=(
            f"the failure {recurrence.failure!r} was healed {recurrence.healed} times, the "
            f"limit was reached on {recurrence.at.date().isoformat()}: a design fault (UC-4.6)"
        ),
        per_month=per_month,
        order=_order(per_month),
        words=(
            f"Step {recurrence.step} fails again and again with {recurrence.failure!r}, and is "
            "healed each time. Change the process so that it no longer fails this way."
        ),
        reader=None,
    )


def _every(cadence: timedelta) -> str:
    days = cadence.total_seconds() / 86400
    if days >= 1:
        return f"every {days:.1f} days".replace(".0 days", " days")
    return f"every {cadence.total_seconds() / 3600:.1f} hours".replace(".0 hours", " hours")


def _order(per_month: float) -> str:
    return f"recurs {per_month:.1f} times per 30 days"


def _cost(used: Sequence[Mapping[str, float]], per_month: float, *, unit: str = "a run") -> str:
    names = sorted({name for each in used for name in each})
    if not used or not names:
        return f"not measured: no run it draws on recorded what it used, per {unit}"
    mean = {name: sum(each.get(name, 0.0) for each in used) / len(used) for name in names}
    per = ", ".join(f"{name} {mean[name]:g}" for name in names)
    month = ", ".join(f"{name} {mean[name] * per_month:g}" for name in names)
    return f"per {unit}: {per}; per 30 days: {month}"
