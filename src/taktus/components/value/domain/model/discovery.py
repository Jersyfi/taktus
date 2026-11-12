"""A process nobody wrote down, brought to light (UC-9.4, ADR-0245 §2).

It passes five stages in order. Each is recorded as a ledger entry `discovery.<stage>`; a stage
is refused unless the one before it is reached. The decision to automate is a person's.

A pattern found in a person's own tools or requests is the person's own until they agree: its
`reader` is that person, and nobody else reads it (`tests/components/value/test_discovery.py`).
Once they agree, `reader` is cleared and the record is a procedure of the organisation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import Value

type Stage = Literal["visible", "documented", "valued", "decided", "automated"]
STAGES: tuple[Stage, ...] = ("visible", "documented", "valued", "decided", "automated")
type Origin = Literal["interview", "pattern", "request"]
type Decision = Literal["automate", "keep"]
AUTOMATION_LEVELS = frozenset({1, 2})
"""A discovered process enters automation at a conservative level (UC-9.4 §2, UC-7.1)."""


class DiscoveryRefused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class DiscoveredProcess(Value):
    id: str = Field(pattern=r"^dsc_[A-Za-z0-9_-]+$")
    tenant: str = Field(min_length=1)
    title: str = Field(min_length=1)
    origin: Origin
    found: str = Field(min_length=1)
    """What was found and where, as a procedure: never how a named person works."""
    stage: Stage = "visible"
    reader: str | None = None
    """For a pattern in a person's own tools or requests: that person, until they agree."""
    description: str | None = None
    owner_role: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]*$")
    minutes_by_hand: float | None = Field(default=None, ge=0)
    cases_per_month: float | None = Field(default=None, ge=0)
    decision: Decision | None = None
    process_id: str | None = None
    """The process it was automated as."""
    at: datetime

    def reached(self, stage: Stage) -> bool:
        return STAGES.index(self.stage) >= STAGES.index(stage)


def next_after(stage: Stage) -> Stage | None:
    at = STAGES.index(stage)
    return None if at + 1 == len(STAGES) else STAGES[at + 1]
