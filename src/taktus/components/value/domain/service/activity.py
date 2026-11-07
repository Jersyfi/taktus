"""What the processes did, folded from the ledger per process and UTC day (ADR-0244 §1).

Per process and day: runs finished and escalated, the seconds from a run's creation to its end,
step results by a person and by any other method, results a check refused, results a person
corrected, and the decisions people took on steps proposed at level 1 or 2 — released,
corrected or rejected. A rehearsal is no work and is left out. No actor is kept: every count is
a process's, never a person's (principle 14).

A second projection keeps the takeover trials and removal verdicts with their time, so that the
bus-factor index can be computed for any past day (UC-6.7 §2).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from taktus.shared.v1 import LedgerEntry, Method

COUNTS = (
    "finished",
    "escalated",
    "cycle_seconds",
    "by_person",
    "by_method",
    "check_failed",
    "corrected",
    "released",
    "changed",
    "refused",
)
DECIDED = {"released": "released", "corrected": "changed", "rejected": "refused"}
KINDS = frozenset(
    {
        "run.created",
        "run.finished",
        "run.escalated",
        "step.finished",
        "step.corrected",
        "proposal.decided",
    }
)


@dataclass
class Activity:
    days: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    """Per process, per ISO day: the counts of `COUNTS`."""
    open: dict[str, list[str]] = field(default_factory=dict)
    """The runs created and not ended: their process and their creation time."""
    corrected: dict[str, list[str]] = field(default_factory=dict)
    """Per run: the steps a person corrected, so a result corrected twice counts once."""

    def total(self, process: str, since: date | None, until: date | None) -> dict[str, float]:
        """The counts of `process` summed over the days from `since` to `until`, inclusive."""
        summed = dict.fromkeys(COUNTS, 0.0)
        for day, counts in self.days.get(process, {}).items():
            at = date.fromisoformat(day)
            if (since is not None and at < since) or (until is not None and at > until):
                continue
            for name, n in counts.items():
                summed[name] = summed.get(name, 0.0) + n
        return summed

    def processes(self) -> tuple[str, ...]:
        return tuple(sorted(self.days))


def _process(entry: LedgerEntry) -> str | None:
    version = entry.refs.process_version
    return None if version is None else version.rsplit("@", 1)[0]


def _add(state: Activity, process: str, at: datetime, name: str, n: float = 1) -> None:
    day = state.days.setdefault(process, {}).setdefault(at.date().isoformat(), {})
    day[name] = day.get(name, 0) + n


def fold(state: Activity, entry: LedgerEntry) -> Activity:
    process = _process(entry)
    run = entry.refs.run_id
    if entry.rehearsal or process is None:
        return state
    if entry.kind == "run.created" and run is not None:
        state.open.setdefault(run, [process, entry.ts.isoformat()])
    elif entry.kind in ("run.finished", "run.escalated") and run is not None:
        opened = state.open.pop(run, None)
        _add(state, process, entry.ts, "finished" if entry.kind == "run.finished" else "escalated")
        if opened is not None:
            seconds = (entry.ts - datetime.fromisoformat(opened[1])).total_seconds()
            _add(state, process, entry.ts, "cycle_seconds", max(seconds, 0.0))
        state.corrected.pop(run, None)
    elif entry.kind == "step.finished":
        if entry.outcome == "succeeded":
            who = "by_person" if entry.method is Method.HUMAN else "by_method"
            _add(state, process, entry.ts, who)
        elif entry.outcome == "check_failed":
            _add(state, process, entry.ts, "check_failed")
    elif entry.kind == "step.corrected" and run is not None and entry.refs.step_id is not None:
        steps = state.corrected.setdefault(run, [])
        if entry.refs.step_id not in steps:
            steps.append(entry.refs.step_id)
            _add(state, process, entry.ts, "corrected")
    elif entry.kind == "proposal.decided" and entry.outcome in DECIDED:
        _add(state, process, entry.ts, DECIDED[entry.outcome])
    return state


class ActivityProjection:
    name = "value.activity.v1"
    kinds: frozenset[str] | None = KINDS

    def empty(self) -> Activity:
        return Activity()

    def fold(self, state: Activity, entry: LedgerEntry) -> Activity:
        return fold(state, entry)

    def dump(self, state: Activity) -> dict[str, Any]:
        return {"days": state.days, "open": state.open, "corrected": state.corrected}

    def load(self, document: Mapping[str, Any]) -> Activity:
        return Activity(
            days={p: {d: dict(c) for d, c in days.items()} for p, days in document["days"].items()},
            open={r: list(v) for r, v in document["open"].items()},
            corrected={r: list(v) for r, v in document["corrected"].items()},
        )


ACTIVITY = ActivityProjection()


# --- dependence: takeover trials and removal verdicts over time ------------------------------


@dataclass
class Dependence:
    trials: list[tuple[str, str, bool]] = field(default_factory=list)
    """Every takeover trial: its time, the version it tried, and whether it passed."""
    verdicts: list[tuple[str, str, str]] = field(default_factory=list)
    """Every removal verdict: its time, the integration, and the verdict."""

    def trial_at(self, version: str, at: datetime) -> bool | None:
        """Whether the newest trial of `version` up to `at` passed; None for no trial."""
        found = [p for ts, v, p in self.trials if v == version and datetime.fromisoformat(ts) <= at]
        return None if not found else found[-1]

    def verdict_at(self, integration: str, at: datetime) -> str | None:
        found = [
            v for ts, i, v in self.verdicts if i == integration and datetime.fromisoformat(ts) <= at
        ]
        return None if not found else found[-1]

    def integrations(self) -> tuple[str, ...]:
        return tuple(sorted({i for _, i, _ in self.verdicts}))


def fold_dependence(state: Dependence, entry: LedgerEntry) -> Dependence:
    if entry.rehearsal:
        return state
    if entry.kind == "takeover.trial" and entry.refs.process_version is not None:
        state.trials.append(
            (entry.ts.isoformat(), entry.refs.process_version, entry.outcome == "passed")
        )
    elif entry.kind == "removal.tested" and entry.adapter is not None and entry.outcome:
        state.verdicts.append((entry.ts.isoformat(), entry.adapter, entry.outcome))
    return state


class DependenceProjection:
    name = "value.dependence.v1"
    kinds: frozenset[str] | None = frozenset({"takeover.trial", "removal.tested"})

    def empty(self) -> Dependence:
        return Dependence()

    def fold(self, state: Dependence, entry: LedgerEntry) -> Dependence:
        return fold_dependence(state, entry)

    def dump(self, state: Dependence) -> dict[str, Any]:
        return {
            "trials": [list(t) for t in state.trials],
            "verdicts": [list(v) for v in state.verdicts],
        }

    def load(self, document: Mapping[str, Any]) -> Dependence:
        return Dependence(
            trials=[(t[0], t[1], bool(t[2])) for t in document["trials"]],
            verdicts=[(v[0], v[1], v[2]) for v in document["verdicts"]],
        )


DEPENDENCE = DependenceProjection()


def rebuilt(projection: Any, entries: Iterable[LedgerEntry]) -> Any:
    """The projection folded from `entries` alone: what a test recomputes from the ledger."""
    state = projection.empty()
    for entry in entries:
        if projection.kinds is None or entry.kind in projection.kinds:
            state = projection.fold(state, entry)
    return state
