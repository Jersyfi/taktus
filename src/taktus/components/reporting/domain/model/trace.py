"""The trace inside a step, as a reader sees it (ADR-0135, UC-6.14).

Every line carries the worker's event as the trace keeps it, and a sentence made from it: its
text equivalent. Nothing in a trace names a person: a line is what a worker did, and a share
names a role.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Value

OWNER = "owner"
"""The role every trace is shown to without a share: the role a decision is addressed to when
an anchor names none (NTC-0230)."""


class TraceEntry(Value):
    position: int = Field(ge=1)
    ts: datetime
    type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    """The line as a sentence: its text equivalent."""
    detail: dict[str, Any] = Field(default_factory=dict)


class TraceView(Value):
    """A step's trace, from one position on, as one reader may see it."""

    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    """The step's state, as the run component records it."""
    open: bool
    """Whether more lines may come: the step is in flight. A reader asks again while it is."""
    lines: tuple[TraceEntry, ...] = ()
    after: int = Field(ge=0)
    """The last position read: what the next read passes as `after`."""
    shared_with: tuple[str, ...] = ()
    """The roles the trace is shared with, beside the owner's."""
    link: str = Field(min_length=1)
    """Where the web app shows the trace, relative to the surface: what a share hands on."""
