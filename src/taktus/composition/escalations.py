"""A failure's escalation delivered with its situation package, and watched against its time to
react (UC-4.5, ADR-0252).

`EscalationWatch` looks at a tenant's `run.escalated` entries. For each one not yet delivered it
reads the run, its process version and the run's own entries, has the governance component
write the situation package, and delivers it by the path the version names for its escalations:
a report of kind `failure` in the tenant's owner-facing channel, to the role the version names
(`channel`), or the record alone (`ledger`). Either way the ledger records
`escalation.delivered`, whose outcome says whether the package is complete or which parts it
lacks. A run still escalated and a report still open past the version's time to react is
recorded once as `escalation.overdue`.

This is wiring, because the run is the run component's record, the version the process
component's, the package the governance component's and the channel the reporting component's.
Nothing here changes a run: the person resumes it, does the step by hand, or leaves it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import structlog

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.escalation import ByHand, Escalated, Target
from taktus.components.governance.domain.service import escalations as rule
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.reporting.application.service import (
    ChannelOf,
    NoChannel,
    NotSent,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import Report, ReportKind, ReportState
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

ESCALATED = "run.escalated"
DELIVERED = "escalation.delivered"
OVERDUE = "escalation.overdue"
HEALED = "step.healed"
OWNER = "owner"
"""The role an escalation reaches where its process version names none."""

log = structlog.get_logger("taktusd")


@dataclass(frozen=True)
class Look:
    """What one look did: the escalations delivered and the ones found overdue, by run."""

    delivered: tuple[str, ...] = ()
    overdue: tuple[str, ...] = ()


class ReportsRead(Protocol):
    """What the watch reads of a report: whether it was answered (`ReportQueries.one`)."""

    async def one(self, tenant: Tenant, report_id: str) -> Report | None: ...


def report_id(run_id: str, number: int) -> str:
    """The report of a run's `number`-th escalation."""
    return f"escalation-{run_id}-{number}"


