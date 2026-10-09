"""The owner-facing channel, joined across components and connectors (ADR-0045).

Four things meet here, and none of them knows another. The reporting component keeps the
reports, renders them and reads the answers. The decision component keeps a decision request
and its register; an answer to one is filed there. A connector carries a message into the
owner's channel and a task into a ticket system. The command component receives what the owner
writes. This module answers each from the other:

- `ConnectorDeliveries` says a report through the reply operation of the configured channel's
  connector (`contracts/connector/v1` §7), as Taktus itself (ADR-0033), and opens a task
  through the configured operation of a ticket system;
- `DecisionsOfTheChannel` files a decision answer through the decision component's own
  handlers, and hands a confirmed decision to the run, which continues from its boundary;
- `OwnerAnswers` is the intake's `ChannelAnswers`: a message written in the thread of a report
  goes to the reporting component and is no command;
- `KnownSecrets` holds the values the instance was configured with, so that no message carries
  one;
- `ShippedPhrasebooks` reads the phrasebooks Taktus ships (`phrasebooks/`), by language.

A decision request addressed to one of the roles the tenant's channel carries is raised as a
report the moment it is raised (`decision_raised`); a failure Taktus notices about itself is
reported through `failure`, the entry the run's noticing will call (issue #100).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import structlog

from taktus.components.decision.application.service import (
    AnswerRequest,
    AnswerRequestHandler,
    ConfirmRequest,
    ConfirmRequestHandler,
    DecisionError,
    NotAnswerable,
    UnknownRequest,
)
from taktus.components.decision.domain.model import Request
from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service import (
    AnswerInChannel,
    AnswerInChannelHandler,
    ChannelOf,
    CloseTaskHandler,
    ConfigureChannelHandler,
    RaiseReport,
    RaiseReportHandler,
    ReportingError,
)
from taktus.components.reporting.domain.model import OwnerChannel, Report, ReportKind
from taktus.components.reporting.ports import (
    DecisionAnswers,
    DecisionRead,
    DecisionRefused,
    Deliveries,
    NotDelivered,
    Phrasebooks,
    SecretValues,
    Sent,
)
from taktus.components.run.ports import ConnectorPool
from taktus.ports.clock import Clock
from taktus.ports.connector import (
    REPLY_OPERATION,
    CallContext,
    CallFailed,
    ChannelAnswers,
    ConnectorError,
    Intake,
    Result,
    Taken,
)
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Stored, Tenant, UnitOfWork
from taktus.ports.worker import CredentialReference

TAKTUS = "taktus"
"""The identity Taktus acts as on its own behalf (ADR-0033)."""

PHRASEBOOKS = Path(__file__).parent / "phrasebooks"

log = structlog.get_logger("taktusd")


class ShippedPhrasebooks(Phrasebooks):
    """The phrasebooks under `phrasebooks/`, one file per language tag."""

    def shipped(self, language: str) -> Mapping[str, Any] | None:
        path = PHRASEBOOKS / f"{language}.json"
        if path.parent != PHRASEBOOKS or not path.is_file():
            return None
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded


class RepositoryOf(Protocol):
    def __call__[T: Stored](self, kind: type[T]) -> Repository[T]: ...


class KnownSecrets(SecretValues):
    """The secret values this instance holds. Short values are not matched: a value of a few
    characters would match ordinary words, and none of Taktus's secrets is that short."""

    SHORTEST = 8

    def __init__(self, values: Iterable[str]) -> None:
        self._values = tuple(v for v in (x.strip() for x in values) if len(v) >= self.SHORTEST)

    def carried_by(self, text: str) -> bool:
        return any(value in text for value in self._values)


def known_secrets(environment: Mapping[str, str], also: Iterable[str] = ()) -> KnownSecrets:
    """Every value a `TAKTUS_…_FILE` variable points at — the one way a secret reaches the
    instance (CLAUDE.md §9) — and the values given beside them."""
    values = list(also)
    for name, path in environment.items():
        if name.startswith("TAKTUS_") and name.endswith("_FILE"):
            try:
                values.append(Path(path).read_text(encoding="utf-8"))
            except OSError:
                continue
    return KnownSecrets(values)


