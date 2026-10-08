"""When a schedule trigger is due (ADR-0035).

A schedule is a five-field cron expression — minute, hour, day of month, month, day of week —
read in UTC, or one of four names for a common one. A **slot** is a minute the expression
matches. The scheduler asks one question of a schedule: what is the latest slot at or before
this moment. A trigger is due when that slot is later than the last slot it fired for, and
later than the moment the scheduler first saw it. Missed slots therefore start one run, for
the latest of them, never one per slot missed.

Fields take `*`, a number, a range `a-b`, a step `*/n` or `a-b/n`, and lists of these separated
by commas. Day of week runs from 0 (Sunday) to 7 (Sunday again). When both day of month and
day of week are restricted, a day matching either is matched, as in every cron.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

NAMED = {
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 1",  # Monday, 00:00 UTC: the start of the ISO week
    "monthly": "0 0 1 * *",
}

# How far back the latest slot is looked for. Every expression matches at least once in four
# years (29 February); one that does not is refused when it is read.
HORIZON_DAYS = 4 * 366 + 1

_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_NAMES = ("minute", "hour", "day of month", "month", "day of week")


class InvalidSchedule(ValueError):
    pass


@dataclass(frozen=True)
class Schedule:
    expression: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 is Sunday; 7 is folded into 0
    days_restricted: bool
    weekdays_restricted: bool

    def latest(self, at: datetime) -> datetime | None:
        """The latest slot at or before `at`, or None when there is none within the horizon."""
        at = at.astimezone(UTC).replace(second=0, microsecond=0)
        day = at.date()
        for back in range(HORIZON_DAYS):
            candidate = day - timedelta(days=back)
            if not self._matches_day(candidate):
                continue
            last_hour = at.hour if back == 0 else 23
            for hour in sorted((h for h in self.hours if h <= last_hour), reverse=True):
                last_minute = at.minute if back == 0 and hour == at.hour else 59
                minutes = [m for m in self.minutes if m <= last_minute]
                if minutes:
                    return datetime(
                        candidate.year,
                        candidate.month,
                        candidate.day,
                        hour,
                        max(minutes),
                        tzinfo=UTC,
                    )
        return None

    def _matches_day(self, day: date) -> bool:
        if day.month not in self.months:
            return False
        in_month = day.day in self.days
        in_week = day.isoweekday() % 7 in self.weekdays
        if self.days_restricted and self.weekdays_restricted:
            return in_month or in_week
        return in_month and in_week


def parse(text: str) -> Schedule:
    """The schedule a trigger names, or InvalidSchedule saying what is wrong with it."""
    expression = NAMED.get(text.strip(), text.strip())
    fields = expression.split()
    if len(fields) != 5:
        raise InvalidSchedule(
            f"{text!r} is not a schedule: name one of {', '.join(NAMED)}, or give five cron "
            "fields — minute, hour, day of month, month, day of week — read in UTC"
        )
    values = [
        _field(field, bounds, name)
        for field, bounds, name in zip(fields, _BOUNDS, _NAMES, strict=True)
    ]
    schedule = Schedule(
        expression=expression,
        minutes=values[0],
        hours=values[1],
        days=values[2],
        months=values[3],
        weekdays=frozenset(d % 7 for d in values[4]),
        days_restricted=fields[2] != "*",
        weekdays_restricted=fields[4] != "*",
    )
    if not any(schedule._matches_day(_day(back)) for back in range(HORIZON_DAYS)):
        raise InvalidSchedule(f"{text!r} matches no day; a schedule that never fires is a mistake")
    return schedule


def _day(back: int) -> date:
    # Four years from a fixed leap day cover every day of month on every weekday.
    return date(2028, 12, 31) - timedelta(days=back)


def _field(text: str, bounds: tuple[int, int], name: str) -> frozenset[int]:
    low, high = bounds
    found: set[int] = set()
    for part in text.split(","):
        body, _, step_text = part.partition("/")
        try:
            step = int(step_text) if step_text else 1
            if body == "*":
                first, last = low, high
            elif "-" in body:
                start, _, end = body.partition("-")
                first, last = int(start), int(end)
            else:
                first = last = int(body)
                if step_text:
                    last = high
        except ValueError:
            raise InvalidSchedule(
                f"the {name} field {text!r} is not a number, range or step"
            ) from None
        if step < 1 or not low <= first <= last <= high:
            raise InvalidSchedule(f"the {name} field {text!r} lies outside {low} to {high}")
        found.update(range(first, last + 1, step))
    return frozenset(found)
