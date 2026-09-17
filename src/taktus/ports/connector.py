"""CONTRACT 2, the client side: how the core reaches a connector (contracts/connector/v1).

Today the intake direction only (§7 of the contract): a delivery — headers, the raw body, when
it arrived — becomes an accepted intake, the channel's half of a command, or a refusal with its
reason. The shapes are bound the way the worker contract's are (frozen, closed). The action
direction — calling an operation with a call context — arrives with the run's binding of
connector steps (`0.2.0`); the port grows then, the adapter with it.

The core never sees a URL or a transport; the adapter under `adapters/driven/connectors/mcp`
speaks MCP to the connector.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value


class ConnectorError(Exception):
    """The connector did not answer, or answered with something the contract does not allow.
    The message names the connector's endpoint and the fault, never a credential."""


class Delivery(Value):
    """`IntakeArguments`: one event as it arrived, before anything is believed about it."""

    headers: Mapping[str, str]
    body: str
    received_at: datetime


class SenderKind(StrEnum):
    PERSON = "person"
    AUTOMATION = "automation"


class Sender(Value):
    account: str = Field(min_length=1)
    kind: SenderKind


class IntakeIntent(Value):
    raw: str


class IntakeReplyTo(Value):
    channel: Capability
    address: str = Field(min_length=1)
    thread: str | None = None


class Intake(Value):
    """`Intake`: an accepted event, normalised as far as the channel can — the command of the
    shared kernel without identity and org_path, which the identity component adds."""

    event_id: str = Field(min_length=1)
    event: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    channel: Capability
    sender: Sender
    intent: IntakeIntent
    context: dict[str, Any]
    reply_to: IntakeReplyTo
    occurred_at: datetime


class RefusalReason(StrEnum):
    UNSIGNED = "unsigned"
    BAD_SIGNATURE = "bad_signature"
    MALFORMED = "malformed"
    UNSUPPORTED_EVENT = "unsupported_event"
    OWN_ACTION = "own_action"


class Refusal(Value):
    reason: RefusalReason
    detail: str = Field(min_length=1)


class IntakeResult(Value):
    """Exactly one of `accepted` and `refused`."""

    accepted: Intake | None = None
    refused: Refusal | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> IntakeResult:
        if (self.accepted is None) == (self.refused is None):
            raise ValueError("an intake result is exactly one of accepted and refused")
        return self


class IntakeConnector(Protocol):
    async def intake(self, delivery: Delivery) -> IntakeResult:
        """Hand the delivery to the connector's `intake` tool and return what it decided.
        Raises `ConnectorError` when the connector cannot be reached or breaks the contract."""
        ...
