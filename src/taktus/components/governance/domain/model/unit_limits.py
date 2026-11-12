"""A limit per unit of the organisation's structure, and the rules that watch it (ADR-0282).

A **unit limit** is a named line for one unit of a tenant's structure: the company (the empty
path), a department or a team below it. It may hold each person of the unit on their own, and it
may name a process; it never names a person (principle 14).
It holds money per currency, compute seconds or tokens per period — a day, an ISO week or a
calendar month, in UTC. Every limit on a run's path holds the run; a child never lets a step
through its parent (UC-8.5, UC-8.10).

The rules here are rules and statistics, never a model (ADR-0023): the forecast is a band from
the mean and deviation of the days so far; an anomaly is a day far above the robust median of
the days before it; a limit does harm where it held more runs or longer than the tenant's watch.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import Value
from taktus.shared.v1.consumption import CurrencyAmounts

NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
"""A limit's name, as the ledger's outcome carries it."""
UNIT_PART = r"^[^/\s][^/]{0,199}$"

type Period = Literal["day", "week", "month"]
type Policy = Literal["halt", "wait"]
type Children = Literal["within", "over"]

ALERT_SHARE = 0.8
"""The share of an amount at which the role is warned, where the tenant names none (ADR-0282)."""
HISTORY_DAYS = 28
"""The days before the period an anomaly is judged against."""
ANOMALY_MINIMUM = 7
"""Days with a cost needed before a day can be an anomaly."""
ANOMALY_DEVIATIONS = 3.5
MAD_SCALE = 1.4826
"""The median absolute deviation times this estimates the standard deviation (ADR-0282 §3)."""


class Amounts(Value):
    """What a limit holds per period: one kind or more."""

    money: CurrencyAmounts | None = None
    compute_seconds: float | None = Field(default=None, gt=0)
    tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _at_least_one(self) -> Amounts:
        if self.money is None and self.compute_seconds is None and self.tokens is None:
            raise ValueError("a limit holds money, compute seconds or tokens")
        if self.money is not None and not self.money:
            raise ValueError("a money limit names at least one currency")
        return self

    def lines(self) -> dict[str, float]:
        """Every line by its key: `money.<currency>`, `compute_seconds`, `tokens`."""
        found: dict[str, float] = {f"money.{c}": float(v) for c, v in (self.money or {}).items()}
        if self.compute_seconds is not None:
            found["compute_seconds"] = float(self.compute_seconds)
        if self.tokens is not None:
            found["tokens"] = float(self.tokens)
        return found


class UnitLimit(Value):
    """One limit, stored under its name."""

    id: str = Field(pattern=NAME_PATTERN)
    tenant: str = Field(min_length=1)
    unit: tuple[str, ...] = ()
    """The unit's path below the tenant; empty for the company."""
    individually: bool = False
    """Each person of the unit is held to the amount on their own, by the runs they
    commissioned (DEC-0069). The limit names no one, and what one person spent is shown only to
    that person (ADR-0282 §6)."""
    process: str | None = Field(default=None, min_length=1)
    """A process id: the limit holds only its runs."""
    period: Period = "month"
    amounts: Amounts
    policy: Policy = "halt"
    alert_at: tuple[float, ...] = (ALERT_SHARE,)
    role: str = Field(min_length=1)
    """Who owns the limit and is told: a role, never a person (principle 14)."""
    children: Children = "within"
    check_every_seconds: int = Field(default=900, ge=1)
    configured_at: datetime
    cleared: bool = False
    """Taken away: it holds nothing, and its row is kept, as nothing is deleted unasked."""

    @model_validator(mode="after")
    def _holds(self) -> UnitLimit:
        for part in self.unit:
            if not re.match(UNIT_PART, part):
                raise ValueError(f"{part!r} is not one level of the structure")
        if any(not 0 < share <= 1 for share in self.alert_at):
            raise ValueError("an alert share lies above 0 and at most 1")
        return self

    @property
    def name(self) -> str:
        return self.id

    def where(self) -> str:
        """The unit it comes from, as a reader names it."""
        return "/".join(self.unit) if self.unit else "company"

    def applies(self, path: Sequence[str], process: str) -> bool:
        """Whether the limit holds a run of this path and process."""
        if tuple(path[: len(self.unit)]) != self.unit:
            return False
        return self.process is None or self.process == process

    def is_parent_of(self, other: UnitLimit) -> bool:
        """Whether `other` is set below this limit, for the same period and scope."""
        return (
            other.id != self.id
            and not self.individually
            and len(other.unit) >= len(self.unit)
            and other.unit[: len(self.unit)] == self.unit
            and (other.unit != self.unit or other.individually)
            and other.period == self.period
            and self.process in (None, other.process)
        )


