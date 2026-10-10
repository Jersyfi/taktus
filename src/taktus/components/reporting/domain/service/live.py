"""The stream of changes, as rules (ADR-0055 §3, §4, §6). Pure: no reading, no time.

Which entries are changes, how one is projected, which belong to a scope, and when a reader who
resumes receives a fresh snapshot instead of what it missed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from taktus.components.reporting.domain.model.live import (
    Change,
    Reader,
    RunRef,
    Scope,
    ScopeKind,
    StateAfter,
)
from taktus.components.reporting.domain.service.visibility import may_see
from taktus.shared.v1 import LedgerEntry

MAX_BEHIND = 1000
"""A reader further behind than this many entries of its tenant receives a fresh snapshot
instead of every change in between."""

type StateOf = Callable[[str, str | None], StateAfter | None]
"""Which state an entry of this kind and outcome led to; None for an entry that is no change of
state. Published by the components that own the state machines."""


def in_scope(scope: Scope, run: RunRef) -> bool:
    if scope.kind is ScopeKind.RUN:
        return run.id == scope.id
    if scope.kind is ScopeKind.PROCESS:
        return run.process == scope.id
    return True


def project(entry: LedgerEntry, state: StateAfter) -> Change | None:
    """The change an entry is, or None for one that names no run. The entry's actor, its
    consumption, its model, its adapter and its digest are left out: no person, no figure, no
    content."""
    refs = entry.refs
    led = StateAfter(
        run=state.run,
        # A step's state only where the entry names a step, a request's only where it names one.
        step=state.step if refs.step_id is not None else None,
        decision_request=state.decision_request if refs.decision_request_id else None,
    )
    if refs.run_id is None or not led.document():
        return None
    return Change(
        position=entry.hash,
        run=refs.run_id,
        step=refs.step_id,
        decision_request=refs.decision_request_id,
        kind=entry.kind,
        outcome=entry.outcome,
        method=entry.method,
        recorded_at=entry.ts,
        rehearsal=bool(entry.rehearsal),
        state=led,
    )


def needs_snapshot(position: int | None, head: int) -> bool:
    """Whether a reader resuming from `position` receives a fresh snapshot: the position is
    unknown in the tenant, or more than `MAX_BEHIND` entries lie behind it."""
    return position is None or head - position > MAX_BEHIND


def visible(reader: Reader, scope: Scope, changes: Iterable[tuple[Change, RunRef]]) -> list[Change]:
    """The changes this reader receives, in order: in its scope, and of a run it may see now.
    Every other is absent — not replaced, not counted."""
    return [change for change, run in changes if in_scope(scope, run) and may_see(reader, run)]
