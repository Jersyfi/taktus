"""An intake event is placed by the identity component and completed into a command by it.

Without a link nothing is placed: an unknown sender's event is kept nowhere, and the sender is
answered in the channel (UC-1.7)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes.identity import Directory, FakeReplies, directory

from taktus.adapters.driven.memory import MemoryRepository
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
from taktus.ports.connector import Delivery, IntakeReplyTo, IntakeResult, Sender, SenderKind
from taktus.shared.v1 import Command

AT = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)


WINDOW = timedelta(hours=1)


def accepted(
    raw: str = "@taktus refine this",
    context: dict[str, object] | None = None,
    *,
    authored: bool | None = None,
    event: str = "issue_comment.created",
    address: str = "acme/product#11",
) -> IntakeResult:
    intent: dict[str, object] = {"raw": raw}
    if authored is not None:
        intent["authored"] = authored
    return IntakeResult.model_validate(
        {
            "accepted": {
                "event_id": "dlv_1",
                "event": event,
                "channel": "channel.repo",
                "sender": {"account": "100200", "kind": "person"},
                "intent": intent,
                "context": context or {"repository": "acme/product", "issue": "11"},
                "reply_to": {"channel": "channel.repo", "address": address},
                "occurred_at": "2026-09-19T07:59:00Z",
            }
        }
    )


class SlowReplies(FakeReplies):
    """A channel that takes its time to answer, as a service over the network does: another
    delivery runs while the reply is on its way."""

    async def reply(self, tenant: str, to: IntakeReplyTo, text: str, *, key: str) -> bool:
        await asyncio.sleep(0)
        return await super().reply(tenant, to, text, key=key)


class Connector:
    def __init__(self, answer: IntakeResult) -> None:
        self.answer = answer

    async def intake(self, delivery: Delivery) -> IntakeResult:
        return self.answer


class Setup:
    def __init__(self, answer: IntakeResult | None = None) -> None:
        self.identity: Directory = directory()
        self.persistence = self.identity.persistence
        self.events = MemoryRepository(self.persistence, IntakeEvent)
        self.commands = MemoryRepository(self.persistence, Command)
        self.replies = SlowReplies()
        self.connector = Connector(answer or accepted())
        self.clock = FakeClock(AT)
        self.receive = ReceiveIntakeHandler(
            {"channel.repo": self.connector},
            self.events,
            self.persistence,
            self.identity.directory,
            replies=self.replies,
            clock=self.clock,
            offer_window=WINDOW,
        )
        self.complete = CompleteIntakeHandler(
            self.events,
            self.commands,
            self.identity.directory,
            self.persistence,
            FakeClock(AT),
            FakeIdentifiers(),
        )
        self.delivery = Delivery(headers={}, body="{}", received_at=AT)

    async def linked(self, name: str = "idn_ada", org_path: tuple[str, ...] = ()) -> None:
        """The person links account 100200 on the channel with a code from their account."""
        who, _ = await self.identity.person("default", name, org_path)
        code = await self.identity.code(who)
        answer = await self.identity.directory.unknown_sender("channel.repo", "100200", code)
        assert answer.linked is not None


async def test_the_link_places_the_event_and_completes_it_as_the_linked_identity() -> None:
    given = Setup()
    await given.linked(org_path=("default", "product"))
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.accepted is not None
    assert outcome.accepted.tenant == "default"
    assert outcome.accepted.status is IntakeStatus.AWAITING_IDENTITY
    assert given.replies.said == [], "a known sender is not answered by the intake"

    command = await given.complete.execute(CompleteIntake(tenant="default", event_id="dlv_1"))
    assert command.identity == "idn_ada" and command.org_path == ("default", "product")
    assert command.channel == "channel.repo" and command.intent.raw == "@taktus refine this"
    assert command.context is not None
    assert command.context["issue"] == "11" and command.context["event_id"] == "dlv_1"
    assert "identity_provisional" not in command.context, "nothing provisional any more"
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
    """No link, and no adapter that places everybody: the event is kept nowhere, and the
    sender is offered, in the channel, how to link the account."""
    given = Setup()
    await given.identity.person("default", "100200")  # a matching name places nobody
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and outcome.accepted is None
    assert outcome.unknown_sender.account == "100200"
    assert outcome.replied and outcome.linked is None
    ((tenant, to, text, key),) = given.replies.said
    assert tenant == "default" and to.address == "acme/product#11"
    assert "does not know this account" in text and "link code" in text
    assert key.startswith("taktus:intake:offer:"), "once per person and conversation"
    again = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert again.unknown_sender is not None and not again.replied
    assert len(given.replies.said) == 1, "within the window the offer is not made again"
    async with given.persistence.transaction("default"):
        assert await given.events.list("default") == []
        assert await given.commands.list("default") == []

    # An event placed earlier, whose account an administrator has since revoked.
    placed = Setup()
    await placed.linked()
    await placed.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=placed.delivery, tenant="default")
    )
    (link,) = await placed.identity.directory.links("default")
    await placed.identity.directory.revoke("default", link.id)
    with pytest.raises(UnknownSender):
        await placed.complete.execute(CompleteIntake(tenant="default", event_id="dlv_1"))
    async with placed.persistence.transaction("default"):
        assert await placed.commands.list("default") == []


async def test_a_message_carrying_a_link_code_links_the_account_and_is_no_command() -> None:
    given = Setup()
    who, _ = await given.identity.person("default", "idn_ada")
    code = await given.identity.code(who)
    given.connector.answer = accepted(f"@taktus link {code}")
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and outcome.accepted is None
    assert outcome.linked is not None and outcome.linked.identity == "idn_ada"
    assert "now linked" in given.replies.said[0][2]
    async with given.persistence.transaction("default"):
        assert await given.events.list("default") == [], "the code's message is not a command"
    given.connector.answer = accepted()
    again = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert again.accepted is not None, "from now on the account is placed"


async def test_identity_and_path_are_the_components_never_the_connectors() -> None:
    """A connector's context that names an identity or a path is the channel's content: the
    command's identity and path come from the link (control-plane.md §2)."""
    given = Setup(accepted(context={"identity": "idn_root", "org_path": ["default", "board"]}))
    await given.linked(org_path=("default", "product"))
    await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    command = await given.complete.execute(CompleteIntake(tenant="default", event_id="dlv_1"))
    assert command.identity == "idn_ada" and command.org_path == ("default", "product")


