"""A report's first level, and when a scheduled report is due (UC-6.2, ADR-0242). Pure.

The first level carries only what bears a decision or a consequence for its reader: a figure
outside its target, a decision waiting for the reader's role, an escalation, blocked work, and
for `owner` a process proposed to be switched off. A period with none of these is one sentence.
No item names a person: each names a process, a run, a request or a figure.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field

from taktus.components.reporting.domain.model.views import OWNER, ReportDefinition
from taktus.shared.v1 import Value


class Item(Value):
    kind: Literal["figure", "decision", "escalation", "blocked", "switch_off"]
    text: str = Field(min_length=1)
    ref: str = Field(min_length=1)


class ReportFacts(Value):
    """What the composition gathered for one reader role over one period."""

    reader: str
    since: datetime
    until: datetime
    missed: tuple[Item, ...] = ()
    """Figures outside their target, among those the reader is entitled to."""
    decisions: tuple[str, ...] = ()
    """Open decision requests whose decider is the reader role."""
    escalated: tuple[tuple[str, str], ...] = ()
    """Runs escalated in the period: run and process."""
    blocked: tuple[tuple[str, str, str], ...] = ()
    """Runs waiting for a person of the reader role: run, process, step."""
    switch_off: tuple[Item, ...] = ()


class Composed(Value):
    title: str
    items: tuple[Item, ...]
    lines: tuple[str, ...]
    quiet: bool


def period(d: ReportDefinition, now: datetime, since: datetime | None = None) -> datetime:
    """Where the period starts: the last delivery's slot if given, else a day or a week back."""
    if since is not None:
        return since
    return now - (timedelta(days=7) if d.every == "week" else timedelta(days=1))


def compose(d: ReportDefinition, facts: ReportFacts) -> Composed:
    items: list[Item] = [*facts.missed]
    items += [
        Item(kind="decision", ref=r, text=f"Decision request {r} waits for {facts.reader}.")
        for r in facts.decisions
    ]
    items += [
        Item(kind="escalation", ref=run, text=f"Run {run} of {process} escalated.")
        for run, process in facts.escalated
    ]
    items += [
        Item(
            kind="blocked",
            ref=run,
            text=f"Run {run} of {process} waits at {step} for {facts.reader}.",
        )
        for run, process, step in facts.blocked
    ]
    if d.reader_role == OWNER:
        items += list(facts.switch_off)
    when = f"{facts.since:%Y-%m-%d %H:%M} to {facts.until:%Y-%m-%d %H:%M} UTC"
    title = f"Report {d.id} for {facts.reader}, {when}"
    if not items:
        return Composed(
            title=title,
            items=(),
            lines=(f"Nothing was outside its range from {when}.",),
            quiet=True,
        )
    return Composed(
        title=title,
        items=tuple(items),
        lines=(
            title,
            *(f"- {i.text}" for i in items),
            "The detail is in your views and the figures (GET /views, GET /figures); reply here "
            "to ask or to act.",
        ),
        quiet=False,
    )


def due(d: ReportDefinition, now: datetime) -> str | None:
    """The slot due now, or None: a day's slot is its date once its hour has come, a week's
    its ISO week once its weekday and hour have; a slot already delivered is not due."""
    if d.trigger != "schedule" or d.hour is None:
        return None
    if now.hour < d.hour:
        return None
    if d.every == "day":
        slot = now.date().isoformat()
    else:
        if d.weekday is None or now.weekday() != d.weekday:
            return None
        year, week, _ = now.isocalendar()
        slot = f"{year}-W{week:02d}"
    return None if slot == d.last_slot else slot
