"""A person's own view of what Taktus took off them (UC-13.5, UC-13.4, ADR-0245 §1). Pure.

A process relieves the reader where it names a role they hold — a step's, a fallback's, or a
role that would do it by hand. For each: its runs finished, the minutes a case takes by hand,
and the time regained, which is the process's own figure `value.time_saved_hours`, and the link
to its takeover instructions. Success is time and the goals the reader set: no points, levels,
streaks, ranks or comparisons. Only the reader reads it, unless they share it with a role.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime

from pydantic import Field

from taktus.components.reporting.domain.model.views import Goal, OwnView
from taktus.shared.v1 import Value


class Relieving(Value):
    """One process, as the composition hands it in."""

    process: str
    roles: tuple[str, ...]
    runs_finished: int = Field(ge=0)
    minutes_by_hand: float | None = None
    hours: float | None = None
    """The process's `value.time_saved_hours` over the period; None where it is withheld."""
    week_hours: float | None = None
    """The same figure over the last seven days."""
    takeover: str
    """Where its takeover instructions are read."""


class Relief(Value):
    process: str
    runs_finished: int
    minutes_by_hand: float | None
    hours_regained: float | None
    takeover: str
    roles: tuple[str, ...]


class Reached(Value):
    title: str
    hours_per_week: float
    hours_this_week: float
    reached: bool


class OwnRelief(Value):
    """The view itself: for `reader` alone (ADR-0015, protective rule)."""

    reader: str
    since: datetime
    until: datetime
    processes: tuple[Relief, ...]
    hours_regained: float
    hours_this_week: float
    goals: tuple[Reached, ...]
    shared_with: tuple[str, ...]
    sentence: str


def duration(hours: float) -> str:
    minutes = round(hours * 60)
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def relief(
    reader: str,
    roles: Collection[str],
    since: datetime,
    until: datetime,
    processes: Sequence[Relieving],
    settings: OwnView | None,
) -> OwnRelief:
    mine = [p for p in processes if any(r in roles for r in p.roles)]
    found = tuple(
        Relief(
            process=p.process,
            runs_finished=p.runs_finished,
            minutes_by_hand=p.minutes_by_hand,
            hours_regained=p.hours,
            takeover=p.takeover,
            roles=tuple(r for r in p.roles if r in roles),
        )
        for p in sorted(mine, key=lambda p: p.process)
    )
    total = sum(p.hours or 0.0 for p in mine)
    week = sum(p.week_hours or 0.0 for p in mine)
    goals: Sequence[Goal] = () if settings is None else settings.goals
    reached = tuple(
        Reached(
            title=g.title,
            hours_per_week=g.hours_per_week,
            hours_this_week=round(week, 6),
            reached=week >= g.hours_per_week,
        )
        for g in goals
    )
    runs = sum(p.runs_finished for p in mine)
    sentence = (
        f"Taktus took {runs} cases off your roles: {duration(total)} regained."
        if mine
        else "No process takes work off your roles yet."
    )
    return OwnRelief(
        reader=reader,
        since=since,
        until=until,
        processes=found,
        hours_regained=round(total, 6),
        hours_this_week=round(week, 6),
        goals=reached,
        shared_with=() if settings is None else settings.shared_with,
        sentence=sentence,
    )


def may_read(viewer_roles: Collection[str], settings: OwnView | None) -> bool:
    """Whether someone other than the person may read their view: only while the person
    shares it with a role the viewer holds."""
    return settings is not None and any(r in viewer_roles for r in settings.shared_with)


def line(view: OwnRelief) -> str:
    """The short line for the person's channel."""
    week = f"{duration(view.hours_this_week)} regained this week"
    met = [g.title for g in view.goals if g.reached]
    return f"{week}." + (f" Goal reached: {', '.join(met)}." if met else "")


LINE_HOUR = 8
"""The hour, in UTC, a person's line is said: daily, or on Mondays for a weekly line."""


def line_due(settings: OwnView, now: datetime) -> str | None:
    if settings.line == "never" or settings.channel is None or settings.address is None:
        return None
    if now.hour < LINE_HOUR or (settings.line == "week" and now.weekday() != 0):
        return None
    year, week, _ = now.isocalendar()
    slot = now.date().isoformat() if settings.line == "day" else f"{year}-W{week:02d}"
    return None if slot == settings.last_slot else slot
