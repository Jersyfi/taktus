"""The run's projections of the ledger (ADR-0105): the calibration and the activity of runs.

Each is a value over a tenant's whole history, computed entry by entry and stored with the
sequence number of the last entry it read. Folding the entries after it into the stored value
gives what folding every entry from the start gives; `tests/components/run/test_projections.py`
rebuilds each from the ledger and compares it with the full computation.

**The calibration** pairs a step's `step.admitted` with the `step.finished` of the same step
after it: an observation of estimate and actual (ADR-0005 §4). The calibration reads only the
last `WINDOW` observations of an adapter and method, and of a step through it (#370). The
projection keeps the last `WINDOW` per adapter, method and step, and the estimates still waiting
for their step to finish. In the order of the entries, those observations end with the last
`WINDOW` of every adapter and method, and of every step: `scale_for` gives the factors it gives
over every observation.

**The activity** names, per process and day, the runs with an entry in it. A week or a month is
the union of its days. The blocked-time sums read it for the share of the work a block held up.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from taktus.components.run.domain.service.blocked import Period, period_of, process_of
from taktus.components.run.domain.service.budget import WINDOW, Observation
from taktus.shared.v1 import Consumption, LedgerEntry, Method

CALIBRATION_KINDS = frozenset({"step.admitted", "step.finished"})


def step_key(process_version: str | None, step_id: str) -> str | None:
    """`<process>/<step>`: the same step of every version of a process, the key a bound is
    calibrated by (#370)."""
    if process_version is None:
        return None
    return f"{process_version.split('@', 1)[0]}/{step_id}"


@dataclass
class Calibration:
    """The estimates waiting for their step, and the last observations of each adapter, method
    and step, each with the sequence number of the entry that finished it."""

    pending: dict[tuple[str, str], Consumption] = field(default_factory=dict)
    kept: dict[tuple[str, str, str | None], list[tuple[int, Observation]]] = field(
        default_factory=dict
    )
    window: int = WINDOW

    def observations(self) -> list[Observation]:
        """What the calibration reads, oldest first."""
        every = [kept for history in self.kept.values() for kept in history]
        return [observation for _, observation in sorted(every, key=lambda kept: kept[0])]


def observed(entry: LedgerEntry, pending: dict[tuple[str, str], Consumption]) -> Observation | None:
    """What one entry adds to the pairing of estimates and actuals: the observation it
    completes, if any. `pending` holds the estimates waiting for their step, and changes."""
    run_id, step_id = entry.refs.run_id, entry.refs.step_id
    if run_id is None or step_id is None or entry.rehearsal:
        return None  # a rehearsal replays recorded answers: it measures no adapter
    if entry.kind == "step.admitted" and entry.consumption is not None:
        pending[(run_id, step_id)] = entry.consumption
    elif entry.kind == "step.finished" and entry.outcome == "stopped":
        # A stopped step used part of what it was estimated for: its partial actual against
        # its whole estimate would read as an overestimate. It measures nothing.
        pending.pop((run_id, step_id), None)
    elif entry.kind == "step.finished" and entry.consumption is not None:
        estimate = pending.pop((run_id, step_id), None)
        if estimate is None or entry.adapter is None or entry.method is None:
            return None
        return Observation(
            adapter=entry.adapter,
            method=entry.method,
            estimate=estimate,
            actual=entry.consumption,
            step=step_key(entry.refs.process_version, step_id),
        )
    return None


def every_observation(entries: Iterable[LedgerEntry]) -> list[Observation]:
    """Every pair of estimate and actual in the entries, oldest first: the full computation the
    calibration projection must equal."""
    pending: dict[tuple[str, str], Consumption] = {}
    return [o for e in entries if (o := observed(e, pending)) is not None]


class CalibrationProjection:
    name = "run.calibration.v1"
    kinds: frozenset[str] | None = CALIBRATION_KINDS

    def empty(self) -> Calibration:
        return Calibration()

    def fold(self, state: Calibration, entry: LedgerEntry) -> Calibration:
        observation = observed(entry, state.pending)
        if observation is not None:
            key = (observation.adapter, observation.method.value, observation.step)
            history = state.kept.setdefault(key, [])
            history.append((entry.seq, observation))
            del history[: -state.window]
        return state

    def dump(self, state: Calibration) -> dict[str, Any]:
        return {
            "pending": [
                [run_id, step_id, estimate.document()]
                for (run_id, step_id), estimate in sorted(state.pending.items())
            ],
            "kept": [
                [
                    adapter,
                    method,
                    step,
                    [[seq, o.estimate.document(), o.actual.document()] for seq, o in history],
                ]
                for (adapter, method, step), history in state.kept.items()
            ],
        }

    def load(self, document: Mapping[str, Any]) -> Calibration:
        state = Calibration()
        for run_id, step_id, estimate in document["pending"]:
            state.pending[(run_id, step_id)] = Consumption.model_validate(estimate)
        for adapter, method, step, history in document["kept"]:
            state.kept[(adapter, method, step)] = [
                (
                    seq,
                    Observation(
                        adapter=adapter,
                        method=Method(method),
                        estimate=Consumption.model_validate(estimate),
                        actual=Consumption.model_validate(actual),
                        step=step,
                    ),
                )
                for seq, estimate, actual in history
            ]
        return state


CALIBRATION = CalibrationProjection()


@dataclass
class Activity:
    """Per process and day, the runs with an entry in it."""

    days: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))

    def active(self, period: Period) -> dict[tuple[str, str], frozenset[str]]:
        """Per process and period, the runs with an entry in it."""
        found: dict[tuple[str, str], set[str]] = defaultdict(set)
        for (process, day), runs in self.days.items():
            found[(process, period_of(datetime.fromisoformat(day), period))] |= runs
        return {key: frozenset(runs) for key, runs in found.items()}


def active(entries: Iterable[LedgerEntry], period: Period) -> dict[tuple[str, str], frozenset[str]]:
    """Per process and period, the runs with an entry in it, from every entry: the full
    computation the activity projection must equal."""
    found: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entry in entries:
        if entry.refs.run_id is None or entry.refs.process_version is None:
            continue
        key = (process_of(entry.refs.process_version), period_of(entry.ts, period))
        found[key].add(entry.refs.run_id)
    return {key: frozenset(runs) for key, runs in found.items()}


class ActivityProjection:
    name = "run.activity.v1"
    kinds: frozenset[str] | None = None

    def empty(self) -> Activity:
        return Activity()

    def fold(self, state: Activity, entry: LedgerEntry) -> Activity:
        if entry.refs.run_id is not None and entry.refs.process_version is not None:
            key = (process_of(entry.refs.process_version), period_of(entry.ts, "day"))
            state.days[key].add(entry.refs.run_id)
        return state

    def dump(self, state: Activity) -> dict[str, Any]:
        return {
            "days": [
                [process, day, sorted(runs)] for (process, day), runs in sorted(state.days.items())
            ]
        }

    def load(self, document: Mapping[str, Any]) -> Activity:
        state = Activity()
        for process, day, runs in document["days"]:
            state.days[(process, day)] = set(runs)
        return state


ACTIVITY = ActivityProjection()
