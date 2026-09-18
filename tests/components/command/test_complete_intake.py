"""An intake event is placed by the identity port and completed into a command by it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.identity import ProvisionalOperatorIdentity
from taktus.adapters.driven.memory import MemoryPersistence, MemoryRepository
from taktus.components.command.application.service import (
    AlreadyCompleted,
    CompleteIntake,
    CompleteIntakeHandler,
    ReceiveIntake,
    ReceiveIntakeHandler,
    UnknownIntakeEvent,
    UnknownSender,
)
from taktus.components.command.domain.model import IntakeEvent, IntakeStatus
from taktus.ports.connector import Delivery, IntakeResult
from taktus.ports.identity import IdentityResolver, Resolution
from taktus.shared.v1 import Command

AT = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
ACCEPTED = IntakeResult.model_validate(
    {
        "accepted": {
            "event_id": "dlv_1",
            "event": "issue_comment.created",
            "channel": "channel.repo",
            "sender": {"account": "100200", "kind": "person"},
            "intent": {"raw": "@taktus refine this"},
            "context": {"repository": "acme/product", "issue": "11"},
            "reply_to": {"channel": "channel.repo", "address": "acme/product#11"},
            "occurred_at": "2026-09-19T07:59:00Z",
        }
    }
)


class Connector:
    async def intake(self, delivery: Delivery) -> IntakeResult:
        return ACCEPTED


class Nobody(IdentityResolver):
    async def resolve(
        self, channel: str, account: str, *, tenant: str | None = None
    ) -> Resolution | None:
        return None


class Setup:
    def __init__(self, resolver: IdentityResolver) -> None:
        self.persistence = MemoryPersistence()
        self.events = MemoryRepository(self.persistence, IntakeEvent)
        self.commands = MemoryRepository(self.persistence, Command)
        self.receive = ReceiveIntakeHandler(
            {"channel.repo": Connector()}, self.events, self.persistence, identities=resolver
        )
        self.complete = CompleteIntakeHandler(
            self.events, self.commands, resolver, self.persistence, FakeClock(AT), FakeIdentifiers()
        )
        self.delivery = Delivery(headers={}, body="{}", received_at=AT)


async def test_the_resolver_places_the_event_and_completes_it_as_the_operator() -> None:
    given = Setup(ProvisionalOperatorIdentity({"default": "idn_owner"}))
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="ignored")
    )
    assert outcome.accepted is not None
    assert outcome.accepted.tenant == "default", "placed by the resolver, not by the hint"
    assert outcome.accepted.status is IntakeStatus.AWAITING_IDENTITY

    command = await given.complete.execute(CompleteIntake(tenant="default", event_id="dlv_1"))
    assert command.identity == "idn_owner" and command.org_path == ("default",)
    assert command.channel == "channel.repo" and command.intent.raw == "@taktus refine this"
    assert command.context is not None
    assert command.context["issue"] == "11" and command.context["event_id"] == "dlv_1"
    assert command.context["identity_provisional"] is True, "the command says what it carries"
    assert command.reply_to.address == "acme/product#11"
    async with given.persistence.transaction("default"):
        stored = await given.commands.get("default", command.id)
        event = await given.events.get("default", "dlv_1")
    assert stored == command
    assert event is not None and event.status is IntakeStatus.COMPLETED
    assert event.command_id == command.id and event.completed_at is not None

    with pytest.raises(AlreadyCompleted) as again:
        await given.complete.execute(CompleteIntake(tenant="default", event_id="dlv_1"))
    assert again.value.command_id == command.id
    with pytest.raises(UnknownIntakeEvent):
        await given.complete.execute(CompleteIntake(tenant="default", event_id="dlv_9"))


async def test_an_unknown_sender_is_kept_nowhere_and_completed_never() -> None:
    given = Setup(Nobody())
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and outcome.accepted is None
    assert outcome.unknown_sender.account == "100200"
    async with given.persistence.transaction("default"):
        assert await given.events.list("default") == []

    # An event that was placed earlier, by a resolver that has since forgotten the sender.
    placed = Setup(ProvisionalOperatorIdentity({"default": "idn_owner"}))
    await placed.receive.execute(ReceiveIntake(channel="channel.repo", delivery=placed.delivery))
    forgotten = CompleteIntakeHandler(
        placed.events,
        placed.commands,
        Nobody(),
        placed.persistence,
        FakeClock(AT),
        FakeIdentifiers(),
    )
    with pytest.raises(UnknownSender):
        await forgotten.execute(CompleteIntake(tenant="default", event_id="dlv_1"))


async def test_without_a_resolver_the_caller_names_the_tenant() -> None:
    persistence = MemoryPersistence()
    events = MemoryRepository(persistence, IntakeEvent)
    handler = ReceiveIntakeHandler({"channel.repo": Connector()}, events, persistence)
    delivery = Delivery(headers={}, body="{}", received_at=AT)
    outcome = await handler.execute(
        ReceiveIntake(channel="channel.repo", delivery=delivery, tenant="named")
    )
    assert outcome.accepted is not None and outcome.accepted.tenant == "named"
    nowhere = await handler.execute(ReceiveIntake(channel="channel.repo", delivery=delivery))
    assert nowhere.unknown_sender is not None
