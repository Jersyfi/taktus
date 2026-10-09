"""Use case: the owner answers in the channel, and the answer is filed where it belongs
(ADR-0008, ADR-0045, UC-6.11).

A message is an answer to a report when it is written in the thread of the report's message.
Every such message is answered in that thread, once, and is never acted on silently:

1. **Only the owner, or someone the owner named, is filed** (UC-1.7). Anyone else — an
   identity the tenant knows, or a sender nobody could place — is told that the answer is not
   filed, and nothing changes.
2. **An answer is read by a rule** and its reading sent back. A decision request's answer is
   read by the decision component, which keeps it; a need's, a date's or a failure's is read
   against the phrasebook's words for "done". An answer that cannot be read as one of the
   offered answers is asked back: nothing changes, and the offered answers are listed again.
3. **Only a confirmed reading is filed.** The same person confirms it with one of the
   phrasebook's words for yes; a word for no rejects it, and the report is open again. A
   decision is filed as the decision component's register entry; any other answer on the
   report itself. Anything else written while a reading waits is read as a new answer.

What the person wrote is never quoted back and never stored here: the report keeps the answer
it confirmed and where it was given — the channel, the address and the thread.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.reporting.application.service._ledger import (
    ANSWERED,
    FILED,
    key,
    record,
)
from taktus.components.reporting.application.service.raise_report import DONE
from taktus.components.reporting.domain.model import (
    Filed,
    Happened,
    OwnerChannel,
    Reading,
    Report,
    ReportKind,
    ReportState,
)
from taktus.components.reporting.domain.service import reading as rules
from taktus.components.reporting.domain.service.rendering import (
    asked_back,
    filed,
    reflected,
)
from taktus.components.reporting.ports import (
    DecisionAnswers,
    DecisionRefused,
    Deliveries,
    SecretValues,
    Sent,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Capability


@dataclass(frozen=True)
class AnswerInChannel:
    tenant: Tenant
    channel: Capability
    address: str
    thread: str | None
    identity: str | None
    """Who wrote it, as the identity component placed them; None for a sender it could not."""
    text: str
    event: str
    """The channel's identifier of the message: the reply to it is said once."""


@dataclass(frozen=True)
class Answer:
    report: Report
    outcome: str
    """`not_filed`, `closed`, `asked_back`, `reflected`, `reread` or `filed`."""
    replied: bool


class AnswerInChannelHandler:
    def __init__(
        self,
        reports: Repository[Report],
        channels: Repository[OwnerChannel],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        deliveries: Deliveries,
        decisions: DecisionAnswers,
        secrets: SecretValues,
    ) -> None:
        self._reports = reports
        self._channels = channels
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._deliveries = deliveries
        self._decisions = decisions
        self._secrets = secrets

    async def execute(self, command: AnswerInChannel) -> Answer | None:
        """The answer, or None when the message answers no report: it is not this
        component's, and goes on as any other message would."""
        async with self._work.transaction(command.tenant):
            channel = await self._channels.get(command.tenant, command.tenant)
            reports = await self._reports.list(command.tenant)
        if channel is None or command.channel != channel.channel:
            return None
        report = next((r for r in reports if r.answers_in(command.address, command.thread)), None)
        if report is None:
            return None
        book = channel.phrasebook
        now = self._clock.now()
        who = command.identity
        where = f"{command.channel} {command.address} {command.thread}"
        if who is None or not channel.may_answer(who):
            return await self._close(command, report, "not_filed", book.not_filed, who)
        if report.state is ReportState.FILED:
            return await self._close(command, report, "closed", book.closed, who)
        reading = report.reading
        if report.state is ReportState.REFLECTED and reading is not None and reading.by == who:
            confirmed = rules.confirmation(command.text, book)
            if confirmed is not None:
                return await self._confirm(command, report, channel, reading, confirmed, where)
        if report.kind is ReportKind.DECISION:
            try:
                read = await self._decisions.answer(command.tenant, report.id, who, command.text)
            except DecisionRefused as error:
                said = book.closed if error.closed else book.not_filed
                return await self._close(
                    command, report, "closed" if error.closed else "not_filed", said, who
                )
            option, kept = read.option, read.kept
        else:
            option, kept = (DONE, False) if rules.done(command.text, book) else (None, False)
        if option is None:
            updated = report.model_copy(
                update={
                    "state": ReportState.OPEN,
                    "reading": None,
                    "history": (*report.history, Happened(at=now, event="asked_back", by=who)),
                }
            )
            return await self._settle(command, updated, "asked_back", asked_back(report, book))
        new = Reading(answer=option, by=who, at=now, kept=kept)
        updated = report.model_copy(
            update={
                "state": ReportState.REFLECTED,
                "reading": new,
                "history": (*report.history, Happened(at=now, event="reflected", by=who)),
            }
        )
        return await self._settle(command, updated, "reflected", reflected(report, new, book))

    async def _confirm(
        self,
        command: AnswerInChannel,
        report: Report,
        channel: OwnerChannel,
        reading: Reading,
        confirmed: bool,
        where: str,
    ) -> Answer:
        book = channel.phrasebook
        now = self._clock.now()
        entry: str | None = None
        if report.kind is ReportKind.DECISION:
            try:
                entry = await self._decisions.confirm(
                    command.tenant, report.id, reading.by, confirmed
                )
            except DecisionRefused as error:
                said = book.closed if error.closed else book.not_filed
                outcome = "closed" if error.closed else "not_filed"
                return await self._close(command, report, outcome, said, reading.by)
        if not confirmed:
            reopened = report.model_copy(
                update={
                    "state": ReportState.OPEN,
                    "reading": None,
                    "history": (
                        *report.history,
                        Happened(at=now, event="reread", by=reading.by),
                    ),
                }
            )
            return await self._settle(command, reopened, "reread", book.reread)
        answer = Filed(answer=reading.answer, by=reading.by, at=now, record=entry, where=where)
        done = report.model_copy(
            update={
                "state": ReportState.FILED,
                "reading": None,
                "filed": answer,
                "history": (*report.history, Happened(at=now, event="filed", by=reading.by)),
            }
        )
        return await self._settle(command, done, "filed", filed(reading.answer, book))

    async def _close(
        self, command: AnswerInChannel, report: Report, outcome: str, said: str, who: str | None
    ) -> Answer:
        """An answer that changes nothing: it is acknowledged, and the history says so."""
        event = "answer_not_filed" if outcome == "not_filed" else "answer_after_filing"
        noted = report.model_copy(
            update={
                "history": (
                    *report.history,
                    Happened(at=self._clock.now(), event=event, by=who),
                )
            }
        )
        return await self._settle(command, noted, outcome, said)

    async def _settle(
        self, command: AnswerInChannel, report: Report, outcome: str, said: str
    ) -> Answer:
        replied = False
        if not self._secrets.carried_by(said):
            sent = await self._deliveries.say(
                command.tenant,
                command.channel,
                command.address,
                said,
                thread=command.thread,
                key=key(report.id, command.event, "reply"),
            )
            replied = isinstance(sent, Sent)
        async with self._work.transaction(command.tenant):
            await self._reports.put(command.tenant, report)
            kind = FILED if outcome == "filed" else ANSWERED
            await record(self._ledger, report, kind, outcome, actor=command.identity)
        return Answer(report=report, outcome=outcome, replied=replied)