class EscalationWatch:
    def __init__(
        self,
        *,
        ledger: Ledger,
        runs: Repository[Run],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        clock: Clock,
        channels: ChannelOf | None = None,
        raising: RaiseReportHandler | None = None,
        reports: ReportsRead | None = None,
    ) -> None:
        """Without `channels` and `raising`, every package goes by the path `ledger`."""
        self._ledger = ledger
        self._runs = runs
        self._versions = versions
        self._work = work
        self._clock = clock
        self._channels = channels
        self._raising = raising
        self._reports = reports

    async def look(self, tenant: Tenant) -> Look:
        """Every escalation not yet delivered, delivered; the newest delivery of a run found
        overdue, recorded once."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (ESCALATED, DELIVERED, OVERDUE))
        escalated: dict[str, list[LedgerEntry]] = {}
        delivered: dict[str, list[LedgerEntry]] = {}
        late_already: set[str] = set()
        """Runs whose newest delivery was recorded overdue."""
        for entry in entries:
            run_id = entry.refs.run_id
            if run_id is None:
                continue
            if entry.kind == ESCALATED:
                escalated.setdefault(run_id, []).append(entry)
            elif entry.kind == DELIVERED:
                delivered.setdefault(run_id, []).append(entry)
                late_already.discard(run_id)
            else:
                late_already.add(run_id)
        sent: list[str] = []
        late: list[str] = []
        now = self._clock.now()
        for run_id, ends in escalated.items():
            done = delivered.get(run_id, [])
            if len(done) < len(ends):
                for number in range(len(done) + 1, len(ends) + 1):
                    await self._deliver(tenant, run_id, number, ends[number - 1])
                    sent.append(run_id)
                continue
            if run_id in late_already or not done:
                continue
            if await self._overdue(tenant, run_id, len(done), done[-1], now):
                late.append(run_id)
        return Look(delivered=tuple(sent), overdue=tuple(late))

    async def _facts(
        self, tenant: Tenant, run_id: str, at: datetime
    ) -> tuple[Escalated, Target, Run | None]:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            version = None if run is None else await self._versions.get(tenant, run.process_version)
            own = await self._ledger.entries(tenant, run_id)
        declared = None if version is None else version.escalation
        target = Target(
            role=OWNER if declared is None else declared.role,
            react_within=None if declared is None else declared.react_within,
            path="channel" if declared is None else declared.path,
        )
        if run is None:
            return Escalated(run_id=run_id, process_version="unknown", escalated_at=at), target, run
        return escalated_of(run, version, own, at), target, run

    async def _deliver(self, tenant: Tenant, run_id: str, number: int, entry: LedgerEntry) -> None:
        escalated, target, _ = await self._facts(tenant, run_id, entry.ts)
        situation = rule.package(escalated)
        outcome = rule.outcome(situation)
        path = target.path
        if path == "channel":
            reached = await self._raise(tenant, run_id, number, situation, target, entry.ts)
            if not reached:
                path = "ledger"
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=DELIVERED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        run_id=run_id,
                        process_version=escalated.process_version,
                        step_id=escalated.step_id,
                    ),
                    outcome=outcome if path == "channel" else f"{outcome}_ledger",
                ),
            )
        log.info(
            "an escalation was delivered with its situation package",
            run=run_id,
            path=path,
            outcome=outcome,
        )

    async def _raise(
        self,
        tenant: Tenant,
        run_id: str,
        number: int,
        situation: SituationPackage,
        target: Target,
        at: datetime,
    ) -> bool:
        if self._channels is None or self._raising is None:
            return False
        channel = await self._channels.of(tenant)
        if channel is None or target.role not in channel.roles:
            return False
        lacking = situation.lacking
        title = situation.happened or "A run escalated, and the record says nothing of why"
        if lacking:
            title += " (this package lacks: " + ", ".join(lacking) + ")"
        due = (at + (target.react_within or timedelta(0))).date()
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=report_id(run_id, number),
                    kind=ReportKind.FAILURE,
                    title=title,
                    needed=situation.needed or ("what is needed is not in the record",),
                    steps=situation.options or ("look at the run and decide by hand",),
                    standing_still=tuple(p for p in (situation.tried, situation.affected) if p)
                    or (f"run {run_id}",),
                    due=due,
                    links=((f"run {run_id}", f"/runs/{run_id}"),),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("an escalation's report was not sent", run=run_id, why=str(error))
            return False
        return True

    async def _overdue(
        self, tenant: Tenant, run_id: str, number: int, entry: LedgerEntry, now: datetime
    ) -> bool:
        _, target, run = await self._facts(tenant, run_id, entry.ts)
        reacted = run is None or run.state is not RunState.ESCALATED
        if not reacted and self._reports is not None:
            report = await self._reports.one(tenant, report_id(run_id, number))
            reacted = report is not None and report.state is not ReportState.OPEN
        if not rule.overdue(target, entry.ts, reacted, now):
            return False
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=OVERDUE,
                    refs=LedgerRefs(
                        tenant=tenant,
                        run_id=run_id,
                        process_version=None if run is None else run.process_version,
                    ),
                    outcome="unanswered",
                    duration_seconds=(now - entry.ts).total_seconds(),
                ),
            )
        return True


def escalated_of(
    run: Run, version: ProcessVersion | None, own: Sequence[LedgerEntry], at: datetime
) -> Escalated:
    """The record of an escalated run, as the governance component reads it."""
    failed = [s for s in run.step_runs if s.state in (StepState.FAILED, StepState.REJECTED)]
    last = failed[-1] if failed else None
    instructions = None if version is None else version.takeover
    hand = None
    if last is not None and instructions is not None:
        step = instructions.steps.get(last.step_id)
        if step is not None:
            hand = ByHand(
                system=step.system,
                do=step.do,
                expertise=step.expertise,
                credentials=tuple(c.parameter for c in step.credentials),
                done=step.done,
            )
    return Escalated(
        run_id=run.id,
        process_version=run.process_version,
        escalated_at=at,
        step_id=None if last is None else last.step_id,
        cause=None if run.cause is None else str(run.cause),
        reason=run.reason if last is None else (last.reason or run.reason),
        attempts=0 if last is None else last.attempt,
        healed=tuple(e.outcome for e in own if e.kind == HEALED and e.outcome),
        finished=tuple(s.step_id for s in run.step_runs if s.state is StepState.SUCCEEDED),
        reached=tuple(sorted({s.adapter for s in run.step_runs if s.adapter})),
        left=sum(1 for e in own if e.kind.startswith("egress.")),
        by_hand=hand,
        instructions=None if instructions is None else instructions.sequence,
    )


INTERVAL_SECONDS = 60
"""How often the scheduler looks: a time to react is minutes long at the shortest."""


def escalations_tick(
    watch: EscalationWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant is looked at once the interval has
    passed since the last look. A look that fails is logged and made again at the next one."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                done = await watch.look(tenant)
            except Exception as error:  # a look must never take the scheduler down
                log.error(
                    "escalations not watched; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for run_id in done.overdue:
                log.warning("an escalation passed its time to react", tenant=tenant, run=run_id)

    return tick
