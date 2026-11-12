"""Status, pause and cancellation asked through any channel (ADR-0236, UC-1.5).

The channel handler in front of the engine of `test_pause_and_cancel.py`: a question about
current work is answered in the channel it was asked in, from the ledger; a pause or a
cancellation is acknowledged at once with when it takes effect, and a second message says when
it did; only an identity with the right to steer a run may, and a refusal names the right.
"""

from __future__ import annotations

from typing import Any

from components.run.test_pause_and_cancel import TENANT, Harness
from fakes.identity import FakeReplies, FixedTenants

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.identity.domain.model import Right, RoleRights
from taktus.components.run.domain.model import Cause, RunState, SteeringKind, SteeringState
from taktus.composition.steering import (
    Steering,
    SteeringConfirmed,
    SteeringInChannel,
    asked,
)
from taktus.ports.connector import Intake, IntakeIntent, IntakeReplyTo, Sender, SenderKind

CHAT = IntakeReplyTo(channel="channel.chat", address="C1", thread="1.1")
TICKETS = IntakeReplyTo(channel="channel.repository", address="org/repo#7", thread=None)


def intake(text: str, to: IntakeReplyTo, event: str) -> Intake:
    return Intake(
        event_id=event,
        event="message.posted",
        channel=to.channel,
        sender=Sender(account="U1", kind=SenderKind.PERSON),
        intent=IntakeIntent(raw=text),
        context={},
        reply_to=to,
        occurred_at=Harness().clock.now(),
    )


def wired(h: Harness) -> tuple[SteeringInChannel, FakeReplies, MemoryRepository[RoleRights]]:
    rights = MemoryRepository(h.persistence, RoleRights)
    steering = Steering(
        engine=h.engine,
        runs=h.runs,
        rights=rights,
        ledger=h.ledger,
        work=h.persistence,
        ceiling_seconds=900,
    )
    replies = FakeReplies()
    return SteeringInChannel(steering, replies), replies, rights


async def test_the_same_question_through_two_channels_is_answered_in_each_from_the_ledger() -> None:
    h = Harness()
    h.ask_during(1, SteeringKind.PAUSE)
    run = await h.start()
    channel, replies, _ = wired(h)
    for to, event in ((CHAT, "e1"), (TICKETS, "e2")):
        taken = await channel.take(
            TENANT, intake("@taktus what are you working on?", to, event), "idn_t"
        )
        assert taken is not None and taken.outcome == "shown" and taken.replied
    assert [said[1] for said in replies.said] == [CHAT, TICKETS], "each answered where it asked"
    first, second = replies.said[0][2], replies.said[1][2]
    assert first == second
    assert f"{run.id} of p@1: halted at step b" in first and "waits for paused" in first


async def test_a_pause_is_acknowledged_at_once_and_confirmed_when_it_took_effect() -> None:
    h = Harness()
    channel, replies, _ = wired(h)
    said: dict[str, Any] = {}

    async def on_assign(_: Any) -> None:
        if "taken" not in said:
            said["taken"] = await channel.take(
                TENANT, intake("pause run_0001", CHAT, "e3"), "idn_t"
            )

    h.worker.on_assign = on_assign
    run = await h.start()
    assert said["taken"].outcome == "asked"
    assert "at its next step boundary" in replies.said[0][2]
    assert run.state is RunState.HALTED and run.cause is Cause.PAUSED
    confirmer = SteeringConfirmed(FixedTenants((TENANT,)), h.steering, h.persistence, replies)
    confirmed = await confirmer.tick()
    assert [c.id for c in confirmed] == [run.id]
    assert confirmed[0].state is SteeringState.CONFIRMED
    assert replies.said[-1][1] == CHAT and "is paused" in replies.said[-1][2]
    assert await confirmer.tick() == [], "said once"


async def test_only_an_identity_with_the_right_may_steer_and_a_refusal_names_it() -> None:
    h = Harness()
    h.ask_during(0, SteeringKind.PAUSE)
    run = await h.start()
    channel, replies, rights = wired(h)
    taken = await channel.take(
        TENANT, intake(f"cancel {run.id}", CHAT, "e4"), "idn_other", ("staff",)
    )
    assert taken is not None and taken.outcome == "refused"
    assert "run.steer" in replies.said[-1][2]
    async with h.persistence.transaction(TENANT):
        await rights.put(TENANT, RoleRights(id="staff", tenant=TENANT, rights=(Right.STEER_RUN,)))
    taken = await channel.take(
        TENANT, intake(f"cancel {run.id}", CHAT, "e5"), "idn_other", ("staff",)
    )
    assert taken is not None and taken.outcome == "took_effect"
    async with h.persistence.transaction(TENANT):
        stored = await h.runs.get(TENANT, run.id)
    assert stored is not None and stored.cause is Cause.CANCELLED
    async with h.persistence.transaction(TENANT):
        entries = await h.ledger.entries(TENANT, run.id)
    assert entries[-1].refs.actor == "idn_other", "recorded with the identity that asked"


async def test_anything_else_goes_on_and_an_unknown_sender_is_not_answered_here() -> None:
    h = Harness()
    channel, replies, _ = wired(h)
    assert await channel.take(TENANT, intake("deploy the release", CHAT, "e6"), "idn_t") is None
    assert await channel.take(TENANT, intake("status", CHAT, "e7"), None) is None
    assert replies.said == []
    assert asked("Status") is not None and asked("pause") is None
    assert asked("pause run_1 now") is None
