"""Which value is outside its corridor, and the words the daily report says it in (ADR-0109).

**A value counts** only when its step finished with outcome `succeeded`, its method is `rule`
or `statistics`, its exactness `exact` or `sourced`, and a provenance record of the step run
says so (§1). The number stands at the corridor's `select` in the result. A boolean is no
number.

**The thresholds** (§2). For `median`, each is a multiple of the median of the admissible values
within the window before the value judged; with fewer than the corridor's minimum, the corridor
cannot be computed. For `fixed`, each is a bound. A value beyond the red threshold is red, one
beyond the yellow and not the red is yellow, and one at a threshold is within it.

**Not measured.** The newest attempt failed, its value is not admissible or no number, no
attempt lies within `fresh` before now, or the median cannot be computed. A signal not measured
is never normal.

Nothing else decides: no model, no estimate, no reading of words (ADR-0023). Pure: the corridor,
the recorded attempts and the time in, the judgement out.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from taktus.components.reporting.domain.model.finding import short
from taktus.components.reporting.domain.model.signal import (
    ADMITTED,
    MEASURING,
    Corridor,
    Judged,
    Level,
    Recorded,
    Unmeasured,
)

DAILY_PREFIX = "signals-"
RED_PREFIX = "signal-red-"

REASONS: dict[str, str] = {
    "failed": "its newest attempt failed",
    "not_admissible": (
        "its newest value was not produced by a rule or statistics, exact or sourced, with a "
        "provenance record"
    ),
    "not_a_number": "its newest result holds no number where the corridor reads it",
    "no_measurement": "no attempt was recorded within the time the corridor allows",
    "too_little_history": "too few earlier values to compute its median",
}
"""One phrase per reason a signal could not be measured."""


def number(result: Any, select: str | None) -> float | None:
    """The number at the dotted path in the result; None when there is none there."""
    value = result
    for part in () if select is None else select.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def admissible(attempt: Recorded) -> bool:
    """Whether the attempt's value may be a signal's value (§1)."""
    return (
        attempt.succeeded
        and attempt.provenance
        and attempt.method in MEASURING
        and attempt.exactness in ADMITTED
    )


def values(corridor: Corridor, attempts: Iterable[Recorded]) -> list[tuple[Recorded, float]]:
    """The admissible attempts that hold a number, oldest first."""
    found: list[tuple[Recorded, float]] = []
    for attempt in sorted(attempts, key=lambda a: a.seq):
        if not admissible(attempt):
            continue
        value = number(attempt.result, corridor.select)
        if value is not None:
            found.append((attempt, value))
    return found


def thresholds(
    corridor: Corridor, before: Recorded, history: Sequence[tuple[Recorded, float]]
) -> tuple[float | None, float, float] | None:
    """The median, the yellow and the red threshold for a value recorded as `before`; None when
    the median cannot be computed. For fixed bounds the median is None."""
    if corridor.bounds == "fixed":
        return None, corridor.yellow, corridor.red
    since = before.at - corridor.window
    earlier = [v for a, v in history if a.seq < before.seq and since <= a.at < before.at]
    if len(earlier) < corridor.minimum:
        return None
    median = float(statistics.median(earlier))
    return median, median * corridor.yellow, median * corridor.red


def level(corridor: Corridor, value: float, yellow_at: float, red_at: float) -> Level:
    """Beyond is strict: a value at a threshold is within it."""
    if corridor.direction == "above":
        if value > red_at:
            return Level.RED
        return Level.YELLOW if value > yellow_at else Level.NORMAL
    if value < red_at:
        return Level.RED
    return Level.YELLOW if value < yellow_at else Level.NORMAL


def judge(corridor: Corridor, attempts: Sequence[Recorded], now: datetime) -> Judged:
    """The signal's newest attempt, judged against its corridor."""
    ordered = sorted(attempts, key=lambda a: a.seq)
    if not ordered or ordered[-1].at < now - corridor.fresh:
        return _unmeasured(corridor, "no_measurement", ordered[-1] if ordered else None)
    newest = ordered[-1]
    if not newest.succeeded:
        return _unmeasured(corridor, "failed", newest)
    if not admissible(newest):
        return _unmeasured(corridor, "not_admissible", newest)
    value = number(newest.result, corridor.select)
    if value is None:
        return _unmeasured(corridor, "not_a_number", newest)
    return judged_value(corridor, newest, value, values(corridor, ordered))


