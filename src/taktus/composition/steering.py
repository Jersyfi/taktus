"""Asking for status, pausing and cancelling, through any channel (ADR-0236, UC-1.5).

Three requests, read the same way from whatever channel a message arrives on — the chat, the
repository's comments, the web app, the command line — once the identity component placed its
sender:

- `status`, or "what are you working on?" — every run that has not ended and that the asker
  may see, each with its process, its current step, its state, since when and what it waits
  for. Drawn from the ledger's projection `run.current_work.v1`, never from the run store, so
  that the answer cannot differ from what the ledger says.
- `pause <run>` — the run halts at its next step boundary and resumes there when a person
  resumes it.
- `cancel <run>` — the run halts at its next step boundary and never resumes.

The answer is said at once in the channel the message came from: that the request was
received and when it takes effect. A second message, said by `SteeringConfirmed`, says when it
did. Only an identity with the right to steer a run may pause or cancel it: the identity the run
acts for, the owner, or a role holding `run.steer`. A refusal names the right that was missing.
Who may see a run is the reporting component's one predicate (UC-6.4).

This is wiring: it joins the run component, the identity component's rights and the reporting
component's predicate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import structlog

from taktus.components.identity.domain.model import Right, RoleRights
from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.model.trace import OWNER
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.application.service import AskSteering, SteeringAsked
from taktus.components.run.domain.model import (
    Run,
    RunError,
    RunSteering,
    SteeringKind,
    SteeringReply,
    SteeringState,
    UnknownRun,
)
from taktus.components.run.domain.service.current_work import (
    CurrentWorkProjection,
    Working,
    answer,
)
from taktus.composition.tenancy import this_round
from taktus.ports.connector import ChannelAnswers, ChannelReplies, Intake, IntakeReplyTo, Taken
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

log = structlog.get_logger("taktus.steering")

STATUS_WORDS: tuple[str, ...] = (
    "status",
    "what are you working on",
    "what are you doing",
    "woran arbeitest du",
    "was läuft",
)
PAUSE_WORDS: tuple[str, ...] = ("pause", "pausiere", "anhalten")
CANCEL_WORDS: tuple[str, ...] = ("cancel", "abbrechen", "storniere")
_AROUND = " \t\r\n.,;:!?\"'„“”«»()"
_MENTION = re.compile(r"^@[\w.-]+\s+")


class Engine(Protocol):
    """What the steering asks of the run engine."""

    async def ask_steering(self, command: AskSteering) -> SteeringAsked: ...


@dataclass(frozen=True)
class Asked:
    kind: str
    """`status`, `pause` or `cancel`."""
    run_id: str | None = None


def asked(text: str) -> Asked | None:
    """A message that asks for status, a pause or a cancellation; None for anything else. A
    leading mention of Taktus is ignored, so that a comment in a ticket reads like a chat."""
    cleaned = _MENTION.sub("", text.strip()).strip(_AROUND)
    folded = " ".join(cleaned.casefold().split())
    if folded in STATUS_WORDS:
        return Asked(kind="status")
    tokens = cleaned.split()
    if len(tokens) != 2:
        return None
    word, run_id = tokens[0].casefold(), tokens[1].strip(_AROUND)
    if word in PAUSE_WORDS:
        return Asked(kind="pause", run_id=run_id)
    if word in CANCEL_WORDS:
        return Asked(kind="cancel", run_id=run_id)
    return None


@dataclass(frozen=True)
class Answered:
    outcome: str
    """`shown`, `asked`, `took_effect`, `refused` or `unknown`."""
    text: str


class Steering:
    """Status, pause and cancellation for one reader: the rules every surface shares."""

    def __init__(
        self,
        *,
        engine: Engine,
        runs: Repository[Run],
        rights: Repository[RoleRights],
        ledger: Ledger,
        work: UnitOfWork,
        ceiling_seconds: float,
    ) -> None:
        self._engine = engine
        self._runs = runs
        self._rights = rights
        self._ledger = ledger
        self._work = work
        self._ceiling = ceiling_seconds

    async def current_work(self, reader: Reader) -> list[Working]:
        """Every run that has not ended and that the reader may see, from the ledger alone."""
        async with self._work.transaction(reader.tenant):
            state = await self._ledger.project(reader.tenant, CurrentWorkProjection())
        return [
            w
            for w in state.values()
            if visibility.may_see(
                reader,
                RunRef(
                    id=w.run_id,
                    tenant=reader.tenant,
                    process_version=w.process_version or "unknown@0",
                ),
            )
        ]

    async def missing_right(self, reader: Reader, run: Run) -> str | None:
        """The right the reader lacks to steer the run, or None when they hold it."""
        if run.identity == reader.identity or OWNER in reader.roles:
            return None
        async with self._work.transaction(reader.tenant):
            for role in reader.roles:
                held = await self._rights.get(reader.tenant, role)
                if held is not None and Right.STEER_RUN in held.rights:
                    return None
        return Right.STEER_RUN.value

    async def answer(self, reader: Reader, request: Asked, reply: SteeringReply | None) -> Answered:
        if request.kind == "status":
            return Answered("shown", answer(await self.current_work(reader)))
        run_id = request.run_id or ""
        kind = SteeringKind(request.kind)
        async with self._work.transaction(reader.tenant):
            run = await self._runs.get(reader.tenant, run_id)
        if run is None or not visibility.may_see(
            reader, RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        ):
            return Answered("unknown", f"There is no run {run_id} that you may see.")
        missing = await self.missing_right(reader, run)
        if missing is not None:
            return Answered(
                "refused",
                f"You may not {kind} run {run_id}: it does not act on your behalf, and none of "
                f"your roles holds the right {missing}.",
            )
        try:
            done = await self._engine.ask_steering(
                AskSteering(
                    run_id=run_id,
                    tenant=reader.tenant,
                    kind=kind,
                    actor=reader.identity,
                    reply=reply,
                )
            )
        except UnknownRun:
            return Answered("unknown", f"There is no run {run_id} that you may see.")
        except RunError as error:
            return Answered("refused", f"Run {run_id} cannot be {_past(kind)}: {error}.")
        if done.at_once:
            return Answered("took_effect", _took_effect(done.steering))
        return Answered(
            "asked",
            f"Received: run {run_id} will be {_past(kind)} at its next step boundary. The step "
            f"it is inside may finish first, within {self._ceiling:g} seconds at most. You will "
            "be told here when it has taken effect.",
        )


class SteeringInChannel:
    """`ChannelAnswers` for status, pause and cancellation, ahead of `then`."""

    def __init__(
        self, steering: Steering, replies: ChannelReplies, then: ChannelAnswers | None = None
    ) -> None:
        self._steering = steering
        self._replies = replies
        self._then = then

    async def take(
        self,
        tenant: str,
        intake: Intake,
        identity: str | None,
        roles: tuple[str, ...] = (),
    ) -> Taken | None:
        request = asked(intake.intent.raw) if identity is not None else None
        if request is None or identity is None:
            if self._then is None:
                return None
            return await self._then.take(tenant, intake, identity, roles)
        reader = Reader(tenant=tenant, identity=identity, roles=roles)
        to = intake.reply_to
        said = await self._steering.answer(
            reader,
            request,
            SteeringReply(channel=to.channel, address=to.address, thread=to.thread),
        )
        replied = await self._replies.reply(tenant, to, said.text, key=_key(intake.event_id))
        return Taken(outcome=said.outcome, replied=replied)


class SteeringConfirmed:
    """Says, in the channel a pause or a cancellation was asked in, that it took effect.

    On every tick of the elected scheduler, every request of every served tenant that took
    effect and has a channel to answer in is said there once and marked confirmed. A request
    whose message fails stays as it is and is tried again at the next tick; the idempotency key
    names the run and the moment it took effect, so the connector says it once."""

    def __init__(
        self,
        tenants: ServedTenants,
        steering: Repository[RunSteering],
        work: UnitOfWork,
        replies: ChannelReplies,
    ) -> None:
        self._tenants = tenants
        self._steering = steering
        self._work = work
        self._replies = replies

    async def tick(self) -> list[RunSteering]:
        confirmed: list[RunSteering] = []
        for tenant in await this_round(self._tenants, "scheduler"):
            try:
                confirmed.extend(await self.confirm(tenant))
            except Exception as error:  # a tick never takes the scheduler down
                log.error("steering could not be confirmed", tenant=tenant, error=str(error))
        return confirmed

    async def confirm(self, tenant: Tenant) -> list[RunSteering]:
        async with self._work.transaction(tenant):
            took = [
                s
                for s in await self._steering.list(tenant)
                if s.state is SteeringState.TOOK_EFFECT and s.reply is not None
            ]
        confirmed: list[RunSteering] = []
        for steering in took:
            reply = steering.reply
            if reply is None:  # filtered above
                continue
            at = "" if steering.took_effect_at is None else steering.took_effect_at.isoformat()
            said = await self._replies.reply(
                tenant,
                IntakeReplyTo(channel=reply.channel, address=reply.address, thread=reply.thread),
                _took_effect(steering),
                key=_key(f"{steering.id}:{steering.kind}:{at}"),
            )
            if not said:
                continue
            done = steering.model_copy(update={"state": SteeringState.CONFIRMED})
            async with self._work.transaction(tenant):
                await self._steering.put(tenant, done)
            confirmed.append(done)
        return confirmed


def _past(kind: SteeringKind) -> str:
    return "paused" if kind is SteeringKind.PAUSE else "cancelled"


def _took_effect(steering: RunSteering) -> str:
    at = steering.took_effect_at
    when = "" if at is None else f" at {at.isoformat(timespec='seconds')}"
    if steering.kind is SteeringKind.PAUSE:
        return (
            f"Run {steering.id} is paused{when}, at a step boundary. Nothing it did is lost; "
            "it continues from there when a person resumes it."
        )
    return f"Run {steering.id} is cancelled{when}, at a step boundary. It will not resume."


def _key(event: str) -> str:
    raw = f"taktus:steering:{event}"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)
    if len(cleaned) <= 128:
        return cleaned
    return "taktus:steering:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
