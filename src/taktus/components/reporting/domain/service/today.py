"""What waits, for the start page: one merged list, short, the most urgent first (ADR-0318 §2).

Pure: the records are read elsewhere and handed in as `Waiting`; this module orders them, cuts
the list to its length and keeps every title to one line. Nothing here names a person: a wait
names a request, a need, a report, a run or an alert.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value

WAITS_SHOWN = 5
"""How many waits the start page lists; the counts say how many there are in all."""
TITLE_LENGTH = 120
"""The longest title a wait carries, in characters: one line (DEC-0239)."""


class WaitKind(StrEnum):
    DECISION = "decision"
    """A decision request addressed to the reader."""
    NEED = "need"
    """Something only the owner can provide (ADR-0028)."""
    REPORT = "report"
    """Any other report to the owner that waits for an answer (ADR-0045)."""
    FAILURE = "failure"
    """A run that escalated in the last day."""
    ALERT = "alert"
    """Something that needs a person's action now (ADR-0106)."""


class Waiting(Value):
    """One thing that waits, as the start page lists it."""

    kind: WaitKind
    title: str = Field(min_length=1, max_length=TITLE_LENGTH)
    link: str = Field(min_length=1)
    """Where it is read in the web app: a route after `#`."""
    since: datetime
    urgent: bool = False
    """Past its date, or in effect now: listed before the rest."""


def one_line(text: str) -> str:
    """The first line of a text, cut to `TITLE_LENGTH` characters with an ellipsis."""
    line = " ".join(text.strip().splitlines()[0].split()) if text.strip() else "—"
    return line if len(line) <= TITLE_LENGTH else line[: TITLE_LENGTH - 1].rstrip() + "…"


def waits(found: Iterable[Waiting], shown: int = WAITS_SHOWN) -> tuple[Waiting, ...]:
    """The most urgent first, then the newest; at most `shown` of them."""
    ordered = sorted(found, key=lambda w: (w.since, w.link), reverse=True)
    return tuple(sorted(ordered, key=lambda w: not w.urgent)[:shown])
