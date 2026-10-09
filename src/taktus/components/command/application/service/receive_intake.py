"""Use case: a delivery on a channel becomes an intake event, or is refused.

The connector that serves the channel decides — signature first, then normalisation
(`contracts/connector/v1` §7) — and this handler keeps what it accepted as an `IntakeEvent`,
awaiting completion into a command. Where it is kept is the identity port's answer: the
sender, as the source system names them, is placed in a tenant by the identity component
(control-plane.md §2). A refusal is returned as the connector stated it and nothing is stored:
an unsigned delivery leaves no trace but a log line. A channel no connector serves is
`UnknownChannel`.

**An unknown sender gets no execution and no row.** The identity component answers them
instead: when what they wrote carries a valid link code, their account is linked; otherwise
they are offered how to link it. The answer is said in the channel, at the event's reply
address, as Taktus itself — to a person, never to an automation — and the outcome says
`unknown_sender` either way. The event is not
kept: the message that carried a code is not a command either.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from taktus.components.command.domain.model import IntakeEvent
from taktus.ports.connector import (
    ChannelReplies,
    ConnectorError,
    Delivery,
    Intake,
    IntakeConnector,
    Refusal,
    Sender,
    SenderKind,
)
from taktus.ports.identity import IdentityResolver, Resolution
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.telemetry import Telemetry
from taktus.shared.v1 import Capability


class UnknownChannel(Exception):
    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"no connector serves the channel {channel!r}")


@dataclass(frozen=True)
class ReceiveIntake:
    channel: Capability
    delivery: Delivery
    tenant: Tenant
    """The tenant the surface receives for: where a reply to a sender nobody could place is
    made. Never where an event is kept — that is the identity component's answer."""


@dataclass(frozen=True)
class IntakeOutcome:
    """Exactly one of the three: accepted and kept, refused by the connector, or accepted by
    the connector and not placed because the sender is unknown. For an unknown sender,
    `replied` says whether the answer reached the channel, and `linked` whether the message
    linked the account."""

    accepted: IntakeEvent | None = None
    refused: Refusal | None = None
    unknown_sender: Sender | None = None
    replied: bool = False
    linked: Resolution | None = None


class ReceiveIntakeHandler:
    def __init__(
        self,
        connectors: Mapping[Capability, IntakeConnector],
        events: Repository[IntakeEvent],
        work: UnitOfWork,
        identities: IdentityResolver,
        telemetry: Telemetry | None = None,
        replies: ChannelReplies | None = None,
    ) -> None:
        self._connectors = connectors
        self._events = events
        self._work = work
        self._identities = identities
        self._telemetry = telemetry
        self._replies = replies

    @property
    def channels(self) -> tuple[Capability, ...]:
        return tuple(self._connectors)

    async def execute(self, command: ReceiveIntake) -> IntakeOutcome:
        connector = self._connectors.get(command.channel)
        if connector is None:
            raise UnknownChannel(command.channel)
        if self._telemetry is None:
            result = await connector.intake(command.delivery)
        else:
            # The connector call is a span of its own: the channel and the tenant, never the
            # delivery — its headers and body are the source system's content.
            attributes = {"channel": command.channel, "tenant": command.tenant}
            async with self._telemetry.span("connector.intake", attributes) as span:
                result = await connector.intake(command.delivery)
                span.set_attribute("intake.outcome", "refused" if result.refused else "accepted")
        if result.refused is not None:
            return IntakeOutcome(refused=result.refused)
        accepted = result.accepted
        if accepted is None:  # unreachable: a result is exactly one of the two
            raise ConnectorError("the intake result is neither accepted nor refused")
        resolution = await self._identities.resolve(command.channel, accepted.sender.account)
        if resolution is None:
            return await self._unknown(command, accepted)
        tenant = resolution.tenant
        event = IntakeEvent(
            id=accepted.event_id,
            tenant=tenant,
            channel=accepted.channel,
            event=accepted.event,
            sender_account=accepted.sender.account,
            sender_kind=accepted.sender.kind,
            intent=accepted.intent.raw,
            context=dict(accepted.context),
            reply_channel=accepted.reply_to.channel,
            reply_address=accepted.reply_to.address,
            reply_thread=accepted.reply_to.thread,
            occurred_at=accepted.occurred_at,
            received_at=command.delivery.received_at,
        )
        async with self._work.transaction(tenant):
            await self._events.put(tenant, event)
        return IntakeOutcome(accepted=event)

    async def _unknown(self, command: ReceiveIntake, accepted: Intake) -> IntakeOutcome:
        answer = await self._identities.unknown_sender(
            command.channel, accepted.sender.account, accepted.intent.raw
        )
        replied = False
        # An automation is not answered: nobody reads the offer, and two automations answering
        # each other would loop. Its event is kept nowhere all the same.
        if self._replies is not None and accepted.sender.kind is SenderKind.PERSON:
            tenant = command.tenant if answer.linked is None else answer.linked.tenant
            # An offer is made once per person and conversation: the key names both, so a
            # second message of the same person there finds the first offer and says nothing
            # new. That a code linked the account is said for the message that carried it.
            to = accepted.reply_to
            key = (
                reply_key(accepted.event_id)
                if answer.linked is not None
                else offer_key(to.channel, to.address, accepted.sender.account)
            )
            replied = await self._replies.reply(tenant, accepted.reply_to, answer.reply, key=key)
        return IntakeOutcome(unknown_sender=accepted.sender, replied=replied, linked=answer.linked)


def offer_key(channel: str, address: str, account: str) -> str:
    """The idempotency key of the offer to one person in one conversation."""
    digest = hashlib.sha256(f"{channel}\n{address}\n{account}".encode()).hexdigest()[:32]
    return f"taktus:intake:offer:{digest}"


def reply_key(event_id: str) -> str:
    """The idempotency key of the answer to one delivery: a redelivery answers once."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", f"taktus:intake:{event_id}:reply")[:128]
