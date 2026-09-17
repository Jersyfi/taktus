"""Use case: a delivery on a channel becomes an intake event, or is refused.

The connector that serves the channel decides — signature first, then normalisation
(`contracts/connector/v1` §7) — and this handler keeps what it accepted as an `IntakeEvent`
under the tenant it was received for, awaiting identity. A refusal is returned as the
connector stated it and nothing is stored: an unsigned delivery leaves no trace but a log line.
A channel no connector serves is `UnknownChannel`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from taktus.components.command.domain.model import IntakeEvent
from taktus.ports.connector import ConnectorError, Delivery, IntakeConnector, Refusal
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability


class UnknownChannel(Exception):
    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"no connector serves the channel {channel!r}")


@dataclass(frozen=True)
class ReceiveIntake:
    tenant: Tenant
    channel: Capability
    delivery: Delivery


@dataclass(frozen=True)
class IntakeOutcome:
    accepted: IntakeEvent | None = None
    refused: Refusal | None = None


class ReceiveIntakeHandler:
    def __init__(
        self,
        connectors: Mapping[Capability, IntakeConnector],
        events: Repository[IntakeEvent],
        work: UnitOfWork,
    ) -> None:
        self._connectors = connectors
        self._events = events
        self._work = work

    @property
    def channels(self) -> tuple[Capability, ...]:
        return tuple(self._connectors)

    async def execute(self, command: ReceiveIntake) -> IntakeOutcome:
        connector = self._connectors.get(command.channel)
        if connector is None:
            raise UnknownChannel(command.channel)
        result = await connector.intake(command.delivery)
        if result.refused is not None:
            return IntakeOutcome(refused=result.refused)
        accepted = result.accepted
        if accepted is None:  # unreachable: a result is exactly one of the two
            raise ConnectorError("the intake result is neither accepted nor refused")
        event = IntakeEvent(
            id=accepted.event_id,
            tenant=command.tenant,
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
        async with self._work.transaction(command.tenant):
            await self._events.put(command.tenant, event)
        return IntakeOutcome(accepted=event)
