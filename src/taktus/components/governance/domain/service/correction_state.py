"""What the correction rule needs of the ledger, as a projection (ADR-0105 §10, issue #550).

`corrections.py` states the rule over every entry of four kinds. The projection holds what the
rule reads and folds the entries after its last read into it, so that the figures, a lowering
and a proposal cost what they return, not what the tenant's decisions hold.

Per unit it keeps the decisions of the last `RETAIN` days (sequence number, moment, outcome) and
the first decision counted since the unit's last change of level. Per unit it keeps the last
lowering and the last proposal, per process the last raise. For each raise Taktus proposed it
keeps the figures it was proposed with, computed when the entry is folded: the figures are the
rule's, at that entry's moment, and never change.

A read the state cannot answer is made from the entries: a moment before the newest entry read, a
window that begins before the days kept, or a unit whose change of level lies before them. The
reader then folds the entries of the four kinds up to the moment into a state that keeps every
decision (`retain=None`), so that both ways answer through the same functions.
`tests/components/governance/test_correction_state.py` rebuilds the projection and compares it,
and the functions below, with the rule over every entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from taktus.components.governance.domain.model.corrections import (
    CorrectionLimits,
    Figures,
    Outcome,
    Proposed,
    Rate,
    Unit,
)
from taktus.components.governance.domain.service import corrections as rule
from taktus.shared.v1 import LedgerEntry

RETAIN = timedelta(days=35)
"""The decisions kept: the 28 days of the longer rate, and seven days more for a window the
tenant set up to that long and for entries whose moments run a little behind their order. A
window that begins before is read from the entries."""

PRUNE_EVERY = timedelta(days=1)
"""How far the newest entry moves on before what lies before the days kept is dropped."""

type Key = tuple[str, str | None]


@dataclass
class Counted:
    """One unit's decisions."""

    decisions: list[tuple[int, datetime, Outcome]] = field(default_factory=list)
    """In sequence order: the decisions from the days kept."""
    first: tuple[int, datetime] | None = None
    """The first decision, by sequence, made after the unit's last change of level."""
    lost: bool = False
    """The unit's last change of level lies before the days kept, so the decisions after it
    are not all held: the state cannot say which was first."""


@dataclass
class Corrected:
    retain: timedelta | None = RETAIN
    units: dict[Key, Counted] = field(default_factory=dict)
    """In the order each unit was first decided."""
    lowered: dict[Key, datetime] = field(default_factory=dict)
    """The moment of each unit's last lowering."""
    raised: dict[str, datetime] = field(default_factory=dict)
    """The moment of each process's last raise."""
    proposed: dict[Key, datetime] = field(default_factory=dict)
    """The moment of each unit's last raise Taktus proposed on the corrections."""
    proposals: list[tuple[int, str, Figures]] = field(default_factory=list)
    """Sequence number, version and figures of each, in sequence order."""
    newest: datetime | None = None
    """The newest moment of an entry folded."""
    kept_from: datetime | None = None
    """Decisions before this are not held; None where none was dropped."""

    def changed(self, key: Key) -> datetime | None:
        """The unit's last change of level: its last lowering or its process's last raise."""
        moments = [m for m in (self.lowered.get(key), self.raised.get(key[0])) if m is not None]
        return max(moments, default=None)

    def reads(self, now: datetime, window: timedelta) -> bool:
        """Whether the state gives the rule's answer at `now`, over windows up to `window`."""
        if self.newest is not None and now < self.newest:
            return False
        if self.kept_from is not None and now - window < self.kept_from:
            return False
        return not any(unit.lost for unit in self.units.values())


def key_of(unit: Unit) -> Key:
    return (unit.process_id, unit.action)


def unit_of(key: Key) -> Unit:
    return Unit(process_id=key[0], action=key[1])


def figures(state: Corrected, unit: Unit, now: datetime) -> Figures:
    """The unit's rate over 7 and 28 days at `now`: `rule.figures`, from the state."""
    key = key_of(unit)
    held = state.units.get(key) or Counted()
    changed = state.changed(key)
    return Figures(
        unit=unit,
        at=now,
        week=_rate(held, now, rule.WEEK, changed),
        month=_rate(held, now, rule.MONTH, changed),
        counted_since=None if held.first is None else held.first[1],
        changed_at=changed,
    )


