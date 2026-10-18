"""The rule that a run is missing or overdue, and that a watcher may be blind (ADR-0107 §3, §5).

Pure: given what the process component says was expected and what the ledger says happened,
the same facts yield the same answer every time. No model decides it (ADR-0023 §1). Each answer
names its rule and the facts it read, so that a person can check it afterwards.

- **A missed slot** (`expected.slot`): the slot is the latest of its schedule at or before
  `now - grace`, after the version was activated. The run happened when a beat — a
  `run.started` or a `trigger.empty` — lies between the slot and the slot plus the grace.
- **A missed gap** (`expected.gap`): a run is expected at the last beat plus the gap; without a
  beat since the activation, at the activation plus the gap. It is missed once the grace has
  passed too.
- **An overrun** (`expected.bound`): a run started more than its bound plus the grace ago, and
  has neither ended nor been stopped by a person since its last start or resume.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from taktus.components.governance.domain.model.incident import RunSeen
from taktus.shared.v1 import LedgerEntry, Value

STARTED = "run.started"
EMPTY = "trigger.empty"
ENDED = "run.ended"
HALTED = "run.halted"
RESUMED = "run.resumed"
RECOVERED = "run.recovered"
BEATS = (STARTED, EMPTY)
"""What says a run happened: it started, or a firing read its list and found nothing."""
ENDS = (ENDED, EMPTY)
"""What says how a run ended: `run.ended`, or a firing that found nothing."""
COURSE = (STARTED, ENDED, HALTED, RESUMED, RECOVERED)
"""What says whether a started run is still under way."""
STOPPED_BY_A_PERSON = "stop"
OVERRUN_HORIZON = timedelta(days=1)
"""How far before its bound and grace ran out a started run is still looked at."""


class Slot(Value):
    """A slot a run was expected at: the latest of one schedule at or before `now - grace`."""

    schedule: str
    at: datetime


class Watched(Value):
    """One process's active version as the watcher reads it, from the process component."""

    process_id: str
    process_version: str
    activated_at: datetime
    slots: tuple[Slot, ...] = ()
    gap: timedelta | None = None
    bound: timedelta | None = None


@dataclass(frozen=True)
class Miss:
    """A run that was expected and did not happen, or one that did not end within its bound."""

    rule: str
    expected_at: datetime
    deadline: datetime
    last_run: RunSeen | None
    facts: dict[str, str | float] = field(default_factory=dict)
    run_id: str | None = None
    """For an overrun: the run that has not ended."""


def seen(entry: LedgerEntry) -> RunSeen:
    return RunSeen(at=entry.ts, run_id=entry.refs.run_id, kind=entry.kind)


def missed_slots(
    watched: Watched,
    grace: timedelta,
    beats: Sequence[LedgerEntry],
    before: Mapping[datetime, LedgerEntry | None],
) -> list[Miss]:
    """Every slot of `watched` no beat answered within the grace. `beats` are the process's
    beats since the earliest slot; `before` names, by slot, the newest beat before it."""
    misses: list[Miss] = []
    for slot in watched.slots:
        deadline = slot.at + grace
        if slot.at <= watched.activated_at:
            continue
        if any(slot.at <= beat.ts <= deadline for beat in beats if beat.kind in BEATS):
            continue
        prior = before.get(slot.at)
        misses.append(
            Miss(
                rule="expected.slot",
                expected_at=slot.at,
                deadline=deadline,
                last_run=None if prior is None else seen(prior),
                facts={
                    "schedule": slot.schedule,
                    "slot": slot.at.isoformat(),
                    "grace_seconds": grace.total_seconds(),
                    "window_from": slot.at.isoformat(),
                    "window_to": deadline.isoformat(),
                },
            )
        )
    return misses


def missed_gap(
    watched: Watched, grace: timedelta, last: LedgerEntry | None, now: datetime
) -> Miss | None:
    """The run the gap expects, when its time and the grace have passed without a beat."""
    if watched.gap is None:
        return None
    since_last = last is not None and last.ts >= watched.activated_at
    base = last.ts if since_last and last is not None else watched.activated_at
    expected = base + watched.gap
    deadline = expected + grace
    if now < deadline:
        return None
    return Miss(
        rule="expected.gap",
        expected_at=expected,
        deadline=deadline,
        last_run=None if last is None else seen(last),
        facts={
            "gap_seconds": watched.gap.total_seconds(),
            "grace_seconds": grace.total_seconds(),
            "counted_from": base.isoformat(),
            "window_to": deadline.isoformat(),
        },
    )


def overruns(
    watched: Watched, grace: timedelta, course: Sequence[LedgerEntry], now: datetime
) -> list[Miss]:
    """Every run whose start lies more than its bound plus the grace back, and that has neither
    ended nor been stopped by a person since. `course` is the process's entries of `COURSE`
    since `now - bound - grace - OVERRUN_HORIZON`, in sequence order."""
    if watched.bound is None:
        return []
    started: dict[str, LedgerEntry] = {}
    done: set[str] = set()
    stopped: dict[str, bool] = {}
    for entry in course:
        run_id = entry.refs.run_id
        if run_id is None:
            continue
        if entry.kind == STARTED:
            started[run_id] = entry
        elif entry.kind == ENDED:
            done.add(run_id)
        elif entry.kind == HALTED:
            stopped[run_id] = entry.outcome == STOPPED_BY_A_PERSON
        elif entry.kind in (RESUMED, RECOVERED):
            stopped[run_id] = False
    misses: list[Miss] = []
    for run_id, start in started.items():
        expected = start.ts + watched.bound
        deadline = expected + grace
        if run_id in done or stopped.get(run_id, False) or now < deadline:
            continue
        misses.append(
            Miss(
                rule="expected.bound",
                expected_at=expected,
                deadline=deadline,
                last_run=seen(start),
                run_id=run_id,
                facts={
                    "bound_seconds": watched.bound.total_seconds(),
                    "grace_seconds": grace.total_seconds(),
                    "started_at": start.ts.isoformat(),
                    "window_to": deadline.isoformat(),
                },
            )
        )
    return misses


@dataclass(frozen=True)
class EmptyShare:
    """How a process's ends within the window fell out, and whether the share is exceeded."""

    process_id: str
    process_version: str
    ends: int
    empty: int
    exceeded: bool


def empty_share(
    watched: Watched, ends: Sequence[LedgerEntry], share: float, minimum: int
) -> EmptyShare:
    """`ends` are the process's `run.ended` and `trigger.empty` entries within the window. The
    share is exceeded when at least `minimum` ended and more than `share` of them were empty."""
    counted = [entry for entry in ends if entry.kind in ENDS]
    empty = sum(1 for entry in counted if entry.outcome == "empty")
    exceeded = len(counted) >= minimum and empty > share * len(counted)
    return EmptyShare(
        process_id=watched.process_id,
        process_version=watched.process_version,
        ends=len(counted),
        empty=empty,
        exceeded=exceeded,
    )
