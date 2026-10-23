"""A tenant's introduction in stages, wired (ADR-0137, UC-9.6).

The governance component keeps the plan and the rule. What it reads elsewhere is answered here,
because components never import each other:

- **the level a process runs at now**: its active version, read from the process component,
  lowered where a level fell by rule (ADR-0110);
- **takeover instructions**: no process version carries them yet (UC-6.3), so every process
  lacks them, and no stage opens on an instance until they exist. This keeps UC-9.6's rule
  strictly;
- **whether a name is a person**: the identity component;
- **the reports**: the tenant's owner-facing channel (ADR-0045), when it carries the plan's
  responsible role. A report that cannot be raised is logged; the ledger and the view hold
  what happened either way.

Registration asks the ceiling through the process component's port `StageCeilings`, answered
from the same use case. The elected scheduler looks at every tenant's stages once an hour.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

import structlog

from taktus.components.governance.application.service import Corrections, Stages
from taktus.components.governance.domain.model import (
    Incident,
    StagePlan,
    StageView,
)
from taktus.components.governance.ports import Identities, RunningLevel
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.process.ports import StageCeiling
from taktus.components.reporting.application.service import (
    ChannelOf,
    RaiseReport,
    RaiseReportHandler,
    ReportingError,
)
from taktus.components.reporting.domain.model import ReportKind
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, Stored, Tenant, UnitOfWork

INTERVAL_SECONDS = 3600
"""How often the scheduler looks: a condition counts weeks, and each look reads the entries of
the open stages' windows."""
DUE_DAYS = 7
"""Within how many days a report about a stage asks for a person's look."""

log = structlog.get_logger("taktusd")


class LevelsOfTheProcess:
    """Governance's port `ProcessLevels`: the active version's level, lowered where it fell."""

    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
        corrections: Corrections,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._work = work
        self._corrections = corrections

    async def running(self, tenant: Tenant, process_id: str) -> RunningLevel | None:
        async with self._work.transaction(tenant):
            process = await self._processes.get(tenant, process_id)
            version = (
                None
                if process is None or process.active_version is None
                else await self._versions.get(tenant, f"{process_id}@{process.active_version}")
            )
        if version is None:
            return None
        lowered = await self._corrections.lowered(tenant, version.ref)
        level = (
            version.autonomy.level
            if lowered.level is None
            else min(version.autonomy.level, lowered.level)
        )
        return RunningLevel(process_version=version.ref, level=level)


class NoTakeoverInstructions:
    """Governance's port `TakeoverInstructions` while no version carries them (UC-6.3)."""

    async def lacking(self, tenant: Tenant, process_id: str) -> str | None:
        return (
            "no process version carries takeover instructions yet (UC-6.3); a stage that adds "
            f"{process_id} opens once its active version does"
        )


