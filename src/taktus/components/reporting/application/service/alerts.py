"""Use case: what needs a person's action reaches the owner of the tenant (ADR-0106, issue #323).

`noticed` is the view: the rules over the recorded facts — capacity crossings, lost claims, the
backup's state — every alert with what became of its report. It is computed from the facts each
time it is read, so there is nothing to keep in step with it. The facts are recorded whether or
not anyone hears of them, and `taktusctl alerts` shows them.

`report` raises the report of every alert in effect that has none yet, as a report of kind
`failure` through the owner-facing channel (ADR-0045), as a broken interface's is raised
(ADR-0047). Raising is idempotent by the report's identifier, which the alert derives from its
facts: it is said once, however often the scheduler looks. A message that was not delivered is
tried again once an hour while the alert is in effect. A cleared alert, or one the owner
answered that it is done, sends nothing more. A tenant without an owner-facing channel raises
nothing, and the view says that the report was not delivered and why.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service.broken_interfaces import (
    NO_CHANNEL,
    NOT_RAISED,
    RETRY,
    Reported,
    last_attempt,
    why_not_delivered,
)
from taktus.components.reporting.application.service.configure_channel import ChannelOf
from taktus.components.reporting.application.service.errors import ReportingError
from taktus.components.reporting.application.service.raise_report import (
    DeliverReport,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import ID_PREFIXES, Alert, Report, ReportKind
from taktus.components.reporting.domain.service import alerts as rule
from taktus.components.reporting.ports import Signals
from taktus.ports.clock import Clock
from taktus.ports.persistence import Tenant


@dataclass(frozen=True)
class Alerted:
    """An alert, and what became of its report."""

    alert: Alert
    report: Report | None
    closed: bool
    """The owner answered its report that it is done."""
    delivered: bool
    """Its message reached the owner's channel."""
    reason: str | None
    """Why it was not delivered, as a token: `no_channel`, `not_raised`, or the reason of the
    last delivery that failed. None when it was, or when it cleared before it was raised."""

    @property
    def state(self) -> str:
        """What became of the report, in one line for the operator."""
        if self.closed:
            return "closed: the owner answered that it is done"
        if self.delivered and self.report is not None:
            message = self.report.message()
            at = "" if message is None else f" at {message.at.isoformat(timespec='seconds')}"
            return f"delivered to the owner's channel{at}"
        if not self.alert.in_effect:
            return "cleared before its report was delivered"
        if self.reason == NO_CHANNEL:
            return (
                "not delivered: this tenant configured no owner-facing channel "
                "(`taktusctl owner-channel set`)"
            )
        if self.reason == NOT_RAISED:
            return "not delivered yet: it is raised at the scheduler's next tick"
        return f"not delivered: {self.reason}"

    def text(self) -> str:
        return rule.shown(self.alert, self.state)


class Alerts:
    def __init__(
        self,
        signals: Signals,
        reports: ReportQueries,
        channels: ChannelOf,
        raising: RaiseReportHandler,
        clock: Clock,
    ) -> None:
        self._signals = signals
        self._reports = reports
        self._channels = channels
        self._raising = raising
        self._clock = clock

    async def noticed(self, tenant: Tenant) -> tuple[Alerted, ...]:
        """Every alert of the tenant, in effect, cleared and closed, each with its report."""
        prefixes = tuple(ID_PREFIXES.values())
        known = {
            r.id: r
            for r in await self._reports.reports(tenant)
            if r.kind is ReportKind.FAILURE and r.id.startswith(prefixes)
        }
        closed = {i: r.filed.at for i, r in known.items() if r.filed is not None}
        signalled = await self._signals.signalled(tenant)
        found: list[Alert] = [
            *rule.capacity(signalled.capacity),
            *rule.claims_lost(signalled.claims_lost, closed),
        ]
        backup = rule.backup(signalled.backup, self._clock.now())
        if backup is not None:
            found.append(backup)
        channel = await self._channels.of(tenant)
        result: list[Alerted] = []
        for alert in found:
            report = known.get(alert.id)
            delivered = report is not None and report.message() is not None
            reason: str | None = None
            if report is None and alert.in_effect:
                reason = NO_CHANNEL if channel is None else NOT_RAISED
            elif report is not None and not delivered:
                reason = why_not_delivered(report)
            result.append(
                Alerted(
                    alert=alert,
                    report=report,
                    closed=alert.id in closed,
                    delivered=delivered,
                    reason=reason,
                )
            )
        return tuple(result)

    async def report(self, tenant: Tenant) -> Reported:
        """Raise the report of every alert in effect that has none; try again a message that was
        not delivered, once an hour. Nothing where the tenant configured no channel."""
        if await self._channels.of(tenant) is None:
            return Reported()
        raised = delivered = refused = 0
        now = self._clock.now()
        for one in await self.noticed(tenant):
            if one.closed or one.delivered or not one.alert.in_effect:
                continue
            try:
                if one.report is None:
                    report = await self._raising.execute(self._command(tenant, one.alert))
                    raised += 1
                else:
                    last = last_attempt(one.report)
                    if last is not None and now - last < RETRY:
                        continue
                    report = await self._raising.deliver(DeliverReport(tenant, one.report.id))
            except ReportingError:
                refused += 1
                continue
            if report.message() is not None:
                delivered += 1
        return Reported(raised=raised, delivered=delivered, refused=refused)

    def _command(self, tenant: Tenant, alert: Alert) -> RaiseReport:
        return RaiseReport(
            tenant=tenant,
            id=alert.id,
            kind=ReportKind.FAILURE,
            title=alert.title,
            needed=alert.needed,
            steps=alert.steps,
            standing_still=alert.standing_still,
            # The condition holds now, and a person must act on it now.
            due=self._clock.now().date(),
        )
