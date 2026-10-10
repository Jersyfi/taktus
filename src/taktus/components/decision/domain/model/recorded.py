"""Which status a ledger entry of a decision request leads to, published beside the request.

A decision request's every change of status is recorded in the ledger with it
(`application/service/_ledger.py`). The entry carries a kind and an outcome token, never the
status. This table says which status each leads to, so that whoever reads the ledger — the
stream of changes of ADR-0055 among them — reads it from one place.
"""

from __future__ import annotations

from taktus.shared.v1 import DecisionStatus

RAISED = "decision.raised"
ANSWERED = "decision.answered"
REREAD = "decision.reread"
CONFIRMED = "decision.confirmed"
APPLIED = "decision.applied"

INTERPRETED = "interpreted"
"""The outcome of `decision.answered` when an option could be read from the answer."""

RECORDED_KINDS: frozenset[str] = frozenset({RAISED, ANSWERED, REREAD, CONFIRMED, APPLIED})


def status_after(kind: str, outcome: str | None) -> DecisionStatus | None:
    """The status the entry of this kind and outcome led to, or None for an entry that is not
    a decision request's."""
    if kind == RAISED or kind == REREAD:
        # Raised, or the reading of its answer rejected: it is open again.
        return DecisionStatus.OPEN
    if kind == ANSWERED:
        return DecisionStatus.INTERPRETED if outcome == INTERPRETED else DecisionStatus.ANSWERED
    if kind == CONFIRMED:
        return DecisionStatus.CONFIRMED
    if kind == APPLIED:
        return DecisionStatus.APPLIED
    return None
