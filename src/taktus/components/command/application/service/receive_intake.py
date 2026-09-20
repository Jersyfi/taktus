"""Use case: a delivery on a channel becomes an intake event, or is refused.

The connector that serves the channel decides — signature first, then normalisation
(`contracts/connector/v1` §7) — and this handler keeps what it accepted as an `IntakeEvent`,
awaiting completion into a command. Where it is kept is the identity port's answer: the
sender, as the source system names them, is placed in a tenant by the identity resolver
(control-plane.md §2). A sender that cannot be placed gets no execution and no row — the
outcome says `unknown_sender`, and the channel may answer with an offer to register. A refusal
is returned as the connector stated it and nothing is stored: an unsigned delivery leaves no
trace but a log line. A channel no connector serves is `UnknownChannel`.

Without a resolver — a test, an instance with no identity configured — the caller names the
tenant to keep the event in, and that is the guess this handler otherwise exists to avoid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from taktus.components.command.domain.model import IntakeEvent
from taktus.ports.connector import (
    ConnectorError,
    Delivery,
    IntakeConnector,
    Refusal,
    Sender,
)
from taktus.ports.identity import IdentityResolver
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
    tenant: Tenant | None = None
    """Where to keep the event when no identity resolver is configured: the surface's
    fallback. With a resolver, the resolver places the sender and this is not consulted."""


@dataclass(frozen=True)
class IntakeOutcome:
    """Exactly one of the three: accepted and kept, refused by the connector, or accepted by
    the connector and not placed because the sender is unknown."""

    accepted: IntakeEvent | None = None
    refused: Refusal | None = None
    unknown_sender: Sender | None = None


class ReceiveIntakeHandler:
    def __init__(
        self,
        connectors: Mapping[Capability, IntakeConnector],
        events: Repository[IntakeEvent],
        work: UnitOfWork,
        telemetry: Telemetry | None = None,
        identities: IdentityResolver | None = None,
    ) -> None:
        self._connectors = connectors
        self._events = events
        self._work = work
        self._telemetry = telemetry
        self._identities = identities

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
            attributes = {"channel": command.channel}
            if command.tenant is not None:
                attributes["tenant"] = command.tenant
            async with self._telemetry.span("connector.intake", attributes) as span:
                result = await connector.intake(command.delivery)
                span.set_attribute("intake.outcome", "refused" if result.refused else "accepted")
        if result.refused is not None:
            return IntakeOutcome(refused=result.refused)
        accepted = result.accepted
        if accepted is None:  # unreachable: a result is exactly one of the two
            raise ConnectorError("the intake result is neither accepted nor refused")
        tenant = await self._place(command, accepted.sender)
        if tenant is None:
            return IntakeOutcome(unknown_sender=accepted.sender)
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

    async def _place(self, command: ReceiveIntake, sender: Sender) -> Tenant | None:
        if self._identities is None:
            return command.tenant
        resolution = await self._identities.resolve(command.channel, sender.account)
        return None if resolution is None else resolution.tenant
