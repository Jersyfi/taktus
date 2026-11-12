"""The coach's rules: which of a person's requests recur, and how many hints are due (ADR-0240).

A rule, never a model: the same requests give the same hints. A request is the intent of one of
the person's commands, as the channel recognised it or, failing that, as written, folded to lower
case with its spaces collapsed.

- **Every weekday.** The same request on the same weekday in at least `WEEKS` different weeks:
  "you ask this every Monday".
- **Often.** Otherwise, the same request at least `TIMES` times within `WINDOW_DAYS` days.

Pure: the commands in, the patterns and the due hints out.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from taktus.components.command.domain.model.coach import CoachHint, CoachSettings, HintState
from taktus.shared.v1 import Command

WEEKS = 3
TIMES = 4
WINDOW_DAYS = 28
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class Pattern:
    key: str
    says: str
    procedure: str


def request_of(command: Command) -> str:
    raw = command.intent.recognised or command.intent.raw
    return " ".join(raw.casefold().split())


def _key(request: str, cadence: str) -> str:
    return hashlib.sha256(f"{cadence}\n{request}".encode()).hexdigest()[:16]


def patterns(commands: Iterable[Command], identity: str, since: datetime) -> list[Pattern]:
    """The recurring requests among `identity`'s own commands received at or after `since`."""
    own = [c for c in commands if c.identity == identity and c.received_at >= since]
    by_request: dict[str, list[datetime]] = defaultdict(list)
    for command in own:
        request = request_of(command)
        if request:
            by_request[request].append(command.received_at)
    found: list[Pattern] = []
    for request, times in sorted(by_request.items()):
        weeks_by_day: dict[int, set[tuple[int, int]]] = defaultdict(set)
        for at in times:
            year, week, _ = at.isocalendar()
            weeks_by_day[at.weekday()].add((year, week))
        weekly = sorted(d for d, weeks in weeks_by_day.items() if len(weeks) >= WEEKS)
        if weekly:
            day = DAYS[weekly[0]]
            found.append(
                Pattern(
                    key=_key(request, f"every {day}"),
                    says=f'You ask "{request}" every {day}. Taktus can do it for you each {day}.',
                    procedure=f'every {day}: "{request}"',
                )
            )
            continue
        latest = max(times)
        recent = [t for t in times if latest - t <= timedelta(days=WINDOW_DAYS)]
        if len(recent) >= TIMES:
            found.append(
                Pattern(
                    key=_key(request, "often"),
                    says=(
                        f'You asked "{request}" {len(recent)} times in four weeks. '
                        "Taktus can do it whenever it is due."
                    ),
                    procedure=f'often, {len(recent)} times in {WINDOW_DAYS} days: "{request}"',
                )
            )
    return found


def due(
    settings: CoachSettings,
    found: Sequence[Pattern],
    hints: Sequence[CoachHint],
    now: datetime,
) -> list[Pattern]:
    """The patterns to offer now: none while the coach is off; never one the person was offered,
    accepted or dismissed before; and no more this week than the person allows."""
    if not settings.on or settings.hints_per_week == 0:
        return []
    known = {h.pattern for h in hints}
    year, week, _ = now.isocalendar()
    this_week = sum(
        1
        for h in hints
        if (h.offered_at.isocalendar()[0], h.offered_at.isocalendar()[1]) == (year, week)
    )
    room = max(settings.hints_per_week - this_week, 0)
    return [p for p in found if p.key not in known][:room]


def share(hints: Iterable[CoachHint]) -> tuple[int, int]:
    """Of the accepted hints that were checked, how many led to a lasting automation: (lasting,
    checked)."""
    checked = [h for h in hints if h.state is HintState.ACCEPTED and h.lasting is not None]
    return sum(1 for h in checked if h.lasting), len(checked)
