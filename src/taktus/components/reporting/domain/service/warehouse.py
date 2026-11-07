"""A warehouse figure as the export carries it (UC-5.6 §2, ADR-0262 §5, ADR-0291 §3). Pure: a
signal judged now, beside its corridor and the query that read it, in; the figure out.

A warehouse figure is a signal whose step queries the warehouse. The export carries the value
the corridor judged, or withholds it with the reason the signal is not measured. Its basis names
the query by reference — the ledger's `query.sent` entry — never by its text.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.components.reporting.domain.model.signal import Corridor, Judged, Level
from taktus.components.reporting.domain.model.views import Shown
from taktus.shared.v1 import Value

FIGURE = "signal.warehouse"
OWNER = "reporting"
DEFINITION = (
    "the number a signal reads from a step that queried the warehouse, as its corridor judges "
    "it now"
)
WITHHELD = {
    "failed": "the newest reading of the warehouse failed",
    "not_admissible": "the newest reading of the warehouse was not admitted",
    "not_a_number": "the warehouse answered no number where the corridor reads it",
    "no_measurement": "no reading of the warehouse is recent enough",
    "too_little_history": "too few readings of the warehouse to compute the corridor",
}


class Reading(Value):
    """The query a warehouse figure was read by, by reference."""

    operation: str = Field(min_length=1)
    fixed: bool
    """The query is literal text in the process version, reviewed when it was registered."""
    seq: int | None = None
    """The ledger's `query.sent` entry of the newest reading; None where none is recorded."""
    digest: str | None = None
    sent_at: datetime | None = None


def figure(corridor: Corridor, judged: Judged, reading: Reading) -> Shown:
    """The warehouse figure of one signal, as the export and the views carry it."""
    unmeasured = judged.level is Level.UNMEASURED
    withheld = (
        WITHHELD.get(judged.reason or "", "the signal is not measured") if unmeasured else None
    )
    query: dict[str, Any] = {"operation": reading.operation, "fixed": reading.fixed}
    if reading.seq is not None:
        query |= {
            "ledger_seq": reading.seq,
            "digest": reading.digest,
            "sent_at": None if reading.sent_at is None else reading.sent_at.isoformat(),
        }
    if judged.run_id is not None:
        query["text_at"] = f"/levels/runs/{judged.run_id}/steps/{corridor.step}/queries"
    return Shown(
        id=FIGURE,
        component=OWNER,
        definition=DEFINITION,
        unit="as the warehouse answers it",
        scope="process",
        subject=corridor.process,
        until=judged.at,
        value=None if unmeasured else judged.value,
        withheld=withheld,
        method=(
            f"read through {reading.operation} by "
            + (
                "the query fixed in the process version"
                if reading.fixed
                else "a query given at run time"
            )
            + f", at {corridor.select or 'the whole result'}; a text that is a decimal number "
            "is read as that number (ADR-0262 §5)"
        ),
        basis={
            "signal": corridor.signal,
            "corridor": corridor.id,
            "step": corridor.step,
            "level": judged.level.value,
            "yellow_at": judged.yellow_at,
            "red_at": judged.red_at,
            "run_id": judged.run_id,
            "process_version": judged.process_version,
            "at": None if judged.at is None else judged.at.isoformat(),
            "query": query,
        },
    )
