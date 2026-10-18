"""The rule over decisions on proposals: the correction rate, when a raise is proposed, and when
a level falls (ADR-0110, UC-7.5). Pure: ledger entries and the tenant's limits in, figures and
verdicts out.

**What is read.** Four kinds of the tenant's ledger, rehearsals left out:

- `proposal.decided`: one decision, its outcome, its process version and its action class;
- `autonomy.lowered`: a level lowered by rule, the new level as outcome (`level_2`), for the
  version and the action class it names;
- `autonomy.raised`: a person's approved raise of a process's levels (ADR-0039);
- `autonomy.proposed`: a raise Taktus proposed, here with outcome `corrections`.

**The rate.** A unit's decisions are counted over a window that ends now, and from the unit's
last change of level, whichever is later. A unit changes level when it is lowered, or when its
process is raised. The rate is corrected and rejected over all decided. Nothing decided is no
rate at all, not a rate of nought.

**Down.** After a decision, the unit falls one level when, over the tenant's window, at least its
minimum of decisions were counted and the rate is above its limit. A process that breached an
anchor falls one level whatever its rate. Neither ever goes below level 1.

**Up.** After a decision, Taktus proposes a raise of the unit when at least the tenant's number of
decisions were counted within 28 days, the first of them is at least the tenant's number of
weeks old, and the rate over 7 days and over 28 is below the tenant's limit for a raise. It
proposes once per change of level. It never applies a raise (UC-7.1).

Nothing else decides: no model, no estimate, no reading of words (ADR-0023).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta

from taktus.components.governance.domain.model.corrections import (
    CorrectionLimits,
    Decided,
    Figures,
    Lowered,
    Outcome,
    Rate,
    Unit,
)
from taktus.shared.v1 import AutonomyLevel, LedgerEntry

DECIDED = "proposal.decided"
LOWERED = "autonomy.lowered"
RAISED = "autonomy.raised"
PROPOSED = "autonomy.proposed"
LOWERED_RUN = "run.lowered"
KINDS = (DECIDED, LOWERED, RAISED, PROPOSED)
"""Every kind the rule reads."""

PROPOSED_BY_CORRECTIONS = "corrections"
"""The outcome of an `autonomy.proposed` entry this rule records."""

WEEK = timedelta(days=7)
MONTH = timedelta(days=28)

LEVEL_PREFIX = "level_"


def level_outcome(level: AutonomyLevel) -> str:
    return f"{LEVEL_PREFIX}{level}"


def level_of(outcome: str | None) -> AutonomyLevel | None:
    """The level an `autonomy.lowered` outcome names; None for any other token."""
    if outcome is None or not outcome.startswith(LEVEL_PREFIX):
        return None
    digits = outcome.removeprefix(LEVEL_PREFIX)
    if digits not in ("1", "2", "3"):
        return None
    level: AutonomyLevel = int(digits)  # type: ignore[assignment]
    return level


def process_of(version: str) -> str:
    return version.rsplit("@", 1)[0]


def unit_of(entry: LedgerEntry) -> Unit | None:
    version = entry.refs.process_version
    if version is None:
        return None
    return Unit(process_id=process_of(version), action=entry.refs.action)


def decisions(entries: Iterable[LedgerEntry]) -> list[Decided]:
    """Every `proposal.decided` entry as the rate reads it, in sequence order."""
    found: list[Decided] = []
    for entry in entries:
        if entry.kind != DECIDED or entry.rehearsal:
            continue
        unit = unit_of(entry)
        if unit is None or entry.refs.process_version is None:
            continue
        try:
            outcome = Outcome(entry.outcome or "")
        except ValueError:
            continue
        found.append(
            Decided(
                seq=entry.seq,
                at=entry.ts,
                unit=unit,
                process_version=entry.refs.process_version,
                outcome=outcome,
            )
        )
    return sorted(found, key=lambda d: d.seq)


def changed_at(entries: Iterable[LedgerEntry], unit: Unit) -> datetime | None:
    """The unit's last change of level: a lowering of the unit itself, or a raise of its
    process, which changes every level of it."""
    newest: datetime | None = None
    for entry in entries:
        if entry.rehearsal or entry.kind not in (LOWERED, RAISED):
            continue
        version = entry.refs.process_version
        if version is None or process_of(version) != unit.process_id:
            continue
        if entry.kind == LOWERED and entry.refs.action != unit.action:
            continue
        if newest is None or entry.ts > newest:
            newest = entry.ts
    return newest


def rate(
    decided: Sequence[Decided],
    unit: Unit,
    *,
    now: datetime,
    window: timedelta,
    changed: datetime | None,
) -> Rate:
    """The unit's decisions in the window that ends now, counted from its last change."""
    since = now - window
    if changed is not None and changed > since:
        since = changed
    counted = [d for d in decided if d.unit == unit and since < d.at <= now]
    return Rate(
        window=window,
        since=since,
        decided=len(counted),
        released=sum(d.outcome is Outcome.RELEASED for d in counted),
        corrected=sum(d.outcome is Outcome.CORRECTED for d in counted),
        rejected=sum(d.outcome is Outcome.REJECTED for d in counted),
        newest=max((d.seq for d in counted), default=None),
    )