async def test_an_unknown_automation_is_kept_nowhere_and_not_answered() -> None:
    answer = accepted()
    automation = answer.model_copy(
        update={
            "accepted": answer.accepted.model_copy(  # type: ignore[union-attr]
                update={"sender": Sender(account="bot-7", kind=SenderKind.AUTOMATION)}
            )
        }
    )
    given = Setup(automation)
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and not outcome.replied
    assert given.replies.said == [], "an automation is never answered: answers would loop"
    async with given.persistence.transaction("default"):
        assert await given.events.list("default") == []


async def test_a_channel_that_cannot_be_answered_is_reported_not_retried() -> None:
    given = Setup()
    given.replies.delivers = False
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and not outcome.replied
    assert len(given.replies.said) == 1


async def test_several_events_within_the_window_get_one_offer_and_a_later_one_another() -> None:
    """Issue #247: events of one unknown person in one conversation that arrive together wait
    for each other, and one offer answers them all; after the window a new event may be
    offered again, under a key of its own, so that the connector does not take it for the
    first."""
    given = Setup()
    receive = ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    outcomes = await asyncio.gather(*(given.receive.execute(receive) for _ in range(4)))
    assert [o.replied for o in outcomes].count(True) == 1
    assert all(o.unknown_sender is not None for o in outcomes)
    ((_, _, _, first),) = given.replies.said

    given.clock.current += WINDOW - timedelta(minutes=5)
    assert not (await given.receive.execute(receive)).replied, "still within the window"
    given.clock.current += timedelta(minutes=10)
    later = await given.receive.execute(receive)
    assert later.replied, "after the window the person may be offered again"
    assert len(given.replies.said) == 2 and given.replies.said[1][3] != first

    # Another conversation, or another person, has a window of its own.
    given.connector.answer = accepted(
        context={"repository": "acme/product", "issue": "12"}, address="acme/product#12"
    )
    assert (await given.receive.execute(receive)).replied
    assert len(given.replies.said) == 3


async def test_an_event_without_the_senders_text_is_never_answered_nor_read_for_a_code() -> None:
    """A label added carries the issue's text, which somebody else wrote: the unknown person who
    added it is not answered, and a code in that text links nobody (issue #247)."""
    given = Setup()
    who, _ = await given.identity.person("default", "idn_ada")
    code = await given.identity.code(who)
    given.connector.answer = accepted(
        f"Pin the model\n\n{code}", authored=False, event="issue.labelled"
    )
    outcome = await given.receive.execute(
        ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
    )
    assert outcome.unknown_sender is not None and outcome.accepted is None
    assert not outcome.replied and outcome.linked is None
    assert given.replies.said == [], "nothing the sender wrote, nothing said to them"
    assert await given.identity.directory.links("default") == [], "the code linked nobody"
    async with given.persistence.transaction("default"):
        assert await given.events.list("default") == []

    # The same person, writing: answered as before.
    given.connector.answer = accepted()
    assert (
        await given.receive.execute(
            ReceiveIntake(channel="channel.repo", delivery=given.delivery, tenant="default")
        )
    ).replied
