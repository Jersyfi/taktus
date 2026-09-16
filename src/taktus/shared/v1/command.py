"""Command.json: the normalised entry into the one execution path."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from taktus.shared.v1.capability import Capability
from taktus.shared.v1.value import Value


class Intent(Value):
    raw: str
    recognised: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]*$")


class ReplyTo(Value):
    channel: Capability
    address: str = Field(min_length=1)
    thread: str | None = None


class Command(Value):
    id: str = Field(min_length=1)
    channel: Capability
    identity: str = Field(min_length=1)
    org_path: tuple[str, ...] = Field(min_length=1)
    intent: Intent
    # The channel context has no fixed shape: an issue, a thread, a file, a previous run. The
    # schema says `type: object` and nothing more, so the values are whatever JSON carries.
    context: dict[str, Any] | None = None
    reply_to: ReplyTo
    received_at: datetime
