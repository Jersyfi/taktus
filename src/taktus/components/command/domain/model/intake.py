"""An intake event: the channel's half of a command, as a connector normalised it, waiting for
the identity component to say who the sender is (control-plane.md §2).

A connector cannot know the Taktus identity behind an account, so what it accepts is not yet a
command and gets no execution. It is kept, under the event identifier the source system gave
the delivery — a redelivery replaces rather than duplicates — so that it can be completed
into a command by the identity the identity port answers (`complete_intake.py`; today the
provisional operator identity, DEC-0013), and so that a person can see what arrived and was
not acted on.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Capability, Value


class IntakeStatus(StrEnum):
    AWAITING_IDENTITY = "awaiting_identity"
    """Accepted by the connector and placed in a tenant; not yet completed into a command."""
    COMPLETED = "completed"
    """Completed into the command `command_id` by the identity the resolver answered."""


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
