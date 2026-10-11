"""An intake event: the channel's half of a command, as a connector normalised it, waiting for
the identity component to say who the sender is (control-plane.md §2).

A connector cannot know the Taktus identity behind an account, so what it accepts is not yet a
command and gets no execution. It is kept, under the event identifier the source system gave
the delivery, so that it can be completed into a command by the identity the identity
component answers (`complete_intake.py`), and so that a person can see what arrived and was
not acted on. A redelivery changes nothing: an event once completed stays completed
(ADR-0048 §4). Only an event whose sender the
identity component placed is kept; an unknown sender's is kept nowhere — except a contribution
on a public channel, kept as data of its triage and never as a command (ADR-0088).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Capability, Value

UNKNOWN_ACCOUNT = "unknown"
"""What a contribution's event holds for the sender's account: not the account (ADR-0088)."""


class IntakeStatus(StrEnum):
    AWAITING_IDENTITY = "awaiting_identity"
    """Accepted by the connector and placed in a tenant; not yet completed into a command."""
    COMPLETED = "completed"
    """Completed into the command `command_id` by the identity the resolver answered."""
    CONTRIBUTION = "contribution"
    """An issue or pull request a sender nobody could place opened on a public channel, kept as
    data of the channel's triage (UC-1.9, ADR-0088): never completed into a command of the
    sender, and kept without their account or their text."""


class IntakeEvent(Value):
    id: str = Field(min_length=1)
    """The source system's identifier for the delivery (`Intake.event_id`)."""
    tenant: str = Field(min_length=1)
    channel: Capability
    event: str = Field(min_length=1)
    sender_account: str = Field(min_length=1)
    sender_kind: str = Field(min_length=1)
    intent: str
    context: dict[str, Any]
    reply_channel: Capability
    reply_address: str = Field(min_length=1)
    reply_thread: str | None = None
    occurred_at: datetime
    received_at: datetime
    status: IntakeStatus = IntakeStatus.AWAITING_IDENTITY
    command_id: str | None = Field(default=None, min_length=1)
    completed_at: datetime | None = None
