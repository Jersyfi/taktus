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
4. **An intervention is a command** (ADR-0109 §6). The daily report of signals offers the
   processes a person may start from it. A reply whose whole message is one of their labels is
   read as that start, sent back, and only its confirmation starts the process, on behalf of
   the person who confirmed it. The report is filed with the run as its record. A start that is
   refused leaves the report open.

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
from taktus.components.reporting.domain.service import corridors
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
from taktus.components.reporting.ports.signals import InterventionRefused, Interventions
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
class AnswerOnPage:
    """An answer given on the report's page in the web app (ADR-0120): an offered answer
    chosen by its identifier, the reader's own words, or the confirmation of a reading."""

    tenant: Tenant
    report_id: str
    identity: str
    """Who answered, as their account key proved it."""
    option: str | None = None
    """The identifier of an offered answer the reader chose."""
    text: str | None = None
    """The reader's own words, read by the same rule as in the channel."""
    confirmed: bool | None = None
    """True or False: the reader confirms or rejects the reading sent back to them."""


ON_PAGE = "web"
"""Where an answer given on the report's page was given (`Filed.where`)."""


@dataclass(frozen=True)
class _Place:
    """Where an answer was given, and where the sentence said back goes: a thread of the
    channel, or the report's page, which says nothing in the channel."""

    tenant: Tenant
    identity: str | None
    where: str
    channel: Capability | None = None
    address: str | None = None
    thread: str | None = None
    event: str | None = None