class LimitWatch(Value):
    """One tenant's figures for a limit that does harm, stored under the tenant (ADR-0282 §4)."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    held_runs: int | None = Field(default=None, ge=1)
    held_seconds: float | None = Field(default=None, gt=0)
    window_days: int = Field(default=7, ge=1, le=366)
    configured_at: datetime

    @model_validator(mode="after")
    def _a_figure(self) -> LimitWatch:
        if self.held_runs is None and self.held_seconds is None:
            raise ValueError("a watch names the runs held or the seconds held")
        return self


# --- periods ----------------------------------------------------------------------------------


def period_of(period: Period, now: datetime) -> tuple[str, datetime, datetime]:
    """The period's key, its first instant and the first instant of the next, in UTC."""
    at = now.astimezone(UTC)
    day = datetime(at.year, at.month, at.day, tzinfo=UTC)
    if period == "day":
        return f"{at:%Y-%m-%d}", day, day + timedelta(days=1)
    if period == "week":
        start = day - timedelta(days=at.weekday())
        year, week, _ = at.isocalendar()
        return f"{year}-W{week:02d}", start, start + timedelta(days=7)
    start = datetime(at.year, at.month, 1, tzinfo=UTC)
    following = (
        datetime(at.year + 1, 1, 1, tzinfo=UTC)
        if at.month == 12
        else datetime(at.year, at.month + 1, 1, tzinfo=UTC)
    )
    return f"{at:%Y-%m}", start, following


# --- the forecast -----------------------------------------------------------------------------


class Forecast(Value):
    """A band, never a point, and what it was computed from (UC-8.5 §2)."""

    line: str
    low: float
    high: float
    days: int
    first_day: date | None
    last_day: date | None
    reached_earliest: date | None
    """The earliest day the amount is reached, at the band's upper edge; None if not within the
    period."""
    reached_latest: date | None
    """The latest day, at the band's lower edge; None if not within the period."""
    basis: str


def forecast(
    line: str,
    amount: float,
    spent: float,
    daily: Mapping[date, float],
    start: datetime,
    end: datetime,
    now: datetime,
) -> Forecast:
    """The period's cost as a band: the rest of the period at the mean daily cost less and plus
    one standard deviation of the days so far, never below what is spent."""
    today = now.astimezone(UTC).date()
    days = [start.date() + timedelta(days=i) for i in range((today - start.date()).days + 1)]
    values = [daily.get(d, 0.0) for d in days]
    mean = statistics.fmean(values) if values else 0.0
    deviation = statistics.pstdev(values) if len(values) > 1 else 0.0
    remaining = max(0.0, (end - now).total_seconds() / 86400.0)
    low = spent + remaining * max(0.0, mean - deviation)
    high = spent + remaining * (mean + deviation)

    def when(rate: float) -> date | None:
        if spent >= amount:
            return today
        if rate <= 0:
            return None
        at = now + timedelta(days=(amount - spent) / rate)
        return at.date() if at < end else None

    return Forecast(
        line=line,
        low=round(low, 6),
        high=round(high, 6),
        days=len(values),
        first_day=days[0] if days else None,
        last_day=days[-1] if days else None,
        reached_earliest=when(mean + deviation),
        reached_latest=when(max(0.0, mean - deviation)),
        basis=(
            f"the cost of {len(values)} day(s) of the period, {days[0]} to {days[-1]}, from the "
            "runs' recorded consumption: the rest of the period at their mean less and plus one "
            "standard deviation; runs planned or expected are not counted"
        ),
    )


# --- the anomaly ------------------------------------------------------------------------------


class Anomaly(Value):
    day: date
    cost: float
    median: float
    deviation: float
    threshold: float
    history_days: int


def anomalous(day: date, cost: float, history: Sequence[float]) -> Anomaly | None:
    """A day whose cost lies more than 3.5 robust deviations above the median of the days
    before it, given at least 7 days with a cost. A statistic over the ledger, never a model."""
    if cost <= 0:
        return None
    with_cost = [v for v in history if v > 0]
    if len(with_cost) < ANOMALY_MINIMUM:
        return None
    median = statistics.median(history)
    mad = statistics.median([abs(v - median) for v in history]) * MAD_SCALE
    # A history of identical days has no deviation: a tenth of its median stands in for it.
    spread = mad if mad > 0 else max(median * 0.1, 1e-9)
    threshold = median + ANOMALY_DEVIATIONS * spread
    if cost <= threshold:
        return None
    return Anomaly(
        day=day,
        cost=round(cost, 6),
        median=round(median, 6),
        deviation=round(spread, 6),
        threshold=round(threshold, 6),
        history_days=len(history),
    )


# --- the harm ---------------------------------------------------------------------------------


class Held(Value):
    """One hold of a run at a limit, as the ledger records it."""

    run_id: str
    process: str
    since: datetime
    seconds: float


class Harm(Value):
    runs: int
    processes: tuple[str, ...]
    seconds: float
    exceeded: Literal["runs", "seconds", "both"]
    """Which figure of the watch was reached."""


def harm(holds: Sequence[Held], watch: LimitWatch) -> Harm | None:
    """Whether a limit held more runs, or longer, than the tenant's watch allows."""
    runs = len({h.run_id for h in holds})
    seconds = sum(h.seconds for h in holds)
    by_runs = watch.held_runs is not None and runs >= watch.held_runs
    by_seconds = watch.held_seconds is not None and seconds >= watch.held_seconds
    if not (by_runs or by_seconds):
        return None
    return Harm(
        runs=runs,
        processes=tuple(sorted({h.process for h in holds})),
        seconds=round(seconds, 3),
        exceeded="both" if by_runs and by_seconds else "runs" if by_runs else "seconds",
    )
