"""Use case: Taktus notices a broken interface from its real calls, and reports it to the owner
(ADR-0047, issue #100, DEC-0058).

`noticed` is the view: the rule over the run's failed calls, every broken interface with what
became of its report. It is computed from the ledger each time it is read, so there is nothing
to keep in step with it. A broken interface is recorded whether or not anyone hears of it: its
failed calls are in the ledger, and `taktusctl interfaces` shows it.

`report` raises the report of every open broken interface that has none yet, as a report of kind
`failure` through the owner-facing channel (ADR-0045), with the run, the step, and the first and
the last failed call. Raising is idempotent by the report's identifier, which the broken
interface derives from its first call: it is raised once, however many calls fail after it. A
tenant without an owner-facing channel raises nothing, and the view says that the report was
not delivered and why. A report whose message was not delivered is tried again once an hour.

A broken interface is closed when the owner answered its report that it is done. A call that
fails after that opens a new one, with a report of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service.configure_channel import ChannelOf
from taktus.components.reporting.application.service.errors import ReportingError
from taktus.components.reporting.application.service.raise_report import (
    DeliverReport,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import (
    BrokenInterface,
    DeliveryChannel,
    Report,
    ReportKind,
)
from taktus.components.reporting.domain.model.interface import ID_PREFIX
from taktus.components.reporting.domain.service import interfaces as rule
from taktus.components.reporting.ports import Failures
from taktus.ports.clock import Clock
from taktus.ports.persistence import Tenant

RETRY = timedelta(hours=1)
"""How long a message that was not delivered waits before it is tried again: often enough that
the owner hears of it the hour the channel works again, rarely enough that a channel that stays
down does not fill the ledger with attempts."""

NO_CHANNEL = "no_channel"
NOT_RAISED = "not_raised"


@dataclass(frozen=True)
class Noticed:
    """A broken interface, and what became of its report."""

    found: BrokenInterface
    report: Report | None
    closed: bool
    """The owner answered its report that it is done."""
    delivered: bool
    """Its message reached the owner's channel."""
    reason: str | None
    """Why it was not delivered, as a token: `no_channel`, `not_raised`, or the reason of the
    last delivery that failed. None when it was."""

    @property
    def state(self) -> str:
        """What became of the report, in one line for the operator."""
        if self.closed:
            return "closed: the owner answered that it is done"
        if self.delivered and self.report is not None:
            message = self.report.message()
            at = "" if message is None else f" at {message.at.isoformat(timespec='seconds')}"
            return f"delivered to the owner's channel{at}"
        if self.reason == NO_CHANNEL:
            return (
                "not delivered: this tenant configured no owner-facing channel "
                "(`taktusctl owner-channel set`)"
            )
        if self.reason == NOT_RAISED:
            return "not delivered yet: it is raised at the scheduler's next tick"
        return f"not delivered: {self.reason}"

    def text(self) -> str:
        return rule.shown(self.found, self.state)


@dataclass(frozen=True)
class Reported:
    """What one `report` did: reports raised, messages delivered, reports refused."""

    raised: int = 0
    delivered: int = 0
    refused: int = 0


class BrokenInterfaces:
    def __init__(
        self,
        failures: Failures,
        reports: ReportQueries,
        channels: ChannelOf,
        raising: RaiseReportHandler,
        clock: Clock,
    ) -> None:
        self._failures = failures
        self._reports = reports
        self._channels = channels
        self._raising = raising
        self._clock = clock

    async def noticed(self, tenant: Tenant) -> tuple[Noticed, ...]:
        """Every broken interface of the tenant, open and closed, each with its report."""
        known = {
            r.id: r
            for r in await self._reports.reports(tenant)
            if r.kind is ReportKind.FAILURE and r.id.startswith(ID_PREFIX)
        }
        closed = {i: r.filed.at for i, r in known.items() if r.filed is not None}
        channel = await self._channels.of(tenant)
        result: list[Noticed] = []
        for found in rule.broken(await self._failures.failures(tenant), closed):
            report = known.get(found.id)
            delivered = report is not None and report.message() is not None
            reason: str | None = None
            if report is None:
                reason = NO_CHANNEL if channel is None else NOT_RAISED
            elif not delivered:
                reason = _why(report)
            result.append(
                Noticed(
                    found=found,
                    report=report,
                    closed=found.id in closed,
                    delivered=delivered,
                    reason=reason,
                )
            )
        return tuple(result)

    async def report(self, tenant: Tenant) -> Reported:
        """Raise the report of every open broken interface that has none; try again a message
        that was not delivered, once an hour. Nothing where the tenant configured no channel."""
        if await self._channels.of(tenant) is None:
            return Reported()
        raised = delivered = refused = 0
        now = self._clock.now()
        for one in await self.noticed(tenant):
            if one.closed or one.delivered:
                continue
            try:
                if one.report is None:
                    report = await self._raising.execute(self._command(tenant, one.found))
                    raised += 1
                else:
                    last = _last_attempt(one.report)
                    if last is not None and now - last < RETRY:
                        continue
                    report = await self._raising.deliver(DeliverReport(tenant, one.report.id))
            except ReportingError:
                refused += 1
                continue
            if report.message() is not None:
                delivered += 1
        return Reported(raised=raised, delivered=delivered, refused=refused)

    def _command(self, tenant: Tenant, found: BrokenInterface) -> RaiseReport:
        return RaiseReport(
            tenant=tenant,
            id=found.id,
            kind=ReportKind.FAILURE,
            title=rule.title(found),
            needed=rule.needed(found),
            steps=rule.steps(found),
            standing_still=rule.standing_still(found),
            # The interface is broken now, and the runs it holds stand still now.
            due=self._clock.now().date(),
        )


def _why(report: Report) -> str:
    attempts = [d for d in report.deliveries if d.channel is DeliveryChannel.MESSAGE]
    if not attempts or attempts[-1].reason is None:
        return NOT_RAISED
    return attempts[-1].reason


def _last_attempt(report: Report) -> datetime | None:
    attempts = [d.at for d in report.deliveries if d.channel is DeliveryChannel.MESSAGE]
    return attempts[-1] if attempts else None
