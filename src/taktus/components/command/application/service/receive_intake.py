"""Use case: a delivery on a channel becomes an intake event, or is refused.

**What is kept is announced.** With an outbox, keeping an event writes the entry
`intake.accepted` in the same transaction, which the automation role reacts to (ADR-0048 §3).
A delivery whose identifier the tenant already holds is a redelivery: nothing is written, and
the event kept first is answered (§4).

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

**Only what the sender wrote is answered, and an offer once per window.** An event that
carries no text its sender wrote — a label added carries the issue's — is neither answered nor
read for a code (`intent.authored`, ADR-0040 §5). Several events of one person in one
conversation within the offer window get one offer there: the offers of one conversation are
made one at a time, and one made within the window is not made again. A later event may get
another. The window's start is part of the offer's idempotency key, so that a redelivery, a
restart or a second instance within the same stretch of the window finds the offer already
made in the channel.

**A contribution is kept as data of its triage** (UC-1.9, ADR-0088). On a channel the instance
names a triage for (`TAKTUS_TRIAGE`), an issue or a pull request that an unknown sender opened
is kept as an intake event of status `contribution`, in the tenant the surface receives for,
without the sender's account and without their text, and the outbox entry
`intake.contribution` names it and the triage process in the same transaction. Nothing makes it
a command of the sender. The sender is answered as any unknown sender is.

**An answer is not a command.** A message written in the thread of something Taktus asked — a
report to the owner (ADR-0045) — is handed to whoever asked it (`ChannelAnswers`), from the
identity its sender was placed as, or from nobody for a sender the identity component could not
place. It is not kept as an intake event, and the outcome says what became of it. A sender
nobody could place who writes there is told that the answer is not filed, not how to link an
account. A message that asks the owner's conversation for a live representation goes the same
way (ADR-0069): it is answered there and is no command.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from taktus.components.command.domain.model import IntakeEvent, IntakeStatus
from taktus.components.command.domain.model.intake import UNKNOWN_ACCOUNT
from taktus.ports.clock import Clock
from taktus.ports.connector import (
    ChannelAnswers,
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
from taktus.ports.outbox import INTAKE_ACCEPTED, INTAKE_CONTRIBUTION, Outbox
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.telemetry import Telemetry
from taktus.shared.v1 import Capability

OFFER_WINDOW = timedelta(days=1)
"""How long one offer to link an account answers every event of its person in its
conversation, unless configured otherwise (`TAKTUS_OFFER_WINDOW_SECONDS`)."""

CONTRIBUTIONS = frozenset({"issue.opened", "pull_request.opened"})
"""The kinds of event that open a contribution (UC-1.9): an item opened, nothing else."""


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
    """Exactly one of four: accepted and kept, refused by the connector, accepted by the
    connector and not placed because the sender is unknown, or taken as an answer to what
    Taktus asked (`answer`, with `unknown_sender` too when nobody could place the sender). For
    an unknown sender and for an answer, `replied` says whether the answer to it reached the
    channel, and `linked` whether the message linked the account."""

    accepted: IntakeEvent | None = None
    refused: Refusal | None = None
    unknown_sender: Sender | None = None
    replied: bool = False
    linked: Resolution | None = None
    answer: str | None = None
    """For a message that answered something Taktus asked: what became of the answer. Nothing
    is kept as an intake event then."""
    contribution: IntakeEvent | None = None
    """For an unknown sender's contribution on a public channel: the event kept as data of
    its triage (ADR-0088), beside `unknown_sender`."""


class ReceiveIntakeHandler:
    def __init__(
        self,
        connectors: Mapping[Capability, IntakeConnector],
        events: Repository[IntakeEvent],
        work: UnitOfWork,
        identities: IdentityResolver,
        telemetry: Telemetry | None = None,
        replies: ChannelReplies | None = None,
        answers: ChannelAnswers | None = None,
        outbox: Outbox | None = None,
        *,
        clock: Clock | None = None,
        offer_window: timedelta = OFFER_WINDOW,
        triage: Mapping[Capability, str] | None = None,
    ) -> None:
        """`triage` maps a public channel to the process that triages its contributions
        (`TAKTUS_TRIAGE`, ADR-0088); a channel it does not name has none."""
        self._connectors = connectors
        self._events = events
        self._work = work
        self._identities = identities
        self._telemetry = telemetry
        self._replies = replies
        self._answers = answers
        self._outbox = outbox
        self._offers = Offers(clock, offer_window)
        self._triage = dict(triage or {})

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
        authored = accepted.intent.by_sender
        if self._answers is not None and accepted.sender.kind is SenderKind.PERSON and authored:
            taken = await self._answers.take(
                command.tenant if resolution is None else resolution.tenant,
                accepted,
                None if resolution is None else resolution.identity,
                () if resolution is None else resolution.roles,
            )
            if taken is not None:
                return IntakeOutcome(
                    unknown_sender=accepted.sender if resolution is None else None,
                    replied=taken.replied,
                    answer=taken.outcome,
                )
        if resolution is None:
            contribution = await self._contribution(command, accepted)
            outcome = await self._unknown(command, accepted)
            if contribution is None:
                return outcome
            return IntakeOutcome(
                unknown_sender=outcome.unknown_sender,
                replied=outcome.replied,
                linked=outcome.linked,
                contribution=contribution,
            )
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
            kept = await self._events.get(tenant, event.id)
            if kept is not None:
                # A redelivery changes nothing: an event already completed stays completed,
                # and nothing reacts to it twice (ADR-0048 §4).
                return IntakeOutcome(accepted=kept)
            await self._events.put(tenant, event)
            if self._outbox is not None:
                await self._outbox.write(tenant, INTAKE_ACCEPTED, {"event_id": event.id})
        return IntakeOutcome(accepted=event)

    async def _contribution(self, command: ReceiveIntake, accepted: Intake) -> IntakeEvent | None:
        """Keep an unknown sender's contribution on a public channel as data of its triage, or
        None when the event is none. A redelivery keeps nothing and writes nothing again."""
        process = self._triage.get(command.channel)
        if process is None or accepted.event not in CONTRIBUTIONS or self._outbox is None:
            return None
        tenant = command.tenant
        event = IntakeEvent(
            id=accepted.event_id,
            tenant=tenant,
            channel=accepted.channel,
            event=accepted.event,
            sender_account=UNKNOWN_ACCOUNT,
            sender_kind=accepted.sender.kind,
            intent="",
            context=dict(accepted.context),
            reply_channel=accepted.reply_to.channel,
            reply_address=accepted.reply_to.address,
            reply_thread=accepted.reply_to.thread,
            occurred_at=accepted.occurred_at,
            received_at=command.delivery.received_at,
            status=IntakeStatus.CONTRIBUTION,
        )
        async with self._work.transaction(tenant):
            kept = await self._events.get(tenant, event.id)
            if kept is not None:
                return kept
            await self._events.put(tenant, event)
            await self._outbox.write(
                tenant, INTAKE_CONTRIBUTION, {"event_id": event.id, "process": process}
            )
        return event

    async def _unknown(self, command: ReceiveIntake, accepted: Intake) -> IntakeOutcome:
        if not accepted.intent.by_sender:
            # A label added, an assignment: nothing the sender wrote, so nothing to answer and
            # no code to look for. A code in the issue's text is its author's, not theirs.
            return IntakeOutcome(unknown_sender=accepted.sender)
        answer = await self._identities.unknown_sender(
            command.channel, accepted.sender.account, accepted.intent.raw
        )
        replied = False
        # An automation is not answered: nobody reads the offer, and two automations answering
        # each other would loop. Its event is kept nowhere all the same.
        if self._replies is not None and accepted.sender.kind is SenderKind.PERSON:
            tenant = command.tenant if answer.linked is None else answer.linked.tenant
            if answer.linked is not None:
                # That a code linked the account is said for the message that carried it.
                replied = await self._replies.reply(
                    tenant, accepted.reply_to, answer.reply, key=reply_key(accepted.event_id)
                )
            else:
                replied = await self._offer(tenant, accepted, answer.reply)
        return IntakeOutcome(unknown_sender=accepted.sender, replied=replied, linked=answer.linked)

    async def _offer(self, tenant: Tenant, accepted: Intake, text: str) -> bool:
        """The offer to link the account, made at most once per window in a conversation."""
        if self._replies is None:  # unreachable: the caller checked
            return False
        to = accepted.reply_to
        conversation = offer_key(to.channel, to.address, accepted.sender.account)
        async with self._offers.turn(conversation) as turn:
            if turn.made:
                return False
            replied = await self._replies.reply(tenant, to, text, key=turn.key)
            if replied:
                turn.done()
        return replied


class Offers:
    """The offers this instance made, by conversation and person, for one window each.

    An offer is made under its conversation's lock: deliveries that arrive together — an issue
    opened and labelled three times in one second — wait for each other instead of each finding
    no offer yet and each making one. What one instance holds here, another does not; the key
    of the offer names the stretch of the window it falls in, so that the connector finds an
    offer another instance made in the same stretch. Without a clock there is no window: an
    offer is made once per conversation, as its key never changes."""

    def __init__(self, clock: Clock | None, window: timedelta) -> None:
        if window <= timedelta(0):
            raise ValueError("the offer window is longer than nothing")
        self._clock = clock
        self._window = window
        self._made: dict[str, datetime] = {}
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def turn(self, conversation: str) -> AsyncIterator[OfferTurn]:
        """One event's turn at the offer of its conversation; the next waits for it."""
        lock, users = self._locks.get(conversation, (asyncio.Lock(), 0))
        self._locks[conversation] = (lock, users + 1)
        try:
            async with lock:
                yield self._state(conversation)
        finally:
            lock, users = self._locks[conversation]
            if users == 1:
                del self._locks[conversation]
            else:
                self._locks[conversation] = (lock, users - 1)

    def _state(self, conversation: str) -> OfferTurn:
        if self._clock is None:
            return OfferTurn(self, conversation, made=False, key=conversation)
        now = self._clock.now()
        for earlier, at in list(self._made.items()):
            if now - at >= self._window:
                del self._made[earlier]
        stretch = int(now.timestamp() // self._window.total_seconds())
        return OfferTurn(
            self, conversation, made=conversation in self._made, key=f"{conversation}:{stretch}"
        )

    def _done(self, conversation: str) -> None:
        if self._clock is not None:
            self._made[conversation] = self._clock.now()


@dataclass
class OfferTurn:
    """What one event's turn finds: whether an offer was made within the window, and the
    idempotency key a new one is made under."""

    offers: Offers
    conversation: str
    made: bool
    key: str

    def done(self) -> None:
        """The offer reached the channel; the window starts now."""
        self.offers._done(self.conversation)


def offer_key(channel: str, address: str, account: str) -> str:
    """The idempotency key of the offer to one person in one conversation."""
    digest = hashlib.sha256(f"{channel}\n{address}\n{account}".encode()).hexdigest()[:32]
    return f"taktus:intake:offer:{digest}"


def reply_key(event_id: str) -> str:
    """The idempotency key of the answer to one delivery: a redelivery answers once."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", f"taktus:intake:{event_id}:reply")[:128]
