"""Use case: an intake event awaiting identity becomes a command.

The channel's half of the command has been waiting as an `IntakeEvent` since the connector
accepted it. The identity port supplies the other half — who acts, in which tenant, under which
organisational path — and the two together are the command of control-plane.md §2, stored with
the event marked completed in one transaction. The command is returned for whoever commissions
a plan from it; nothing is executed here.

A sender the resolver cannot place is `UnknownSender`: the event stays as it is. An event that
was completed before is `AlreadyCompleted`, and the command it produced is named, so that a
redelivery completes nothing twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.command.domain.model import IntakeEvent, IntakeStatus
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Command, Intent, ReplyTo


class UnknownIntakeEvent(Exception):
    def __init__(self, tenant: str, event_id: str) -> None:
        super().__init__(f"tenant {tenant!r} holds no intake event {event_id!r}")


class UnknownSender(Exception):
    def __init__(self, event: IntakeEvent) -> None:
        super().__init__(
            f"the sender of intake event {event.id!r} on {event.channel} cannot be placed; "
            "an unknown sender gets no execution"
        )


class AlreadyCompleted(Exception):
    def __init__(self, event: IntakeEvent) -> None:
        self.command_id = event.command_id
        super().__init__(
            f"intake event {event.id!r} was completed before, into command {event.command_id!r}"
        )


@dataclass(frozen=True)
class CompleteIntake:
    tenant: Tenant
    event_id: str


class CompleteIntakeHandler:
    def __init__(
        self,
        events: Repository[IntakeEvent],
        commands: Repository[Command],
        identities: IdentityResolver,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._events = events
        self._commands = commands
        self._identities = identities
        self._work = work
        self._clock = clock
        self._ids = ids

    async def execute(self, command: CompleteIntake) -> Command:
        async with self._work.transaction(command.tenant):
            event = await self._events.get(command.tenant, command.event_id)
        if event is None:
            raise UnknownIntakeEvent(command.tenant, command.event_id)
        if event.status is IntakeStatus.COMPLETED:
            raise AlreadyCompleted(event)
        resolution = await self._identities.resolve(
            event.channel, event.sender_account, tenant=event.tenant
        )
        if resolution is None:
            raise UnknownSender(event)
        completed = Command(
            id=self._ids.new("cmd"),
            channel=event.channel,
            identity=resolution.identity,
            org_path=resolution.org_path,
            intent=Intent(raw=event.intent),
            context={
                **event.context,
                "event": event.event,
                "event_id": event.id,
                "sender": {"account": event.sender_account, "kind": event.sender_kind},
                "identity_provisional": resolution.provisional,
            },
            reply_to=ReplyTo(
                channel=event.reply_channel,
                address=event.reply_address,
                thread=event.reply_thread,
            ),
            received_at=event.received_at,
        )
        done = event.model_copy(
            update={
                "status": IntakeStatus.COMPLETED,
                "command_id": completed.id,
                "completed_at": self._clock.now(),
            }
        )
        async with self._work.transaction(command.tenant):
            await self._commands.put(command.tenant, completed)
            await self._events.put(command.tenant, done)
        return completed