def every_figure(state: Corrected, now: datetime) -> list[Figures]:
    """Every unit's figures at `now`, in the order its first decision was made."""
    return [figures(state, unit_of(key), now) for key in state.units]


def lowering_due(
    state: Corrected, unit: Unit, now: datetime, limits: CorrectionLimits
) -> Rate | None:
    """`rule.lowering_due`, from the state."""
    key = key_of(unit)
    counted = _rate(state.units.get(key) or Counted(), now, limits.lower_window, state.changed(key))
    value = counted.rate
    if counted.decided < limits.lower_minimum or value is None or value <= limits.lower_rate:
        return None
    return counted


def raise_due(
    state: Corrected, unit: Unit, now: datetime, limits: CorrectionLimits
) -> Figures | None:
    """`rule.raise_due`, from the state."""
    found = figures(state, unit, now)
    week, month = found.week.rate, found.month.rate
    if found.month.decided < limits.raise_decisions:
        return None
    if found.counted_since is None or now - found.counted_since < timedelta(
        weeks=limits.raise_weeks
    ):
        return None
    if week is None or month is None or week >= limits.raise_rate or month >= limits.raise_rate:
        return None
    proposed = state.proposed.get(key_of(unit))
    if proposed is not None and (found.changed_at is None or proposed > found.changed_at):
        return None
    return found


def _rate(held: Counted, now: datetime, window: timedelta, changed: datetime | None) -> Rate:
    since = now - window
    if changed is not None and changed > since:
        since = changed
    counted = [d for d in held.decisions if since < d[1] <= now]
    return Rate(
        window=window,
        since=since,
        decided=len(counted),
        released=sum(d[2] is Outcome.RELEASED for d in counted),
        corrected=sum(d[2] is Outcome.CORRECTED for d in counted),
        rejected=sum(d[2] is Outcome.REJECTED for d in counted),
        newest=max((d[0] for d in counted), default=None),
    )


class CorrectionProjection:
    name = "governance.corrections.v1"
    kinds: frozenset[str] | None = frozenset(rule.KINDS)

    def __init__(self, retain: timedelta | None = RETAIN) -> None:
        self._retain = retain

    def empty(self) -> Corrected:
        return Corrected(retain=self._retain)

    def fold(self, state: Corrected, entry: LedgerEntry) -> Corrected:
        if state.newest is None or entry.ts > state.newest:
            state.newest = entry.ts
        if entry.kind == rule.DECIDED:
            _decided(state, entry)
        elif entry.kind in (rule.LOWERED, rule.RAISED):
            _changed(state, entry)
        elif entry.kind == rule.PROPOSED:
            _proposed(state, entry)
        _prune(state)
        return state

    def dump(self, state: Corrected) -> dict[str, Any]:
        return {
            "retain": None if state.retain is None else state.retain.total_seconds(),
            "units": [
                {
                    "process": key[0],
                    "action": key[1],
                    "decisions": [[s, at.isoformat(), o.value] for s, at, o in held.decisions],
                    "first": None
                    if held.first is None
                    else [held.first[0], held.first[1].isoformat()],
                    "lost": held.lost,
                }
                for key, held in state.units.items()
            ],
            "lowered": [[k[0], k[1], at.isoformat()] for k, at in state.lowered.items()],
            "raised": {process: at.isoformat() for process, at in state.raised.items()},
            "proposed": [[k[0], k[1], at.isoformat()] for k, at in state.proposed.items()],
            "proposals": [
                [seq, version, found.model_dump(mode="json")]
                for seq, version, found in state.proposals
            ],
            "newest": None if state.newest is None else state.newest.isoformat(),
            "kept_from": None if state.kept_from is None else state.kept_from.isoformat(),
        }

    def load(self, document: Mapping[str, Any]) -> Corrected:
        retain = document["retain"]
        state = Corrected(retain=None if retain is None else timedelta(seconds=retain))
        for one in document["units"]:
            first = one["first"]
            state.units[(one["process"], one["action"])] = Counted(
                decisions=[
                    (s, datetime.fromisoformat(at), Outcome(o)) for s, at, o in one["decisions"]
                ],
                first=None if first is None else (first[0], datetime.fromisoformat(first[1])),
                lost=one["lost"],
            )
        state.lowered = {(p, a): datetime.fromisoformat(at) for p, a, at in document["lowered"]}
        state.raised = {p: datetime.fromisoformat(at) for p, at in document["raised"].items()}
        state.proposed = {(p, a): datetime.fromisoformat(at) for p, a, at in document["proposed"]}
        state.proposals = [
            (seq, version, Figures.model_validate(found))
            for seq, version, found in document["proposals"]
        ]
        state.newest = _moment(document["newest"])
        state.kept_from = _moment(document["kept_from"])
        return state


