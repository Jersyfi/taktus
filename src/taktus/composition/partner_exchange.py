"""A partner's message that arrives more often than its data contract's frequency, stopped
before anything of it is mapped and escalated to a person (UC-15.3, ADR-0315).

`ContractControl` answers the run component's boundary port (`ExternalControl`, ADR-0272) in
front of the one it wraps. At the first boundary after an import step under a contract that
names a frequency succeeded, it reads when the same step of the same process last succeeded in
another run. A message that arrived sooner than the contract's frequency allows stops the run at
that boundary, before the step that maps it: the ledger records `contract.deviated` with the
outcome `too_frequent`, and the run's reason names the clause it breaks. Nothing of the message
is mapped, completed or guessed.

`ContractWatch` delivers every such deviation once: the governance component writes the
situation package, and it reaches the role the version names for its escalations in the
tenant's owner-facing channel. The ledger records `contract.escalated`.

This is wiring, because the run is the run component's, the contract the process component's,
the package the governance component's and the channel the reporting component's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.escalation import Escalated
from taktus.components.governance.domain.service import escalations as rule
from taktus.components.process.domain.model import Escalation, ProcessVersion
from taktus.components.process.domain.service import partners
from taktus.components.reporting.application.service import (
    ChannelOf,
    NoChannel,
    NotSent,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.domain.model import Run, StepState
from taktus.components.run.ports.control import ExternalControl
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

FINISHED = "step.finished"
DEVIATED = "contract.deviated"
ESCALATED = "contract.escalated"
TOO_FREQUENT = "too_frequent"
OWNER = "owner"

log = structlog.get_logger("taktusd")


def report_id(run_id: str, step_id: str) -> str:
    return f"contract-{run_id}-{step_id}"


class ContractControl:
    def __init__(
        self,
        *,
        versions: Repository[ProcessVersion],
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
        inner: ExternalControl | None = None,
    ) -> None:
        self._versions = versions
        self._ledger = ledger
        self._work = work
        self._clock = clock
        self._inner = inner
        self._looked: set[tuple[str, str]] = set()

    async def withdrawn(self, run: Run) -> str | None:
        if self._inner is not None:
            said = await self._inner.withdrawn(run)
            if said is not None:
                return said
        async with self._work.transaction(run.tenant):
            version = await self._versions.get(run.tenant, run.process_version)
        if version is None:
            return None
        for contract in version.contracts.values():
            if contract.direction != "import" or contract.frequency is None:
                continue
            for step_id in contract.steps:
                key = (run.id, step_id)
                if key in self._looked or not _succeeded(run, step_id):
                    continue
                self._looked.add(key)
                said = await self._early(run, version, step_id)
                if said is not None:
                    return said
        return None

    async def _early(self, run: Run, version: ProcessVersion, step_id: str) -> str | None:
        process = run.process_version.rsplit("@", 1)[0]
        async with self._work.transaction(run.tenant):
            entries = await self._ledger.of_kinds(run.tenant, (FINISHED,))
        before = [
            e.ts
            for e in entries
            if e.refs.step_id == step_id
            and e.refs.run_id != run.id
            and e.outcome == "succeeded"
            and not e.rehearsal
            and (e.refs.process_version or "").rsplit("@", 1)[0] == process
        ]
        if not before:
            return None
        now = self._clock.now()
        said = partners.too_often(version, step_id, now - max(before))
        if said is None:
            return None
        async with self._work.transaction(run.tenant):
            await self._ledger.record(
                run.tenant,
                Fact(
                    kind=DEVIATED,
                    refs=LedgerRefs(
                        tenant=run.tenant,
                        run_id=run.id,
                        process_version=run.process_version,
                        step_id=step_id,
                    ),
                    outcome=TOO_FREQUENT,
                ),
            )
        return said


def _succeeded(run: Run, step_id: str) -> bool:
    try:
        return run.step_run(step_id).state is StepState.SUCCEEDED
    except KeyError:
        return False


class ContractWatch:
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
    ) -> None:
        self._ledger = ledger
        self._runs = runs
        self._versions = versions
        self._work = work
        self._clock = clock
        self._channels = channels
        self._raising = raising

    async def look(self, tenant: Tenant) -> tuple[str, ...]:
        """Every deviation not yet delivered, delivered once; the runs, by identifier."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (DEVIATED, ESCALATED))
        done = {(e.refs.run_id, e.refs.step_id) for e in entries if e.kind == ESCALATED}
        sent: list[str] = []
        for entry in entries:
            run_id, step_id = entry.refs.run_id, entry.refs.step_id
            if entry.kind != DEVIATED or run_id is None or step_id is None:
                continue
            if (run_id, step_id) in done:
                continue
            await self._deliver(tenant, run_id, step_id, entry.ts)
            done.add((run_id, step_id))
            sent.append(run_id)
        return tuple(sent)

    async def _deliver(self, tenant: Tenant, run_id: str, step_id: str, at: datetime) -> None:
        async with self._work.transaction(tenant):
            run = await self._runs.get(tenant, run_id)
            version = None if run is None else await self._versions.get(tenant, run.process_version)
        if run is None:
            return
        instructions = None if version is None else version.takeover
        escalated = Escalated(
            run_id=run.id,
            process_version=run.process_version,
            escalated_at=at,
            step_id=step_id,
            cause="contract_deviated",
            reason="the message arrived more often than its data contract allows",
            finished=tuple(s.step_id for s in run.step_runs if s.state is StepState.SUCCEEDED),
            reached=tuple(sorted({s.adapter for s in run.step_runs if s.adapter})),
            instructions=None if instructions is None else instructions.sequence,
            breaks=run.reason,
        )
        situation = rule.package(escalated)
        declared = None if version is None else version.escalation
        role = OWNER if declared is None else declared.role
        path = "ledger"
        if (declared is None or declared.path == "channel") and await self._raise(
            tenant, run, step_id, role, situation, at, declared
        ):
            path = "channel"
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=ESCALATED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        run_id=run.id,
                        process_version=run.process_version,
                        step_id=step_id,
                    ),
                    outcome=rule.outcome(situation) + ("" if path == "channel" else "_ledger"),
                ),
            )

    async def _raise(
        self,
        tenant: Tenant,
        run: Run,
        step_id: str,
        role: str,
        situation: SituationPackage,
        at: datetime,
        declared: Escalation | None,
    ) -> bool:
        if self._channels is None or self._raising is None:
            return False
        channel = await self._channels.of(tenant)
        if channel is None or role not in channel.roles:
            return False
        react = timedelta(0) if declared is None else declared.react_within
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=report_id(run.id, step_id),
                    kind=ReportKind.FAILURE,
                    title=situation.happened or f"Run {run.id} received a message too early",
                    needed=situation.needed or ("what is needed is not in the record",),
                    steps=situation.options or ("look at the run and decide by hand",),
                    standing_still=tuple(p for p in (situation.tried, situation.affected) if p)
                    or (f"run {run.id}",),
                    due=(at + react).date(),
                    links=((f"run {run.id}", f"/runs/{run.id}"),),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("a contract's deviation was not said", run=run.id, why=str(error))
            return False
        return True


INTERVAL_SECONDS = 60


def contracts_tick(
    watch: ContractWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick; a look that fails is logged and made again."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                await watch.look(tenant)
            except Exception as error:  # watching never stops the scheduler
                log.error(
                    "contract deviations not delivered; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )

    return tick