def _context(tenant: Tenant, key: str, credentials: Sequence[str]) -> CallContext:
    return CallContext(
        tenant=tenant,
        identity=TAKTUS,
        run_id="owner-channel",
        step_id="report",
        attempt=1,
        idempotency_key=key,
        credentials=tuple(CredentialReference(name=n, injected_as="env") for n in credentials),
    )


def _sent(result: Result) -> Sent:
    records = result.effect.records or ()
    first = records[0] if records else None
    thread = result.output.get("thread")
    return Sent(
        thread=thread if isinstance(thread, str) and thread else None,
        record=None if first is None else f"{first.kind}:{first.id}",
        url=None if first is None else first.url,
    )


class ConnectorDeliveries(Deliveries):
    def __init__(self, connectors: ConnectorPool) -> None:
        self._connectors = connectors

    async def say(
        self,
        tenant: Tenant,
        channel: str,
        address: str,
        text: str,
        *,
        thread: str | None = None,
        key: str,
    ) -> Sent | NotDelivered:
        document: dict[str, Any] = {"address": address, "text": text}
        if thread is not None:
            document["thread"] = thread
        return await self._call(
            tenant, channel, REPLY_OPERATION.format(channel=channel), document, key
        )

    async def open_task(
        self,
        tenant: Tenant,
        capability: str,
        operation: str,
        title: str,
        body: str,
        *,
        key: str,
    ) -> Sent | NotDelivered:
        return await self._call(tenant, capability, operation, {"title": title, "body": body}, key)

    async def _call(
        self, tenant: Tenant, capability: str, operation: str, document: dict[str, Any], key: str
    ) -> Sent | NotDelivered:
        resolved = await self._connectors.resolve(capability)
        if resolved is None or resolved.declaration.operation(operation) is None:
            log.warning("no connector offers the operation", operation=operation)
            return NotDelivered(reason="no_connector")
        credentials = [
            need.name for need in resolved.declaration.credentials if need.purpose == "actions"
        ]
        try:
            result = await resolved.connector.call(
                operation, _context(tenant, key, credentials), document
            )
        except CallFailed as error:
            log.error(
                "a report did not reach its channel",
                operation=operation,
                cause=str(error.error.cause),
            )
            return NotDelivered(reason="refused")
        except ConnectorError as error:
            log.error(
                "a report did not reach its channel",
                operation=operation,
                error=type(error).__name__,
            )
            return NotDelivered(reason="unreachable")
        return _sent(result)


type Decided = Callable[[Tenant, str, str], Awaitable[None]]
"""A decision took effect: the run it holds continues from its boundary, or halts there."""


class DecisionsOfTheChannel(DecisionAnswers):
    def __init__(
        self,
        answer: AnswerRequestHandler,
        confirm: ConfirmRequestHandler,
        decided: Decided | None = None,
    ) -> None:
        self._answer = answer
        self._confirm = confirm
        self.decided = decided

    async def answer(
        self, tenant: Tenant, request_id: str, identity: str, text: str
    ) -> DecisionRead:
        try:
            answered = await self._answer.execute(
                AnswerRequest(tenant=tenant, request_id=request_id, identity=identity, text=text)
            )
        except (NotAnswerable, UnknownRequest) as error:
            raise DecisionRefused(str(error), closed=True) from error
        except DecisionError as error:
            raise DecisionRefused(str(error)) from error
        reading = answered.request.request.answer_interpreted
        if reading is None:
            return DecisionRead()
        return DecisionRead(option=reading.option, kept=reading.modifications is not None)

    async def confirm(
        self, tenant: Tenant, request_id: str, identity: str, confirmed: bool
    ) -> str | None:
        try:
            done = await self._confirm.execute(
                ConfirmRequest(
                    tenant=tenant, request_id=request_id, identity=identity, confirmed=confirmed
                )
            )
        except (NotAnswerable, UnknownRequest) as error:
            raise DecisionRefused(str(error), closed=True) from error
        except DecisionError as error:
            raise DecisionRefused(str(error)) from error
        if done.entry is None:
            return None
        if self.decided is not None:
            await self.decided(tenant, done.entry.run_id, identity)
        return done.entry.id


