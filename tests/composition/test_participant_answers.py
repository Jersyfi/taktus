"""An outside participant's answer arrives through the mail channel's intake (UC-1.12,
ADR-0155).

The supplier has no Taktus account. Their reply to the question is normalised by the mail
connector's own intake, matched by its thread before the identity component is asked who they
are, said back in the thread, and recorded once they confirm. A message of the same unknown
sender in another thread goes on as any unknown sender's does (ADR-0040).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from components.run.test_participants import CHANNEL, QUESTION_ID, Asked, after, answer, ask
from fakes import FakeClock
from fakes.identity import directory

from taktus.adapters.driven.connectors.mail import intake as mail_intake
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.command.application.service import (
    IntakeOutcome,
    ReceiveIntake,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.participants import ParticipantAnswers
from taktus.ports.connector import Delivery, IntakeReplyTo, IntakeResult

TENANT = "t"
SECRET = "intake-" + "x" * 16
RECEIVED = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
SUPPLIER = "orders@supplier.example.org"


@dataclass
class MailIntake:
    """The mail connector's intake, called in this process."""

    async def intake(self, delivery: Delivery) -> IntakeResult:
        return IntakeResult.model_validate(
            mail_intake.normalise(
                delivery.headers, delivery.body, delivery.received_at.isoformat(), SECRET
            )
        )


@dataclass
class Replies:
    said: list[tuple[IntakeReplyTo, str, str]] = field(default_factory=list)

    async def reply(self, tenant: str, to: IntakeReplyTo, text: str, *, key: str) -> bool:
        self.said.append((to, text, key))
        return True


def delivered(mid: str, text: str, *, thread: str | None = QUESTION_ID) -> Delivery:
    lines = [
        f"From: Orders <{SUPPLIER}>",
        "To: purchasing@example.org",
        "Subject: Re: Delivery date",
        "Date: Tue, 03 Nov 2026 08:55:00 +0000",
        f"Message-ID: {mid}",
        *([f"In-Reply-To: {thread}", f"References: {thread}"] if thread else []),
        "Content-Type: text/plain; charset=utf-8",
        "",
        text,
        "",
    ]
    raw = "\r\n".join(lines).encode()
    body = json.dumps({"message": base64.b64encode(raw).decode(), "mailbox": "INBOX"})
    return Delivery(headers=mail_intake.signed(body, SECRET), body=body, received_at=RECEIVED)


class Wired:
    def __init__(self) -> None:
        self.asked = Asked(ask(), answer(), after())
        self.given = directory((TENANT,), clock=FakeClock(RECEIVED))
        self.events = MemoryRepository(self.given.persistence, IntakeEvent)
        self.replies = Replies()
        self.receive = ReceiveIntakeHandler(
            {CHANNEL: MailIntake()},
            self.events,
            self.given.persistence,
            self.given.directory,
            replies=self.replies,
            answers=ParticipantAnswers(
                self.asked.runs,
                self.asked.persistence,
                self.asked.engine,
                self.replies,
                enqueue=False,
            ),
        )

    async def deliver(self, delivery: Delivery) -> IntakeOutcome:
        return await self.receive.execute(
            ReceiveIntake(channel=CHANNEL, delivery=delivery, tenant=TENANT)
        )


async def test_an_unknown_supplier_answers_in_the_thread_and_confirms_there() -> None:
    w = Wired()
    run = await w.asked.begin()
    assert run.state is RunState.WAITING_HUMAN

    read = await w.deliver(delivered("<r-1@supplier.example.org>", "Friday, 14 November."))
    assert read.answer == "participant_read" and read.replied
    ((to, said, _),) = w.replies.said
    assert to.address == SUPPLIER and to.thread == "<r-1@supplier.example.org>"
    assert "“Friday, 14 November.”" in said and "Reply yes to confirm" in said

    done = await w.deliver(delivered("<r-2@supplier.example.org>", "Yes"))
    assert done.answer == "participant_recorded"
    run = await w.asked.stored(run.id)
    assert run is not None and run.state is RunState.FINISHED, run and run.reason
    assert run.step_run("answer").state is StepState.SUCCEEDED
    result = await w.asked.result(run, "answer")
    assert result["answer"] == "Friday, 14 November."
    assert result["answered_by"] == {
        "channel": CHANNEL,
        "account": mail_intake.account_of(SUPPLIER),
    }
    async with w.given.persistence.transaction(TENANT):
        assert await w.events.list(TENANT) == [], "an answer is not a command"


async def test_the_same_sender_in_another_thread_is_an_unknown_sender() -> None:
    w = Wired()
    await w.asked.begin()
    other = await w.deliver(
        delivered("<r-3@supplier.example.org>", "A new offer for you.", thread=None)
    )
    assert other.answer is None
    assert other.unknown_sender is not None