@dataclass(frozen=True)
class Answer:
    report: Report
    outcome: str
    """`not_filed`, `closed`, `asked_back`, `reflected`, `reread`, `refused`, `filed`, or, on
    the page only, `nothing_to_confirm`."""
    replied: bool
    said: str = ""
    """The sentence said back: in the thread, or on the report's page."""


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
        interventions: Interventions | None = None,
    ) -> None:
        self._interventions = interventions
        self._reports = reports
        self._channels = channels
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._deliveries = deliveries
        self._decisions = decisions
        self._secrets = secrets

    def intervene_with(self, interventions: Interventions) -> None:
        """What starts a confirmed intervention: bound once the run engine exists."""
        self._interventions = interventions

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
        place = _Place(
            tenant=command.tenant,
            identity=command.identity,
            where=f"{command.channel} {command.address} {command.thread}",
            channel=command.channel,
            address=command.address,
            thread=command.thread,
            event=command.event,
        )
        confirmed: bool | None = None
        reading = report.reading
        if (
            report.state is ReportState.REFLECTED
            and reading is not None
            and reading.by == command.identity
        ):
            confirmed = rules.confirmation(command.text, channel.phrasebook)
        return await self._answer(place, report, channel, command.text, None, confirmed)

    async def on_page(self, command: AnswerOnPage) -> Answer | None:
        """The answer given on the report's page; None when the tenant has no such report.
        A confirmation with no reading of this person's waiting changes nothing."""
        async with self._work.transaction(command.tenant):
            channel = await self._channels.get(command.tenant, command.tenant)
            report = await self._reports.get(command.tenant, command.report_id)
        if channel is None or report is None:
            return None
        place = _Place(tenant=command.tenant, identity=command.identity, where=ON_PAGE)
        if command.confirmed is not None and channel.may_answer(command.identity):
            reading = report.reading
            if (
                report.state is not ReportState.REFLECTED
                or reading is None
                or reading.by != command.identity
            ):
                return Answer(report=report, outcome="nothing_to_confirm", replied=False)
        chosen = command.option
        if chosen is not None and all(o.id != chosen for o in report.offered):
            chosen = None
        return await self._answer(
            place, report, channel, command.text or "", chosen, command.confirmed
        )

    async def _answer(
        self,
        place: _Place,
        report: Report,
        channel: OwnerChannel,
        text: str,
        chosen: str | None,
        confirmed: bool | None,
    ) -> Answer:
        """One answer, wherever it was given: `chosen` is an offered answer picked by its
        identifier, `confirmed` the confirmation of the reading that waits for this person."""
        book = channel.phrasebook
        now = self._clock.now()
        who = place.identity
        if who is None or not channel.may_answer(who):
            return await self._close(place, report, "not_filed", book.not_filed)
        if report.state is ReportState.FILED:
            return await self._close(place, report, "closed", book.closed)
        reading = report.reading
        if confirmed is not None and reading is not None:
            return await self._confirm(place, report, channel, reading, confirmed)
        if report.kind is ReportKind.DECISION:
            try:
                read = await self._decisions.answer(place.tenant, report.id, who, chosen or text)
            except DecisionRefused as error:
                said = book.closed if error.closed else book.not_filed
                return await self._close(
                    place, report, "closed" if error.closed else "not_filed", said
                )
            option, kept = read.option, read.kept
        elif chosen is not None:
            option, kept = chosen, False
        elif report.kind is ReportKind.SIGNALS:
            starts = [o for o in report.offered if o.id != DONE]
            option, kept = rules.offer(text, starts), False
            if option is None and rules.done(text, book):
                option = DONE
        else:
            option, kept = (DONE, False) if rules.done(text, book) else (None, False)
        if option is None:
            updated = report.model_copy(
                update={
                    "state": ReportState.OPEN,
                    "reading": None,
                    "history": (*report.history, Happened(at=now, event="asked_back", by=who)),
                }
            )
            return await self._settle(place, updated, "asked_back", asked_back(report, book))
        new = Reading(answer=option, by=who, at=now, kept=kept)
        updated = report.model_copy(
            update={
                "state": ReportState.REFLECTED,
                "reading": new,
                "history": (*report.history, Happened(at=now, event="reflected", by=who)),
            }
        )
        return await self._settle(place, updated, "reflected", reflected(report, new, book))

    async def _confirm(
        self,
        place: _Place,
        report: Report,
        channel: OwnerChannel,
        reading: Reading,
        confirmed: bool,
    ) -> Answer:
        book = channel.phrasebook
        now = self._clock.now()
        entry: str | None = None
        if report.kind is ReportKind.DECISION:
            try:
                entry = await self._decisions.confirm(
                    place.tenant, report.id, reading.by, confirmed
                )
            except DecisionRefused as error:
                said = book.closed if error.closed else book.not_filed
                outcome = "closed" if error.closed else "not_filed"
                return await self._close(place, report, outcome, said)
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
            return await self._settle(place, reopened, "reread", book.reread)
        said = filed(reading.answer, book)
        process = (
            corridors.intervened(reading.answer) if report.kind is ReportKind.SIGNALS else None
        )
        if process is not None:
            try:
                if self._interventions is None:
                    raise InterventionRefused("no intervention can be started here")
                entry = await self._interventions.start(
                    place.tenant,
                    process,
                    by=reading.by,
                    report=report.id,
                    channel=place.channel or channel.channel,
                    address=place.address or channel.address,
                )
            except InterventionRefused:
                refused = report.model_copy(
                    update={
                        "state": ReportState.OPEN,
                        "reading": None,
                        "history": (
                            *report.history,
                            Happened(at=now, event="intervention_refused", by=reading.by),
                        ),
                    }
                )
                return await self._settle(
                    place, refused, "refused", book.act_refused or book.not_filed
                )
            if book.intervened is not None:
                said = book.intervened.format(process=process, run=entry)
        answer = Filed(
            answer=reading.answer, by=reading.by, at=now, record=entry, where=place.where
        )
        done = report.model_copy(
            update={
                "state": ReportState.FILED,
                "reading": None,
                "filed": answer,
                "history": (*report.history, Happened(at=now, event="filed", by=reading.by)),
            }
        )
        return await self._settle(place, done, "filed", said)

    async def _close(self, place: _Place, report: Report, outcome: str, said: str) -> Answer:
        """An answer that changes nothing: it is acknowledged, and the history says so."""
        event = "answer_not_filed" if outcome == "not_filed" else "answer_after_filing"
        noted = report.model_copy(
            update={
                "history": (
                    *report.history,
                    Happened(at=self._clock.now(), event=event, by=place.identity),
                )
            }
        )
        return await self._settle(place, noted, outcome, said)

    async def _settle(self, place: _Place, report: Report, outcome: str, said: str) -> Answer:
        """The report kept, and the sentence said back in the thread where the answer was given.
        On the page nothing is said in the channel: the page shows the sentence."""
        replied = False
        if self._secrets.carried_by(said):
            said = ""
        if said and place.channel is not None and place.address is not None and place.event:
            sent = await self._deliveries.say(
                place.tenant,
                place.channel,
                place.address,
                said,
                thread=place.thread,
                key=key(report.id, place.event, "reply"),
            )
            replied = isinstance(sent, Sent)
        async with self._work.transaction(place.tenant):
            await self._reports.put(place.tenant, report)
            kind = FILED if outcome == "filed" else ANSWERED
            await record(self._ledger, report, kind, outcome, actor=place.identity)
        return Answer(report=report, outcome=outcome, replied=replied, said=said)