class StageReportsOfTheChannel:
    """Governance's port `StageReports`, over the owner-facing channel (ADR-0045)."""

    def __init__(self, channel: ChannelOf, raising: RaiseReportHandler, clock: Clock) -> None:
        self._channel = channel
        self._raising = raising
        self._clock = clock

    async def carries(self, tenant: Tenant, role: str) -> bool:
        channel = await self._channel.of(tenant)
        return channel is not None and role in channel.roles

    async def proposed(
        self, tenant: Tenant, plan: StagePlan, stage: StageView, before: StageView | None
    ) -> None:
        figures = [] if before is None else _figures(before)
        await self._raise(
            tenant,
            RaiseReport(
                tenant=tenant,
                id=f"stage-{stage.stage.id}-proposed-{self._stamp()}",
                kind=ReportKind.NEED,
                title=f"Stage {stage.stage.name} can be opened",
                needed=[
                    f"A person's approval to open the stage {stage.stage.id!r}"
                    + (
                        "" if before is None else f": the stage {before.stage.id!r} before it holds"
                    ),
                    *figures,
                ],
                steps=[
                    "Read the figures; every one was counted from the ledger by rule.",
                    f"Open it: taktusctl stage open {stage.stage.id} --tenant {tenant} "
                    "--by <your identity>",
                    *(f"Still missing: {m}" for m in stage.missing),
                ],
                standing_still=[
                    f"{p} runs at most at level 2 until the stage opens"
                    for p in stage.stage.processes
                ],
                due=self._due(),
            ),
        )

    async def fell(
        self, tenant: Tenant, plan: StagePlan, stage: StageView, lowered: Sequence[Incident]
    ) -> None:
        await self._raise(
            tenant,
            RaiseReport(
                tenant=tenant,
                id=f"stage-{stage.stage.id}-fell-{self._stamp()}",
                kind=ReportKind.NEED,
                title=f"Stage {stage.stage.name} stopped holding",
                needed=[
                    f"A look at why the stage {stage.stage.id!r} no longer holds",
                    *(f"Not met: {m}" for m in stage.missing),
                ],
                steps=[
                    "Find the cause in the incidents of its processes (`taktusctl incident list`).",
                    "A level that fell rises again only by a version a person approves with its "
                    "history (UC-7.1).",
                ],
                standing_still=[
                    f"{i.process_id} fell from level {i.facts.get('level_before')} to "
                    f"{i.facts.get('level_after')}"
                    for i in lowered
                ]
                or [f"the stage {stage.stage.id!r} grants no level until it holds again"],
                due=self._due(),
            ),
        )

    async def _raise(self, tenant: Tenant, report: RaiseReport) -> None:
        try:
            await self._raising.execute(report)
        except ReportingError as error:
            log.error(
                "a report about a stage was not raised; the ledger and the view hold it",
                tenant=tenant,
                report=report.id,
                error=str(error),
            )

    def _stamp(self) -> str:
        return self._clock.now().strftime("%Y%m%dT%H%M%S")

    def _due(self) -> date:
        return (self._clock.now() + timedelta(days=DUE_DAYS)).date()


def _figures(view: StageView) -> list[str]:
    found = view.figures
    if found is None:
        return []
    rate = "none decided" if found.correction_rate is None else f"{found.correction_rate:.0%}"
    return [
        f"Figures of {view.stage.id!r}: open {found.weeks:.1f} week(s); {found.runs} run(s) "
        f"finished; {found.missed} expected run(s) missed; {found.incidents} incident(s); "
        f"highest correction rate {rate}; {found.undecided} proposal(s) waiting"
    ]


class CeilingsOfTheStages:
    """Registration's port `StageCeilings`, answered from `Stages`."""

    def __init__(self, stages: Stages) -> None:
        self._stages = stages

    async def ceiling(self, tenant: Tenant, process_id: str) -> StageCeiling | None:
        found = await self._stages.ceiling(tenant, process_id)
        if found is None:
            return None
        ceiling, missing = found
        return StageCeiling(level=ceiling.level, stage=ceiling.stage, missing=missing)


@dataclass(frozen=True)
class StageWiring:
    """Everything an entry point needs of the stages, built once."""

    stages: Stages
    ceilings: CeilingsOfTheStages
    """Registration's port."""


class RepositoryOf(Protocol):
    def __call__[T: Stored](self, kind: type[T]) -> Repository[T]: ...


def stage_wiring(
    of: RepositoryOf,
    work: UnitOfWork,
    ledger: Ledger,
    clock: Clock,
    *,
    identities: Identities,
    corrections: Corrections,
    channel: ChannelOf,
    raising: RaiseReportHandler,
) -> StageWiring:
    stages = Stages(
        of(StagePlan),
        of(Incident),
        ledger,
        work,
        clock,
        levels=LevelsOfTheProcess(of(Process), of(ProcessVersion), work, corrections),
        instructions=NoTakeoverInstructions(),
        identities=identities,
        reports=StageReportsOfTheChannel(channel, raising, clock),
    )
    return StageWiring(stages=stages, ceilings=CeilingsOfTheStages(stages))


def stages_tick(
    stages: Stages,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: every tenant's stages are looked at once the
    interval has passed since the last look. A look that fails is logged and made again at the
    next interval: it never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                looked = await stages.look(tenant)
            except Exception as error:  # a look must never take the scheduler down
                log.error(
                    "stages not looked at; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for stage in looked.fell:
                log.error("a stage stopped holding; its processes fell", tenant=tenant, stage=stage)
            for stage in looked.proposed:
                log.info("a stage was proposed for opening", tenant=tenant, stage=stage)

    return tick