def _moment(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def _decided(state: Corrected, entry: LedgerEntry) -> None:
    """`rule.decisions`: a rehearsal, an entry without a version and an outcome that is none
    of the three are no decision."""
    if entry.rehearsal or entry.refs.process_version is None:
        return
    try:
        outcome = Outcome(entry.outcome or "")
    except ValueError:
        return
    unit = rule.unit_of(entry)
    if unit is None:
        return
    key = key_of(unit)
    held = state.units.setdefault(key, Counted())
    if state.kept_from is None or entry.ts >= state.kept_from:
        held.decisions.append((entry.seq, entry.ts, outcome))
    changed = state.changed(key)
    if held.first is None and (changed is None or entry.ts > changed):
        held.first = (entry.seq, entry.ts)


def _changed(state: Corrected, entry: LedgerEntry) -> None:
    """`rule.changed_at`: a lowering of the unit itself, or a raise of its process."""
    version = entry.refs.process_version
    if entry.rehearsal or version is None:
        return
    process = rule.process_of(version)
    if entry.kind == rule.LOWERED:
        key = (process, entry.refs.action)
        before = state.changed(key)
        if key not in state.lowered or entry.ts > state.lowered[key]:
            state.lowered[key] = entry.ts
        affected = [key] if state.changed(key) != before else []
    else:
        before_all = {k: state.changed(k) for k in state.units if k[0] == process}
        if process not in state.raised or entry.ts > state.raised[process]:
            state.raised[process] = entry.ts
        affected = [k for k, was in before_all.items() if state.changed(k) != was]
    for key in affected:
        if key in state.units:
            _restart(state, key)


def _restart(state: Corrected, key: Key) -> None:
    """The unit changed level: its first decision is the first made after the change."""
    held = state.units[key]
    changed = state.changed(key)
    held.first = next(
        ((s, at) for s, at, _ in held.decisions if changed is not None and at > changed),
        None,
    )
    held.lost = state.kept_from is not None and changed is not None and changed < state.kept_from


def _proposed(state: Corrected, entry: LedgerEntry) -> None:
    """A raise Taktus proposed on the corrections: `rule.raise_due` reads that it was made,
    `Corrections.proposed` the figures it was made with."""
    if entry.outcome != rule.PROPOSED_BY_CORRECTIONS:
        return
    unit = rule.unit_of(entry)
    if unit is None or entry.refs.process_version is None:
        return
    key = key_of(unit)
    if key not in state.proposed or entry.ts > state.proposed[key]:
        state.proposed[key] = entry.ts
    if not entry.rehearsal:
        state.proposals.append(
            (entry.seq, entry.refs.process_version, figures(state, unit, entry.ts))
        )


def _prune(state: Corrected) -> None:
    if state.retain is None or state.newest is None:
        return
    cutoff = state.newest - state.retain
    if state.kept_from is not None and cutoff < state.kept_from + PRUNE_EVERY:
        return
    state.kept_from = cutoff
    for held in state.units.values():
        held.decisions = [d for d in held.decisions if d[1] >= cutoff]


def proposed(state: Corrected) -> list[Proposed]:
    """Every raise Taktus proposed on the corrections, oldest first, with its figures."""
    return [
        Proposed(seq=seq, process_version=version, figures=found)
        for seq, version, found in state.proposals
    ]


CORRECTIONS = CorrectionProjection()
UNBOUNDED = CorrectionProjection(retain=None)
"""The state folded from the entries a read the days kept cannot answer."""