def figures(entries: Sequence[LedgerEntry], unit: Unit, now: datetime) -> Figures:
    """The unit's rate over 7 and 28 days at `now`, from the entries recorded until then."""
    until = [e for e in entries if e.ts <= now]
    decided = decisions(until)
    changed = changed_at(until, unit)
    first = next(
        (
            d.at
            for d in decided
            if d.unit == unit and (changed is None or d.at > changed) and d.at <= now
        ),
        None,
    )
    return Figures(
        unit=unit,
        at=now,
        week=rate(decided, unit, now=now, window=WEEK, changed=changed),
        month=rate(decided, unit, now=now, window=MONTH, changed=changed),
        counted_since=first,
        changed_at=changed,
    )


def units(entries: Iterable[LedgerEntry]) -> list[Unit]:
    """Every unit any decision was made for, in the order first decided."""
    return list(dict.fromkeys(d.unit for d in decisions(entries)))


def lowering_due(
    entries: Sequence[LedgerEntry], unit: Unit, now: datetime, limits: CorrectionLimits
) -> Rate | None:
    """The rate that lowers the unit now, or None when it does not."""
    until = [e for e in entries if e.ts <= now]
    counted = rate(
        decisions(until),
        unit,
        now=now,
        window=limits.lower_window,
        changed=changed_at(until, unit),
    )
    value = counted.rate
    if counted.decided < limits.lower_minimum or value is None or value <= limits.lower_rate:
        return None
    return counted


def raise_due(
    entries: Sequence[LedgerEntry], unit: Unit, now: datetime, limits: CorrectionLimits
) -> Figures | None:
    """The figures a raise of the unit is proposed with now, or None when the tenant's
    conditions do not hold or a raise was proposed since the unit's last change."""
    found = figures(entries, unit, now)
    week, month = found.week.rate, found.month.rate
    if found.month.decided < limits.raise_decisions:
        return None
    if found.counted_since is None or now - found.counted_since < timedelta(
        weeks=limits.raise_weeks
    ):
        return None
    if week is None or month is None or week >= limits.raise_rate or month >= limits.raise_rate:
        return None
    for entry in entries:
        if (
            entry.kind == PROPOSED
            and entry.outcome == PROPOSED_BY_CORRECTIONS
            and entry.ts <= now
            and unit_of(entry) == unit
            and (found.changed_at is None or entry.ts > found.changed_at)
        ):
            return None
    return found


def lowered(entries: Iterable[LedgerEntry], process_version: str) -> Lowered:
    """The levels a version was lowered to by rule: for each unit, the lowest named."""
    level: AutonomyLevel | None = None
    actions: dict[str, AutonomyLevel] = {}
    for entry in entries:
        if entry.kind != LOWERED or entry.rehearsal:
            continue
        if entry.refs.process_version != process_version:
            continue
        to = level_of(entry.outcome)
        if to is None:
            continue
        action = entry.refs.action
        if action is None:
            level = to if level is None else min(level, to)
        else:
            actions[action] = min(actions.get(action, to), to)
    return Lowered(level=level, actions=actions)


def one_below(level: AutonomyLevel) -> AutonomyLevel | None:
    """The level one below, or None at level 1, below which nothing lies."""
    if level <= 1:
        return None
    below: AutonomyLevel = level - 1  # type: ignore[assignment]
    return below


def every_figure(entries: Sequence[LedgerEntry], now: datetime) -> list[Figures]:
    """Every unit's figures at `now`, in the order its first decision was made."""
    return [figures(entries, unit, now) for unit in units(entries)]