def judged_value(
    corridor: Corridor,
    attempt: Recorded,
    value: float,
    history: Sequence[tuple[Recorded, float]],
) -> Judged:
    """One admissible value judged against the values recorded before it."""
    found = thresholds(corridor, attempt, history)
    if found is None:
        judged = _unmeasured(corridor, "too_little_history", attempt)
        return judged.model_copy(update={"value": value})
    median, yellow_at, red_at = found
    return Judged(
        signal=corridor.signal,
        corridor=corridor.id,
        level=level(corridor, value, yellow_at, red_at),
        value=value,
        median=median,
        yellow_at=yellow_at,
        red_at=red_at,
        **_where(attempt),
    )


def series(corridor: Corridor, attempts: Sequence[Recorded]) -> list[Judged]:
    """Every admissible value of a series, each judged against the values before it."""
    history = values(corridor, attempts)
    return [judged_value(corridor, a, v, history) for a, v in history]


def _where(attempt: Recorded | None) -> dict[str, Any]:
    if attempt is None:
        return {}
    return {
        "run_id": attempt.run_id,
        "step_id": attempt.step_id,
        "process_version": attempt.process_version,
        "at": attempt.at,
    }


def _unmeasured(corridor: Corridor, reason: Unmeasured, attempt: Recorded | None) -> Judged:
    return Judged(
        signal=corridor.signal,
        corridor=corridor.id,
        level=Level.UNMEASURED,
        reason=reason,
        **_where(attempt),
    )


# --- identifiers -------------------------------------------------------------------------------


def daily_id(day: datetime) -> str:
    return DAILY_PREFIX + day.strftime("%Y%m%d")


def red_id(incident: str, judged: Judged) -> str:
    """Derived from the incident and the run, never stored: one report per red value."""
    return RED_PREFIX + short(f"{incident}|{judged.run_id}|{judged.step_id}")


def intervention_id(process: str) -> str:
    return f"start:{process}"


def intervened(option: str) -> str | None:
    """The process an option starts; None for an option that starts none."""
    return option.removeprefix("start:") if option.startswith("start:") else None


# --- words -------------------------------------------------------------------------------------


def _figure(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def _at(moment: datetime | None) -> str:
    return "never" if moment is None else moment.isoformat(timespec="seconds")


def measured_by(judged: Judged, run_url: str | None) -> str:
    """Where the value comes from: the run and the step, and the run's page where it is known."""
    if judged.run_id is None:
        return "No run measured it."
    where = f"Run {judged.run_id}, step {judged.step_id}, at {_at(judged.at)}"
    return where + (f": {run_url}." if run_url is not None else ".")


def line(
    corridor: Corridor,
    judged: Judged,
    *,
    run_url: str | None,
    incident: str | None = None,
) -> str:
    """One line of the daily report: what the signal is, why it is listed, where it was
    measured and where its case is worked."""
    if judged.level is Level.UNMEASURED:
        why = REASONS[judged.reason or "no_measurement"]
        head = f"NOT MEASURED {corridor.signal}: {why}."
    else:
        word = "RED" if judged.level is Level.RED else "YELLOW"
        threshold = judged.red_at if judged.level is Level.RED else judged.yellow_at
        side = "above" if corridor.direction == "above" else "below"
        head = (
            f"{word} {corridor.signal}: {_figure(judged.value)} is {side} the "
            f"{word.lower()} threshold {_figure(threshold)}"
        )
        if judged.median is not None:
            head += f" ({_figure(corridor.yellow if word == 'YELLOW' else corridor.red)} times "
            head += f"the median {_figure(judged.median)} of {_days(corridor)})"
        head += "."
    parts = [head, measured_by(judged, run_url)]
    if incident is not None:
        parts.append(f"Incident {incident}.")
    parts.append(f"Case: {corridor.case}")
    return " ".join(parts)


def _days(corridor: Corridor) -> str:
    seconds = corridor.window.total_seconds()
    if seconds % 86400 == 0:
        days = int(seconds // 86400)
        return f"{days} day" + ("" if days == 1 else "s")
    return f"{seconds / 3600:g} hours"


def daily_title(day: datetime, deviating: int, unmeasured: int) -> str:
    date = day.date().isoformat()
    if not deviating and not unmeasured:
        return f"Signals of {date}: every signal within its corridor"
    return f"Signals of {date}: {deviating} outside their corridor, {unmeasured} not measured"


def nothing_deviates(measured: int, unmeasured: int) -> str:
    """The line that says no signal left its corridor; never that one not measured is normal."""
    if unmeasured:
        return (
            f"No signal left its corridor: {measured} measured within it, {unmeasured} not "
            "measured."
        )
    signals = "the one signal was" if measured == 1 else f"all {measured} signals were"
    return f"Nothing left its corridor: {signals} measured within it."
