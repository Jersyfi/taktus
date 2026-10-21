"""The quality history of every process, as a projection of the ledger (ADR-0105 §9).

`autonomy.history` computes the history of one process from every entry of the tenant. The
projection holds what that computation needs and folds the entries after its last read into it,
so that a proposal or a registration reads the entries since the last one, not the ledger.

Per process it keeps the runs that have begun and not ended, the number of runs that ended, the
newest ended run that failed (the *anchor*), and the start of every run that ended cleanly after
the anchor began. The clean runs in a row are those: a failed run after them would have become
the anchor. A run that ended is dropped; an entry of it recorded later changes nothing, in the
full computation as here. `tests/components/process/test_quality.py` rebuilds the projection and
compares it with `autonomy.history`.
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.components.process.domain.service.autonomy import CLEAN_STEP_OUTCOMES, QualityHistory
from taktus.shared.v1 import LedgerEntry

KINDS = frozenset({"run.created", "step.finished", "run.escalated", "run.finished"})


@dataclass
class Quality:
    """One process's runs, as far as its history counts them."""

    ended: int = 0
    anchor: tuple[int, str] | None = None
    """The sequence number of the `run.created` and the id of the newest ended run, by its
    start, that failed; None when no run ended in failure."""
    clean: list[int] = field(default_factory=list)
    """The start of every run that ended cleanly and began after the anchor, ascending."""
    running: dict[str, tuple[int, bool]] = field(default_factory=dict)
    """The runs that began and have not ended: their start, and whether a step failed."""


@dataclass
class Qualities:
    processes: dict[str, Quality] = field(default_factory=dict)

    def history(self, process_id: str) -> QualityHistory:
        held = self.processes.get(process_id) or Quality()
        return QualityHistory(
            process_id=process_id,
            clean=len(held.clean),
            ended=held.ended,
            last_failed=None if held.anchor is None else held.anchor[1],
        )


class QualityProjection:
    name = "process.quality.v1"
    kinds: frozenset[str] | None = KINDS

    def empty(self) -> Qualities:
        return Qualities()

    def fold(self, state: Qualities, entry: LedgerEntry) -> Qualities:
        run_id, version = entry.refs.run_id, entry.refs.process_version
        if entry.rehearsal or run_id is None or version is None:
            return state
        held = state.processes.setdefault(version.split("@", 1)[0], Quality())
        if entry.kind == "run.created":
            held.running.setdefault(run_id, (entry.seq, False))
        elif run_id in held.running:
            start, failed = held.running[run_id]
            if entry.kind == "step.finished":
                if (entry.outcome or "") not in CLEAN_STEP_OUTCOMES:
                    held.running[run_id] = (start, True)
            elif entry.kind == "run.escalated":
                _end(held, run_id, start, failed=True)
            elif entry.kind == "run.finished":
                _end(held, run_id, start, failed=failed)
        return state

    def dump(self, state: Qualities) -> dict[str, Any]:
        return {
            "processes": {
                process: {
                    "ended": held.ended,
                    "anchor": None if held.anchor is None else list(held.anchor),
                    "clean": held.clean,
                    "running": {run: list(found) for run, found in held.running.items()},
                }
                for process, held in sorted(state.processes.items())
            }
        }

    def load(self, document: Mapping[str, Any]) -> Qualities:
        state = Qualities()
        for process, held in document["processes"].items():
            state.processes[process] = Quality(
                ended=held["ended"],
                anchor=None if held["anchor"] is None else (held["anchor"][0], held["anchor"][1]),
                clean=list(held["clean"]),
                running={run: (found[0], found[1]) for run, found in held["running"].items()},
            )
        return state


def _end(held: Quality, run_id: str, start: int, *, failed: bool) -> None:
    del held.running[run_id]
    held.ended += 1
    if held.anchor is not None and start < held.anchor[0]:
        return  # began before the newest failed run: it is not among the runs in a row
    if failed:
        held.anchor = (start, run_id)
        held.clean = [c for c in held.clean if c > start]
    else:
        insort(held.clean, start)


QUALITY = QualityProjection()
