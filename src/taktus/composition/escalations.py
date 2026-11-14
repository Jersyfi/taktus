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

A backlog is never a flood (ADR-0316 §1). Only a current escalation — its run still escalated,
the newest of its run, within the horizon — is delivered on its own, at most a few per role and
look. A settled one is recorded as `escalation.not_sent` and says nothing. The rest go into one
summary per role and look, whose message is one line and a link.

This is wiring, because the run is the run component's record, the version the process
component's, the package the governance component's and the channel the reporting component's.
Nothing here changes a run: the person resumes it, does the step by hand, or leaves it.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import structlog

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.escalation import ByHand, Escalated, Target
from taktus.components.governance.domain.service import escalations as rule
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.service import partners
from taktus.components.reporting.application.service import (
    ChannelOf,
    NoChannel,
    NotSent,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import (
    Brief,
    OwnerChannel,
    Report,
    ReportKind,
    ReportState,
    Said,
)
from taktus.components.reporting.domain.service import backlog
from taktus.components.reporting.domain.service.rendering import run_url
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.components.run.domain.service import checking
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

ESCALATED = "run.escalated"
DELIVERED = "escalation.delivered"
NOT_SENT = "escalation.not_sent"
"""An escalation handled without a message of its own (ADR-0316 §1): `settled` — its run no
longer waits, or a newer escalation of it exists — or `summarised` into one report."""
SETTLED = "settled"
SUMMARISED = "summarised"
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
        horizon: timedelta = backlog.HORIZON,
        per_look: int = backlog.PER_LOOK,
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
        self._horizon = horizon
        self._per_look = per_look

    async def look(self, tenant: Tenant) -> Look:
        """Every escalation not yet handled, sorted (ADR-0316 §1): a current one delivered on its
        own, at most a few per role; a settled one recorded as not sent; the rest summarised
        once per role. The newest delivery of a run found overdue, recorded once."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (ESCALATED, DELIVERED, NOT_SENT, OVERDUE))
        escalated: dict[str, list[LedgerEntry]] = {}
        handled: dict[str, list[str]] = {}
        """By run: the kinds that handled its escalations, in order."""
        late_already: set[str] = set()
        """Runs whose newest delivery was recorded overdue."""
        for entry in entries:
            run_id = entry.refs.run_id
            if run_id is None:
                continue
            if entry.kind == ESCALATED:
                escalated.setdefault(run_id, []).append(entry)
            elif entry.kind in (DELIVERED, NOT_SENT):
                handled.setdefault(run_id, []).append(entry.kind)
                late_already.discard(run_id)
            else:
                late_already.add(run_id)
        now = self._clock.now()
        channel = None if self._channels is None else await self._channels.of(tenant)
        pending: list[backlog.Pending] = []
        facts: dict[str, _Facts] = {}
        sent: list[str] = []
        late: list[str] = []
        for run_id, ends in escalated.items():
            done = handled.get(run_id, [])
            if len(done) >= len(ends):
                if run_id in late_already or not done or done[-1] != DELIVERED:
                    continue
                if await self._overdue(tenant, run_id, len(done), ends[len(done) - 1], now):
                    late.append(run_id)
                continue
            for number in range(len(done) + 1, len(ends) + 1):
                entry = ends[number - 1]
                found = await self._facts(tenant, run_id, entry.ts)
                key = f"{run_id}#{number}"
                facts[key] = found
                if found.target.path == "ledger":
                    await self._record(tenant, found, DELIVERED, _ledger(found))
                    continue
                pending.append(
                    backlog.Pending(
                        key=key,
                        run=run_id,
                        role=found.target.role,
                        at=entry.ts,
                        waiting=found.run is not None and found.run.state is RunState.ESCALATED,
                        newest=number == len(ends),
                    )
                )
        decided = backlog.sort(pending, now, horizon=self._horizon, per_look=self._per_look)
        for key in decided.settled:
            await self._record(tenant, facts[key], NOT_SENT, SETTLED)
        for key in decided.send:
            run_id, nth = key.rsplit("#", 1)
            await self._deliver(tenant, run_id, int(nth), facts[key], channel)
            sent.append(run_id)
        for role, keys in decided.summarised.items():
            told = await self._summarise(tenant, role, [facts[k] for k in keys], channel, now)
            for key in keys:
                outcome = SUMMARISED if told else f"{SUMMARISED}_ledger"
                await self._record(tenant, facts[key], NOT_SENT, outcome)
        return Look(delivered=tuple(sent), overdue=tuple(late))

    async def _facts(self, tenant: Tenant, run_id: str, at: datetime) -> _Facts:
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
        record = (
            Escalated(run_id=run_id, process_version="unknown", escalated_at=at)
            if run is None
            else escalated_of(run, version, own, at)
        )
        return _Facts(
            escalated=record,
            target=target,
            run=run,
            name=_name(version, record.process_version),
        )

    async def _record(self, tenant: Tenant, facts: _Facts, kind: str, outcome: str) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(
                        tenant=tenant,
                        run_id=facts.escalated.run_id,
                        process_version=facts.escalated.process_version,
                        step_id=facts.escalated.step_id,
                    ),
                    outcome=outcome,
                ),
            )

    async def _deliver(
        self,
        tenant: Tenant,
        run_id: str,
        number: int,
        facts: _Facts,
        channel: OwnerChannel | None,
    ) -> None:
        situation = rule.package(facts.escalated)
        outcome = rule.outcome(situation)
        reached = await self._raise(tenant, run_id, number, situation, facts, channel)
        await self._record(tenant, facts, DELIVERED, outcome if reached else f"{outcome}_ledger")
        log.info(
            "an escalation was delivered with its situation package",
            run=run_id,
            path="channel" if reached else "ledger",
            outcome=outcome,
        )

    async def _raise(
        self,
        tenant: Tenant,
        run_id: str,
        number: int,
        situation: SituationPackage,
        facts: _Facts,
        channel: OwnerChannel | None,
    ) -> bool:
        if self._raising is None or channel is None or facts.target.role not in channel.roles:
            return False
        at = facts.escalated.escalated_at
        due = (at + (facts.target.react_within or timedelta(0))).date()
        standing = tuple(p for p in (situation.tried, situation.affected) if p)
        if situation.lacking:
            standing += ("This package lacks: " + ", ".join(situation.lacking) + ".",)
        page = run_url(channel, run_id)
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=report_id(run_id, number),
                    kind=ReportKind.FAILURE,
                    title=situation.happened
                    or f"Run {run_id} escalated; its record says nothing why",
                    needed=situation.needed
                    or ("Nothing in the record names it; the run's page holds what it has.",),
                    steps=situation.options or ("Look at the run and decide by hand.",),
                    standing_still=standing,
                    due=due,
                    links=() if page is None else ((f"run {run_id}", page),),
                    brief=_brief(facts),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("an escalation's report was not sent", run=run_id, why=str(error))
            return False
        return True

    async def _summarise(
        self,
        tenant: Tenant,
        role: str,
        listed: Sequence[_Facts],
        channel: OwnerChannel | None,
        now: datetime,
    ) -> bool:
        """One report for every escalation of a role not delivered on its own (ADR-0316 §1): its
        record and its view list each run; its message is one headline and a link."""
        if self._raising is None or channel is None or role not in channel.roles:
            return False
        lines: list[str] = []
        links: list[tuple[str, str]] = []
        for facts in listed:
            record = facts.escalated
            step = f" at step {record.step_id}" if record.step_id else ""
            lines.append(
                f"{facts.name}{step}: run {record.run_id}, escalated "
                f"{record.escalated_at.date().isoformat()}."
            )
            page = run_url(channel, record.run_id)
            if page is not None:
                links.append((f"run {record.run_id}", page))
        count = len(listed)
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=f"escalations-{role}-{now:%Y%m%dT%H%M}",
                    kind=ReportKind.FAILURE,
                    title=f"{count} older escalations are open",
                    needed=lines,
                    steps=(
                        "Open each run's page: resume it once its cause is removed, do its step "
                        "by hand, or leave it stopped.",
                    ),
                    standing_still=(f"{count} runs are escalated and wait for a person.",),
                    due=now.date(),
                    links=links,
                    brief=Brief(
                        headline=Said(entry="backlog", values={"count": str(count)}),
                        ask=Said(entry="backlog_ask"),
                    ),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("a summary of escalations was not sent", role=role, why=str(error))
            return False
        return True

    async def _overdue(
        self, tenant: Tenant, run_id: str, number: int, entry: LedgerEntry, now: datetime
    ) -> bool:
        found = await self._facts(tenant, run_id, entry.ts)
        run, target = found.run, found.target
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


@dataclass(frozen=True)
class _Facts:
    """What the watch read of one escalation."""

    escalated: Escalated
    target: Target
    run: Run | None
    name: str
    """The process's name, as people know it."""


def _name(version: ProcessVersion | None, ref: str) -> str:
    """The process's name; its identifier where the version is not known."""
    return version.name if version is not None else ref.rsplit("@", 1)[0]


def _ledger(facts: _Facts) -> str:
    return rule.outcome(rule.package(facts.escalated)) + "_ledger"


def brief_of(escalated: Escalated, name: str) -> Brief:
    """An escalation's short form (ADR-0316 §2): which process stopped where, by its name; the
    failure as one quoted line; the options in a few words."""
    if escalated.step_id is None:
        return Brief(headline=Said(entry="escalated_unknown", values={"process": name}))
    cause = escalated.cause or ""
    if escalated.reason:
        cause = f"{cause}: {escalated.reason}" if cause else escalated.reason
    return Brief(
        headline=Said(entry="escalated", values={"process": name, "step": escalated.step_id}),
        quote=cause or None,
        ask=Said(entry="escalated_ask_hand" if escalated.by_hand else "escalated_ask"),
    )


def _brief(facts: _Facts) -> Brief:
    return brief_of(facts.escalated, facts.name)


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
        breaks=None
        if version is None or last is None
        else _breach(version, last.step_id, last.reason),
    )


def _breach(version: ProcessVersion, step_id: str, reason: str | None) -> str | None:
    """The data contract's clause the failed step broke, from the fields its failed shape check
    found lacking (`checking.LACKS`), by the process component's rule (ADR-0303)."""
    lacking: list[str] = []
    if reason is not None and checking.LACKS in reason:
        named = re.split(r";|\.(?:\s|$)", reason.split(checking.LACKS, 1)[1], maxsplit=1)[0]
        lacking = [f.strip() for f in named.split(",") if f.strip()]
    return partners.breach(version, step_id, lacking)


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