class OwnerAnswers(ChannelAnswers):
    def __init__(self, answering: AnswerInChannelHandler) -> None:
        self._answering = answering

    async def take(self, tenant: str, intake: Intake, identity: str | None) -> Taken | None:
        answer = await self._answering.execute(
            AnswerInChannel(
                tenant=tenant,
                channel=intake.reply_to.channel,
                address=intake.reply_to.address,
                thread=intake.reply_to.thread,
                identity=identity,
                text=intake.intent.raw,
                event=intake.event_id,
            )
        )
        if answer is None:
            return None
        return Taken(outcome=answer.outcome, replied=answer.replied)


@dataclass(frozen=True)
class OwnerChannelWiring:
    """Everything an entry point needs of the owner-facing channel, built once."""

    configure: ConfigureChannelHandler
    channel: ChannelOf
    raising: RaiseReportHandler
    answering: AnswerInChannelHandler
    close_task: CloseTaskHandler
    queries: ReportQueries
    answers: OwnerAnswers
    """The intake's `ChannelAnswers`."""
    decisions: DecisionsOfTheChannel

    async def decision_raised(self, tenant: Tenant, request: Request) -> Report | None:
        """A decision request addressed to a role the tenant's channel carries reaches the
        owner as a report. One that cannot be raised as a report stays on the control plane's
        surface, where it was raised, and the log says why."""
        channel = await self.channel.of(tenant)
        if channel is None or request.decider not in channel.roles:
            return None
        shaped = request.request
        steps = []
        for option in shaped.options:
            step = f"{option.id}: {option.proposal}"
            if option.consequence:
                step += f" {option.consequence}"
            if option.recommended and option.reason:
                step += f" ({option.reason})"
            steps.append(step)
        try:
            return await self.raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=request.id,
                    kind=ReportKind.DECISION,
                    title=shaped.situation,
                    needed=(shaped.question,),
                    steps=steps,
                    standing_still=shaped.blocking,
                    due=shaped.due,
                    offered=[(o.id, o.proposal, o.recommended) for o in shaped.options],
                )
            )
        except ReportingError as error:
            log.error(
                "a decision request did not reach the owner", request=request.id, error=str(error)
            )
            return None

    async def failure(
        self,
        tenant: Tenant,
        id: str,
        title: str,
        *,
        needed: Sequence[str],
        steps: Sequence[str],
        standing_still: Sequence[str],
        due: date,
        links: Sequence[tuple[str, str]] = (),
    ) -> Report:
        """A failure Taktus noticed about itself, through the same channel (DEC-0058)."""
        return await self.raising.execute(
            RaiseReport(
                tenant=tenant,
                id=id,
                kind=ReportKind.FAILURE,
                title=title,
                needed=needed,
                steps=steps,
                standing_still=standing_still,
                due=due,
                links=links,
            )
        )


def owner_channel_wiring(
    of: RepositoryOf,
    work: UnitOfWork,
    ledger: Ledger,
    clock: Clock,
    connectors: ConnectorPool,
    answer: AnswerRequestHandler,
    confirm: ConfirmRequestHandler,
    secrets: SecretValues,
    *,
    deliveries: Deliveries | None = None,
    decided: Decided | None = None,
) -> OwnerChannelWiring:
    reports: Repository[Report] = of(Report)
    channels: Repository[OwnerChannel] = of(OwnerChannel)
    carrier = deliveries or ConnectorDeliveries(connectors)
    decisions = DecisionsOfTheChannel(answer, confirm, decided)
    answering = AnswerInChannelHandler(
        reports, channels, work, ledger, clock, carrier, decisions, secrets
    )
    return OwnerChannelWiring(
        configure=ConfigureChannelHandler(channels, work, ledger, clock, ShippedPhrasebooks()),
        channel=ChannelOf(channels, work),
        raising=RaiseReportHandler(reports, channels, work, ledger, clock, carrier, secrets),
        answering=answering,
        close_task=CloseTaskHandler(reports, work, ledger, clock),
        queries=ReportQueries(reports, channels, work),
        answers=OwnerAnswers(answering),
        decisions=decisions,
    )
