"""The automation coach: hints drawn from a person's own requests (ADR-0240, UC-13.3).

What a person asks Taktus for again and again is a candidate for an automation. The coach finds
such a pattern among the person's own commands, by a rule, and offers the person a hint. Everything
here belongs to that person (ADR-0015, principle 14): the settings, the hints and whether an
automation a hint led to still runs. Nobody else reads any of it under the person's name; the share
of hints that led to a lasting automation is shown to others only aggregated by role.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from taktus.shared.v1 import Value

DEFAULT_HINTS_PER_WEEK = 1
"""How many hints a week a person receives until they set it: one, stated where it is set."""

DEFAULT_LASTING_DAYS = 28
"""After how many days an accepted hint's automation is checked for still running, until the
tenant configures it."""


class CoachSettings(Value):
    """One person's coach. Keyed by the identity; read and changed only by it."""

    id: str = Field(min_length=1)
    """The identity the settings belong to."""
    tenant: str = Field(min_length=1)
    on: bool = True
    hints_per_week: int = Field(default=DEFAULT_HINTS_PER_WEEK, ge=0, le=7)
    observed_since: datetime | None = None
    """From when the person's requests are read for hints: the moment the coach was switched on.
    None while it is off; a request made while it was off is never read for a hint."""


class HintState(StrEnum):
    OFFERED = "offered"
    DISMISSED = "dismissed"
    """Never shown again for the same pattern."""
    ACCEPTED = "accepted"


class CoachHint(Value):
    id: str = Field(min_length=1)
    """`<identity>:<pattern>`: one hint per person and pattern, ever."""
    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
    says: str = Field(min_length=1)
    procedure: str = Field(min_length=1)
    """What recurs, as a procedure of a process: the request and its cadence, never who asks."""
    state: HintState = HintState.OFFERED
    offered_at: datetime
    process_version: str | None = Field(default=None, min_length=1)
    """The automation the hint led to, once accepted."""
    accepted_at: datetime | None = None
    lasting: bool | None = None
    """Whether the automation still ran after the tenant's period; None until it was checked."""


class CoachPolicy(Value):
    """A tenant's setting for the coach: after how long an automation counts as lasting."""

    id: str = Field(min_length=1)
    """The tenant."""
    lasting_days: int = Field(default=DEFAULT_LASTING_DAYS, ge=1, le=365)


class ProcedureDraft(Value):
    """What the coach hands to the first stage of the skill lifecycle (UC-14.2): a procedure,
    and the person it belongs to. The procedure names no person."""

    owner: str = Field(min_length=1)
    procedure: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
