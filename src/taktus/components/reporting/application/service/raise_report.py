"""Use case: something is needed from the owner, and it reaches them (ADR-0045, UC-6.11).

A report is raised for a decision request addressed to the owner, a need, a date or a failure
Taktus noticed about itself. **A report without one of its four items is not sent**: what is
needed, the steps to provide it, the work that stands still for want of it, and the date
(ADR-0028). Nor is one whose renderings would carry a secret value. Either is refused with
`NotSent`, and nothing is stored or sent.

A raised report is stored first — it is the record — and `report.raised` points to it. Then it
is delivered: as a task in the ticket system where one is configured, then as a message in the
owner's channel, which links the task. **A delivery that fails leaves the report where it is**:
stored, in the view, its failed delivery in its history and in its repository text, and
`report.delivered` says so. `DeliverReport` tries again; a delivery that went out is never
repeated, and the idempotency key makes a repeat after a restart land once.

Raising is idempotent by the report's identifier: the same event raised twice is one report.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from taktus.components.reporting.application.service._ledger import (
    DELIVERED,
    RAISED,
    key,
    record,
)
from taktus.components.reporting.application.service.errors import (
    NoChannel,
    NotSent,
    UnknownReport,
)
from taktus.components.reporting.domain.model import (
    Delivery,
    DeliveryChannel,
    DeliveryState,
    Happened,
    Link,
    Offered,
    OwnerChannel,
    Report,
    ReportKind,
)
from taktus.components.reporting.domain.service.rendering import message, repository_text
from taktus.components.reporting.ports import Deliveries, NotDelivered, SecretValues, Sent
from taktus.ports.clock import Clock
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

DONE = "done"
"""The identifier of the one answer a need, a date or a failure offers."""


@dataclass(frozen=True)
class RaiseReport:
    tenant: Tenant
    id: str
    """The event's own identifier: the decision request's, the need's, the date's, the
    failure's."""
    kind: ReportKind
    title: str
    needed: Sequence[str]
    steps: Sequence[str]
    standing_still: Sequence[str]
    due: date | None
    offered: Sequence[tuple[str, str, bool]] = ()
    """A decision request's options, as identifier, proposal and whether it is recommended.
    Empty for every other kind, which offers the one answer that it is done."""
    links: Sequence[tuple[str, str]] = ()
    """Every file, issue and pull request the report concerns, as label and address."""


@dataclass(frozen=True)
class DeliverReport:
    tenant: Tenant
    id: str


def _items(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(v.strip() for v in values if v.strip())


class RaiseReportHandler:
    def __init__(
        self,
        reports: Repository[Report],
        channels: Repository[OwnerChannel],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        deliveries: Deliveries,
        secrets: SecretValues,
    ) -> None:
        self._reports = reports
        self._channels = channels
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._deliveries = deliveries
        self._secrets = secrets

    async def execute(self, command: RaiseReport) -> Report:
        needed = _items(command.needed)
        steps = _items(command.steps)
        standing_still = _items(command.standing_still)
        missing = [
            name
            for name, present in (
                ("what is needed", bool(needed)),
                ("the steps to provide it", bool(steps)),
                ("the work that stands still", bool(standing_still)),
                ("the date it is needed by", command.due is not None),
            )
            if not present
        ]
        if missing or command.due is None:
            raise NotSent(f"report {command.id} is not sent: it names no {', no '.join(missing)}")
        async with self._work.transaction(command.tenant):
            channel = await self._channels.get(command.tenant, command.tenant)
            existing = await self._reports.get(command.tenant, command.id)
        if channel is None:
            raise NoChannel(command.tenant)
        if existing is not None:
            return existing
        if command.kind is ReportKind.DECISION:
            offered = tuple(
                Offered(id=i, label=label, recommended=recommended)
                for i, label, recommended in command.offered
            )
        else:
            offered = (Offered(id=DONE, label=channel.phrasebook.done),)
        now = self._clock.now()
        report = Report(
            id=command.id,
            tenant=command.tenant,
            kind=command.kind,
            title=command.title.strip(),
            needed=needed,
            steps=steps,
            standing_still=standing_still,
            due=command.due,
            offered=offered,
            links=tuple(Link(label=label, url=url) for label, url in command.links),
            raised_at=now,
            history=(Happened(at=now, event="raised"),),
        )
        text = repository_text(report)
        if self._secrets.carried_by(text) or self._secrets.carried_by(message(report, channel)):
            raise NotSent(f"report {command.id} is not sent: it would carry a secret value")
        async with self._work.transaction(command.tenant):
            await self._reports.put(command.tenant, report)
            await record(self._ledger, report, RAISED, str(report.kind), text=text)
        return await self._deliver(report, channel)

    async def deliver(self, command: DeliverReport) -> Report:
        """Try again what was not delivered."""
        async with self._work.transaction(command.tenant):
            channel = await self._channels.get(command.tenant, command.tenant)
            report = await self._reports.get(command.tenant, command.id)
        if report is None:
            raise UnknownReport(command.tenant, command.id)
        if channel is None:
            raise NoChannel(command.tenant)
        return await self._deliver(report, channel)

    async def _deliver(self, report: Report, channel: OwnerChannel) -> Report:
        attempts = len(report.deliveries)
        made: list[Delivery] = []
        if channel.task is not None and report.task() is None:
            body = repository_text(report)
            title = f"{report.id}: {report.title}"
            if self._secrets.carried_by(title + "\n" + body):
                made.append(self._withheld(DeliveryChannel.TASK))
            else:
                outcome = await self._deliveries.open_task(
                    report.tenant,
                    channel.task.capability,
                    channel.task.operation,
                    title,
                    body,
                    key=key(report.id, "task"),
                )
                made.append(self._delivery(DeliveryChannel.TASK, outcome, None))
            report = report.model_copy(update={"deliveries": (*report.deliveries, made[-1])})
        if report.message() is None:
            text = message(report, channel)
            if self._secrets.carried_by(text):
                made.append(self._withheld(DeliveryChannel.MESSAGE))
            else:
                outcome = await self._deliveries.say(
                    report.tenant,
                    channel.channel,
                    channel.address,
                    text,
                    key=key(report.id, "message"),
                )
                made.append(self._delivery(DeliveryChannel.MESSAGE, outcome, channel.address))
        if not made:
            return report
        history = tuple(Happened(at=d.at, event=f"{d.channel}_{d.state}") for d in made)
        delivered = report.model_copy(
            update={
                "deliveries": (*report.deliveries[:attempts], *made),
                "history": (*report.history, *history),
            }
        )
        async with self._work.transaction(report.tenant):
            await self._reports.put(report.tenant, delivered)
            for d in made:
                await record(self._ledger, delivered, DELIVERED, f"{d.channel}_{d.state}")
        return delivered

    def _withheld(self, channel: DeliveryChannel) -> Delivery:
        return Delivery(
            channel=channel,
            state=DeliveryState.WITHHELD,
            at=self._clock.now(),
            reason="secret_value",
        )

    def _delivery(
        self, channel: DeliveryChannel, outcome: Sent | NotDelivered, address: str | None
    ) -> Delivery:
        now = self._clock.now()
        if isinstance(outcome, Sent):
            return Delivery(
                channel=channel,
                state=DeliveryState.DELIVERED,
                at=now,
                address=address,
                thread=outcome.thread,
                record=outcome.record,
                url=outcome.url,
            )
        return Delivery(
            channel=channel,
            state=DeliveryState.FAILED,
            at=now,
            reason=outcome.reason,
            address=address,
        )
