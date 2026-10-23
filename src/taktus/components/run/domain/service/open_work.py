"""A cap on a process's open work (ADR-0132 §1 to §2, UC-8.12).

A process declares, per kind of open outcome, how many may wait at once. Before a run of it
starts anything, the run counts the outcomes open now, per kind: those a read operation of a
connector answers as open outside, and the runs of the process in flight. A run is *in flight*
from the moment it passed the cap, `open_work.admitted` in the ledger, until it finished or
escalated: an outcome it opens is not yet visible outside the moment it passes, and two runs
that pass at once would otherwise both see room for one. A kind whose count reaches its cap
holds the run: it waits, and counts again later.

The decision is a rule over facts the ledger and the connector's answer hold, never a model
(ADR-0023). Its facts are recorded with it, as a document whose digest the ledger entry names.

**The runs in flight** are a projection of the ledger (ADR-0105): per process, the runs that
passed and have not ended. A rehearsal neither passes nor counts: it acts on nothing outside.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from taktus.components.run.domain.model.work import select as part
from taktus.shared.v1 import LedgerEntry, Value

ADMITTED = "open_work.admitted"
"""A run passed its process's caps on open work: it is in flight until it ends."""
CAPPED = "open_work.capped"
"""A run found a cap of its process reached, and waits."""
ENDS = frozenset({"run.finished", "run.escalated"})
KINDS = frozenset({ADMITTED, *ENDS})


def process_of(process_version: str) -> str:
    return process_version.split("@", 1)[0]


@dataclass
class InFlight:
    """Per process, the runs that passed its caps and have not ended."""

    processes: dict[str, set[str]] = field(default_factory=dict)

    def of(self, process_id: str) -> frozenset[str]:
        return frozenset(self.processes.get(process_id, ()))


class InFlightProjection:
    name = "run.open_work.v1"
    kinds: frozenset[str] | None = KINDS

    def empty(self) -> InFlight:
        return InFlight()

    def fold(self, state: InFlight, entry: LedgerEntry) -> InFlight:
        run_id, version = entry.refs.run_id, entry.refs.process_version
        if entry.rehearsal or run_id is None or version is None:
            return state
        process = process_of(version)
        if entry.kind == ADMITTED:
            state.processes.setdefault(process, set()).add(run_id)
        elif entry.kind in ENDS and process in state.processes:
            state.processes[process].discard(run_id)
            if not state.processes[process]:
                del state.processes[process]
        return state

    def dump(self, state: InFlight) -> dict[str, Any]:
        return {
            "processes": {
                process: sorted(runs) for process, runs in sorted(state.processes.items())
            }
        }

    def load(self, document: Mapping[str, Any]) -> InFlight:
        return InFlight(
            processes={process: set(runs) for process, runs in document["processes"].items()}
        )


IN_FLIGHT = InFlightProjection()


def in_flight(entries: Iterable[LedgerEntry]) -> InFlight:
    """The full computation the projection must equal: every entry folded from the first."""
    state = IN_FLIGHT.empty()
    for entry in entries:
        if entry.kind in KINDS:
            state = IN_FLIGHT.fold(state, entry)
    return state


class Counted(Value):
    """One kind's count at one moment: the cap, what the reading answered, the runs in flight,
    and why the reading could not be read where it could not."""

    kind: str
    cap: int
    read: int | None = None
    """The open outcomes the connector answered; None where the cap names no reading, or the
    reading failed."""
    in_flight: int
    unread: str | None = None
    """Why the reading failed. A count that cannot be read holds the run as at its cap."""

    @property
    def open(self) -> int:
        return (self.read or 0) + self.in_flight

    @property
    def reached(self) -> bool:
        return self.unread is not None or self.open >= self.cap

    def describe(self) -> str:
        if self.unread is not None:
            return f"{self.kind}: the open outcomes could not be read ({self.unread})"
        parts = [f"{self.in_flight} run(s) in flight"]
        if self.read is not None:
            parts.insert(0, f"{self.read} open outside")
        return f"{self.kind}: {self.open} of {self.cap} ({', '.join(parts)})"


def counted_from(output: Any, select: str | None) -> int:
    """How many outcomes a reading's output names as open: the length of the list the path
    selects, or the number it selects. Anything else is a ValueError that says so."""
    try:
        found = part(output, select)
    except KeyError as error:
        raise ValueError(f"the output has no {select!r}") from error
    if isinstance(found, list | tuple):
        return len(found)
    if isinstance(found, int) and not isinstance(found, bool) and found >= 0:
        return found
    raise ValueError(f"{select or 'the output'!s} is neither a list nor a count of open outcomes")


def document(
    counts: Iterable[Counted], *, run_id: str, process_version: str, at: datetime
) -> dict[str, Any]:
    """The facts of a decision at the cap, as the record its ledger entry names."""
    return {
        "rule": "open_work.cap",
        "run_id": run_id,
        "process_version": process_version,
        "at": at.isoformat(),
        "kinds": {c.kind: c.model_dump(mode="json", exclude_none=True) for c in counts},
    }
