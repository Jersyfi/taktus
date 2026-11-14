"""Every ended run measured against its process's objectives, and a failure healed again and
again said to the owner (UC-4.6, ADR-0254).

`ObjectivesWatch` looks at a tenant's ledger. Each ended run — `run.finished` or
`run.escalated` — of a version that declares `slo.latency` or `slo.completion` and that was not
measured yet is measured once, by the governance component's rule, and recorded as
`slo.measured`: `met`, or `missed_` with the objectives it missed, with its duration. Each
failure healed its process's `heal_limit` of times is recorded once as `heal.recurred` and said
in the tenant's owner-facing channel as a report of kind `failure`: a failure healed again and
again is a design fault of the process, to be changed under UC-4.3.

This is wiring, because the runs' entries are the run component's, the objectives the process
component's, the rule the governance component's and the channel the reporting component's.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from taktus.components.governance.domain.service import objectives as rule
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.reporting.application.service import (
    ChannelOf,
    NoChannel,
    NotSent,
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import Brief, ReportKind, Said
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock
from taktus.ports.identity import ServedTenants
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

CREATED = "run.created"
FINISHED = "run.finished"
ESCALATED = "run.escalated"
MEASURED = "slo.measured"
HEALED = "step.healed"
RECURRED = "heal.recurred"
INTERVAL_SECONDS = 60

log = structlog.get_logger("taktusd")


@dataclass(frozen=True)
class Look:
    measured: tuple[tuple[str, str], ...] = ()
    """Each run measured, with the outcome recorded."""
    recurred: tuple[tuple[str, str], ...] = ()
    """Each process and step whose failure recurred."""


def process_of(version: str) -> str:
    return version.split("@", 1)[0]


class ObjectivesWatch:
    def __init__(
        self,
        *,
        ledger: Ledger,
        versions: Repository[ProcessVersion],
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        channels: ChannelOf | None = None,
        raising: RaiseReportHandler | None = None,
    ) -> None:
        self._clock = clock
        self._ledger = ledger
        self._versions = versions
        self._objects = objects
        self._work = work
        self._channels = channels
        self._raising = raising

    async def look(self, tenant: Tenant) -> Look:
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(
                tenant, (CREATED, FINISHED, ESCALATED, MEASURED, HEALED, RECURRED)
            )
        versions: dict[str, ProcessVersion | None] = {}

        async def version_of(ref: str) -> ProcessVersion | None:
            if ref not in versions:
                async with self._work.transaction(tenant):
                    versions[ref] = await self._versions.get(tenant, ref)
            return versions[ref]

        measured = await self._measure(tenant, entries, version_of)
        recurred = await self._recurrences(tenant, entries, version_of)
        return Look(measured=tuple(measured), recurred=tuple(recurred))

    async def _measure(
        self,
        tenant: Tenant,
        entries: Sequence[LedgerEntry],
        version_of: Callable[[str], Awaitable[ProcessVersion | None]],
    ) -> list[tuple[str, str]]:
        created: dict[str, datetime] = {}
        done = {e.refs.run_id for e in entries if e.kind == MEASURED and e.refs.run_id}
        ended: dict[str, list[bool]] = {}
        found: list[tuple[str, str]] = []
        for entry in entries:
            run_id, ref = entry.refs.run_id, entry.refs.process_version
            if run_id is None or ref is None or entry.rehearsal:
                continue
            if entry.kind == CREATED:
                created[run_id] = entry.ts
                continue
            if entry.kind not in (FINISHED, ESCALATED):
                continue
            recent = ended.setdefault(process_of(ref), [])
            recent.append(entry.kind == FINISHED)
            if run_id in done:
                continue
            version = await version_of(ref)
            slo = None if version is None else version.slo
            if slo is None or (slo.latency is None and slo.completion is None):
                continue
            began = created.get(run_id)
            duration = None if began is None else entry.ts - began
            missed = rule.missed(
                duration, tuple(recent), latency=slo.latency, completion=slo.completion
            )
            outcome = rule.outcome(missed)
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=MEASURED,
                        refs=LedgerRefs(tenant=tenant, run_id=run_id, process_version=ref),
                        outcome=outcome,
                        duration_seconds=None if duration is None else duration.total_seconds(),
                    ),
                )
            done.add(run_id)
            found.append((run_id, outcome))
        return found

    async def _recurrences(
        self,
        tenant: Tenant,
        entries: Sequence[LedgerEntry],
        version_of: Callable[[str], Awaitable[ProcessVersion | None]],
    ) -> list[tuple[str, str]]:
        said = {
            (process_of(e.refs.process_version or ""), e.refs.step_id or "", e.content_digest)
            for e in entries
            if e.kind == RECURRED
        }
        heals: list[rule.Heal] = []
        limits: dict[str, int] = {}
        refs: dict[tuple[str, str, str], LedgerEntry] = {}
        for entry in entries:
            if entry.kind != HEALED or entry.rehearsal or entry.refs.process_version is None:
                continue
            failure = await self._failure(entry)
            process = process_of(entry.refs.process_version)
            version = await version_of(entry.refs.process_version)
            if version is not None:
                limits[process] = version.heal_limit
            heal = rule.Heal(process=process, step=entry.refs.step_id or "", failure=failure)
            heals.append(heal)
            refs.setdefault((heal.process, heal.step, heal.failure), entry)
        found: list[tuple[str, str]] = []
        for recurring in rule.recurring(heals, limits):
            key = (recurring.process, recurring.step, recurring.failure)
            if key in said:
                continue
            first = refs[key]
            async with self._work.transaction(tenant):
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=RECURRED,
                        refs=LedgerRefs(
                            tenant=tenant,
                            process_version=first.refs.process_version,
                            step_id=recurring.step,
                        ),
                        outcome="proposed",
                        content_digest=recurring.failure,
                    ),
                )
            await self._say(tenant, recurring)
            found.append((recurring.process, recurring.step))
        return found

    async def _failure(self, entry: LedgerEntry) -> str:
        """The failure a heal answered, as a digest of its reason: the same reason is the same
        failure, whichever attempt it came on."""
        reason = ""
        if entry.content_digest is not None:
            stored = await self._objects.get(entry.content_digest)
            if stored is not None:
                reason = str(json.loads(stored).get("failure") or "")
        return "sha256:" + hashlib.sha256(reason.encode("utf-8")).hexdigest()

    async def _say(self, tenant: Tenant, recurring: rule.Recurring) -> None:
        if self._channels is None or self._raising is None:
            return
        if await self._channels.of(tenant) is None:
            return
        try:
            await self._raising.execute(
                RaiseReport(
                    tenant=tenant,
                    id=f"recurred-{recurring.process}-{recurring.step}-{recurring.failure[7:19]}",
                    kind=ReportKind.FAILURE,
                    title=(
                        f"Step {recurring.step} of {recurring.process} was healed "
                        f"{recurring.count} times for the same failure: a design fault of "
                        "the process"
                    ),
                    needed=(
                        f"A change of {recurring.process} that removes the failure's cause, as "
                        "a new version (UC-4.3).",
                    ),
                    steps=(
                        "Read the step's healed failures in its runs' ledger.",
                        "Change the process so that the failure no longer occurs, or accept it.",
                    ),
                    standing_still=(
                        f"Nothing yet: each run of {recurring.process} heals the failure again.",
                    ),
                    due=self._clock.now().date(),
                    brief=Brief(
                        headline=Said(
                            entry="recurred",
                            values={
                                "process": recurring.process,
                                "step": recurring.step,
                                "count": str(recurring.count),
                            },
                        ),
                        ask=Said(entry="recurred_ask"),
                    ),
                )
            )
        except (NotSent, NoChannel) as error:
            log.warning("a recurring failure was not said", why=str(error))


def objectives_tick(
    watch: ObjectivesWatch,
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
                    "objectives not measured; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )

    return tick
