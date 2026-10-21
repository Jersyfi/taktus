"""What the Takt rate needs of the ledger, as a projection (ADR-0105 §9).

The rate weighs each run's finished steps at the table its budget statement names. The
projection keeps, for the last `RETAIN_DAYS` days and per day, each run's breakdown of the steps
it finished that day (`metering.Meter`), and, per run, the budget statement it names. A read of
the rate takes the whole days of its window from the projection and reads only the two partial
days from the ledger, so it costs what the window's runs return, not what its entries hold.

`budgets` holds a run from its `run.created`, so that a run known to have no statement is
distinguished from a run the projection no longer knows: the second is read from the ledger.
A day is a day of UTC. `tests/components/accounting/test_takt.py` rebuilds the projection from
the ledger and compares it with the rate computed from the entries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from taktus.components.accounting.domain.service.metering import Meter, combine, meter
from taktus.shared.v1 import LedgerEntry

RETAIN_DAYS = 33
"""The days the projection keeps: the thirty of the window in force, its two partial days and
a day of margin. A window longer than that is read from the entries."""

KINDS = frozenset({"run.created", "step.finished", "budget.set"})


@dataclass
class TaktDays:
    days: dict[str, dict[str, Meter]] = field(default_factory=dict)
    """Per day, per run: what the run's steps finished that day used."""
    budgets: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    """Per run: the digest of its latest budget statement, and the day it last appeared."""
    newest: str = ""
    """The day of the newest entry read."""

    def of_days(self, first: date, last: date) -> dict[str, Meter]:
        """Each run's breakdown over the whole days `first` to `last`, both included."""
        found: dict[str, Meter] = {}
        day = first
        while day <= last:
            for run_id, used in self.days.get(day.isoformat(), {}).items():
                found[run_id] = combine(found[run_id], used) if run_id in found else used
            day += timedelta(days=1)
        return found


class TaktProjection:
    name = "accounting.takt.v1"
    kinds: frozenset[str] | None = KINDS

    def empty(self) -> TaktDays:
        return TaktDays()

    def fold(self, state: TaktDays, entry: LedgerEntry) -> TaktDays:
        run_id = entry.refs.run_id
        if run_id is None:
            return state
        day = entry.ts.date().isoformat()
        if entry.kind == "step.finished":
            used = meter([entry])
            today = state.days.setdefault(day, {})
            today[run_id] = combine(today[run_id], used) if run_id in today else used
            if run_id in state.budgets:
                digest, seen = state.budgets[run_id]
                state.budgets[run_id] = (digest, max(seen, day))
        else:
            digest, seen = state.budgets.get(run_id, (None, day))
            if entry.kind == "budget.set" and entry.content_digest is not None:
                digest = entry.content_digest
            state.budgets[run_id] = (digest, max(seen, day))
        if day > state.newest:
            state.newest = day
            _forget(state)
        return state

    def dump(self, state: TaktDays) -> dict[str, Any]:
        return {
            "newest": state.newest,
            "days": {
                day: {
                    run: used.model_dump(mode="json", exclude_defaults=True)
                    for run, used in runs.items()
                }
                for day, runs in sorted(state.days.items())
            },
            "budgets": {run: list(held) for run, held in sorted(state.budgets.items())},
        }

    def load(self, document: Mapping[str, Any]) -> TaktDays:
        return TaktDays(
            days={
                day: {run: Meter.model_validate(used) for run, used in runs.items()}
                for day, runs in document["days"].items()
            },
            budgets={run: (held[0], held[1]) for run, held in document["budgets"].items()},
            newest=document["newest"],
        )


def _forget(state: TaktDays) -> None:
    """Drop what lies before the days kept, relative to the newest entry read."""
    cutoff = (date.fromisoformat(state.newest) - timedelta(days=RETAIN_DAYS)).isoformat()
    for day in [d for d in state.days if d < cutoff]:
        del state.days[day]
    for run in [r for r, (_, seen) in state.budgets.items() if seen < cutoff]:
        del state.budgets[run]


TAKT = TaktProjection()
