"""What Taktus is working on, folded from the ledger alone (ADR-0236 §1, UC-1.5).

"What are you working on?" is answered from the entries a run writes as its state changes, and
from no second record of state: the answer cannot differ from what the ledger says. The
projection keeps, for every run that has not ended, its process version, its state, since
when it is in that state, the step it is at, and what it waits for — the cause of a halt, a
person. A run that finished, or was cancelled, leaves it.

Who may see which run is not decided here: the caller filters the rows by the one predicate
of the reporting component (UC-6.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from taktus.shared.v1 import LedgerEntry

STATE_KINDS: Mapping[str, str] = {
    "run.created": "planned",
    "run.started": "running",
    "run.resumed": "running",
    "run.recovered": "running",
    "run.waiting_human": "waiting_human",
    "run.halted": "halted",
    "run.escalated": "escalated",
}
"""The entries that change a run's state, and the state each leaves it in."""

ENDED_KINDS = frozenset({"run.finished"})

STEP_KINDS = frozenset({"step.started", "step.waiting", "step.awaiting"})
"""The entries that name the step a run is at."""

ASKED_KINDS = frozenset({"run.pause_asked", "run.cancel_asked"})
"""A pause or a cancellation asked and not yet landed: the run says so until its boundary."""


@dataclass(frozen=True)
class Working:
    """One run that has not ended, as the ledger has it."""

    run_id: str
    process_version: str | None
    state: str
    since: datetime
    step: str | None = None
    waits_for: str | None = None
    """The cause of a halt or an escalation, `a person` for a run that waits for one, or the
    pause or cancellation asked of it; None for a run that works."""

    def document(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "process_version": self.process_version,
            "state": self.state,
            "since": self.since.isoformat(),
            "step": self.step,
            "waits_for": self.waits_for,
        }

    @staticmethod
    def of(document: Mapping[str, Any]) -> Working:
        return Working(
            run_id=document["run_id"],
            process_version=document.get("process_version"),
            state=document["state"],
            since=datetime.fromisoformat(document["since"]),
            step=document.get("step"),
            waits_for=document.get("waits_for"),
        )


CurrentWork = Mapping[str, Working]


def fold(state: CurrentWork, entry: LedgerEntry) -> CurrentWork:
    run_id = entry.refs.run_id
    if run_id is None:
        return state
    kind = entry.kind
    if kind in ENDED_KINDS or (kind == "run.halted" and entry.outcome == "cancelled"):
        if run_id not in state:
            return state
        return {k: v for k, v in state.items() if k != run_id}
    known = state.get(run_id)
    if kind in STATE_KINDS:
        new_state = STATE_KINDS[kind]
        waits: str | None = None
        if new_state == "waiting_human":
            waits = "a person"
        elif new_state in ("halted", "escalated"):
            waits = entry.outcome
        working = Working(
            run_id=run_id,
            process_version=entry.refs.process_version
            or (None if known is None else known.process_version),
            state=new_state,
            since=entry.ts,
            step=None if known is None else known.step,
            waits_for=waits,
        )
        return {**state, run_id: working}
    if known is None:
        return state
    if kind in STEP_KINDS and entry.refs.step_id is not None:
        return {**state, run_id: replace(known, step=entry.refs.step_id)}
    if kind in ASKED_KINDS:
        asked = "pause" if kind == "run.pause_asked" else "cancellation"
        return {**state, run_id: replace(known, waits_for=f"its {asked}, asked")}
    return state


class CurrentWorkProjection:
    """The runs that have not ended, by run (ADR-0105): what a status answer is drawn from."""

    name = "run.current_work.v1"
    kinds: frozenset[str] | None = frozenset(
        {*STATE_KINDS, *ENDED_KINDS, *STEP_KINDS, *ASKED_KINDS}
    )

    def empty(self) -> CurrentWork:
        return {}

    def fold(self, state: CurrentWork, entry: LedgerEntry) -> CurrentWork:
        return fold(state, entry)

    def dump(self, state: CurrentWork) -> dict[str, Any]:
        return {"runs": [w.document() for w in state.values()]}

    def load(self, document: Mapping[str, Any]) -> CurrentWork:
        return {d["run_id"]: Working.of(d) for d in document.get("runs", [])}


def answer(rows: list[Working]) -> str:
    """The answer to "what are you working on?", one line per run, oldest state first."""
    if not rows:
        return "Nothing is running that you may see."
    lines = [f"{len(rows)} run{'s' if len(rows) != 1 else ''} you may see:"]
    for w in sorted(rows, key=lambda r: (r.since, r.run_id)):
        line = f"• {w.run_id} of {w.process_version or 'an unnamed process'}: {w.state}"
        if w.step is not None:
            line += f" at step {w.step}"
        line += f" since {w.since.isoformat(timespec='seconds')}"
        if w.waits_for is not None:
            line += f", waits for {w.waits_for}"
        lines.append(line)
    return "\n".join(lines)
