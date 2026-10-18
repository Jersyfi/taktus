"""Use cases: a corridor configured by a person, and signals judged against their corridors
(ADR-0109, UC-6.13).

**`Corridors`** keeps the tenant's corridors. Each change is a new version, stored beside the
earlier ones, and `corridor.changed` records who made it, with the version's digest. A change
that comes from a run or a worker's assignment, or from an identity the tenant does not know, is
refused, and `corridor.refused` records it. So is a corridor that names a person.

**`SignalWatch`** judges each corridor's newest attempt. A red value raises an incident through
`RedIncidents` and a report of kind `failure` at once. Once a day from the report hour, it raises
the daily report of kind `signals`: every signal outside its corridor and every one not
measured, each line with its run, its step and its case, and the processes a person may start
from it. Raising is idempotent by the report's identifier.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, time, timedelta
from typing import Any

from pydantic import ValidationError

from taktus.components.reporting.application.query import ReportQueries
from taktus.components.reporting.application.service._ledger import digest
from taktus.components.reporting.application.service.configure_channel import ChannelOf
from taktus.components.reporting.application.service.errors import ReportingError
from taktus.components.reporting.application.service.raise_report import (
    RaiseReport,
    RaiseReportHandler,
)
from taktus.components.reporting.domain.model import OwnerChannel, Report, ReportKind
from taktus.components.reporting.domain.model.signal import (
    ADMITTED,
    MEASURING,
    Corridor,
    Judged,
    Level,
)
from taktus.components.reporting.domain.service import corridors as rule
from taktus.components.reporting.domain.service.rendering import run_url
from taktus.components.reporting.ports.signals import (
    Measurements,
    MeasuringSteps,
    RedIncidents,
    RedSignal,
)
from taktus.ports.clock import Clock
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerRefs

CHANGED = "corridor.changed"
REFUSED = "corridor.refused"
REPORT_AT = time(6, 0)
"""When the daily report is raised, in UTC, for every tenant (ADR-0109 §5, NTC-0214)."""
KEPT = ("id", "tenant", "version", "changed_at", "retired")


class CorridorRefused(ReportingError):
    """A change of a corridor that is not a person's, or that names a person. Recorded, and
    nothing changed."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


@dataclass(frozen=True)
class ConfigureCorridor:
    """What a person sets of one signal's corridor; what it leaves out stays as the version in
    force has it. Who sets it is given beside it (`Corridors.configure`), never a field beside
    its figures (principle 14)."""

    tenant: Tenant
    signal: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    retire: bool = False


@dataclass(frozen=True)
class Changer:
    """Who asks for the change, and through what. A change that arrives from a run or from a
    worker's assignment is a process's or a worker's, whoever it acts for."""

    identity: str
    run_id: str | None = None
    assignment_id: str | None = None


@dataclass(frozen=True)
class Changed:
    """One version of a corridor and who made it, as its ledger entry says."""

    corridor: Corridor
    actor: str | None


def corridor_digest(corridor: Corridor) -> str:
    return digest(json.dumps(corridor.document(), sort_keys=True, ensure_ascii=False))


class Corridors:
    def __init__(
        self,
        corridors: Repository[Corridor],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        identities: IdentityResolver,
        steps: MeasuringSteps,
        channels: ChannelOf,
    ) -> None:
        self._corridors = corridors
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._identities = identities
        self._steps = steps
        self._channels = channels

    async def every(self, tenant: Tenant) -> list[Corridor]:
        """Every version of every corridor, oldest first."""
        async with self._work.transaction(tenant):
            found = list(await self._corridors.list(tenant))
        return sorted(found, key=lambda c: (c.signal, c.version))

    async def current(self, tenant: Tenant) -> list[Corridor]:
        """The version in force of every signal that is not retired, by signal."""
        newest: dict[str, Corridor] = {}
        for corridor in await self.every(tenant):
            newest[corridor.signal] = corridor
        return [c for c in newest.values() if not c.retired]

    async def history(self, tenant: Tenant, signal: str) -> list[Changed]:
        """Every version of one signal's corridor, with who made it and when."""
        versions = [c for c in await self.every(tenant) if c.signal == signal]
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (CHANGED,))
        by_digest = {e.content_digest: e.refs.actor for e in entries}
        return [Changed(c, by_digest.get(corridor_digest(c))) for c in versions]

    async def configure(self, command: ConfigureCorridor, *, by: Changer) -> Corridor:
        """A new version of the corridor. `CorridorRefused` for a change that is not a person's
        or that names a person, recorded; `ValueError` for a corridor that does not hold."""
        tenant = command.tenant
        if by.run_id is not None:
            await self._refuse(tenant, "process", by, "a process does not change a corridor")
        if by.assignment_id is not None:
            await self._refuse(tenant, "worker", by, "a worker does not change a corridor")
        if await self._identities.identity(tenant, by.identity) is None:
            await self._refuse(tenant, "unknown", by, f"{by.identity!r} is not known to {tenant}")
        versions = [c for c in await self.every(tenant) if c.signal == command.signal]
        before = versions[-1] if versions else None
        kept = (
            {} if before is None else {k: v for k, v in before.document().items() if k not in KEPT}
        )
        version = 1 if before is None else before.version + 1
        try:
            corridor = Corridor.model_validate(
                {
                    **kept,
                    **{k: v for k, v in command.fields.items() if k not in KEPT},
                    "id": f"{command.signal}@{version}",
                    "tenant": tenant,
                    "signal": command.signal,
                    "version": version,
                    "retired": command.retire,
                    "changed_at": self._clock.now(),
                }
            )
        except ValidationError as error:
            raise ValueError(_findings(error)) from None
        if not corridor.retired:
            await self._holds(corridor, by)
        async with self._work.transaction(tenant):
            await self._corridors.put(tenant, corridor)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CHANGED,
                    refs=LedgerRefs(tenant=tenant, actor=by.identity),
                    outcome="retired" if corridor.retired else "configured",
                    content_digest=corridor_digest(corridor),
                ),
            )
        return corridor

    async def _holds(self, corridor: Corridor, by: Changer) -> None:
        tenant = corridor.tenant
        for name in (corridor.signal, corridor.about.name):
            if name is not None and await self._identities.identity(tenant, name) is not None:
                await self._refuse(
                    tenant,
                    "person",
                    by,
                    f"{name!r} is a person of {tenant}: a signal measures no named person, "
                    "and a figure of people's work is a role's or a department's",
                )
        declared = await self._steps.declared(tenant, corridor.process, corridor.step)
        if declared is None:
            raise ValueError(
                f"the active version of {corridor.process} has no step {corridor.step!r}"
            )
        if declared.method not in MEASURING or declared.exactness not in ADMITTED:
            raise ValueError(
                f"step {corridor.step!r} is {declared.method}, {declared.exactness}: a signal is "
                "measured by a rule or statistics, exact or sourced"
            )
        channel = await self._channels.of(tenant)
        if channel is None or corridor.role not in channel.roles:
            carried = "none" if channel is None else ", ".join(channel.roles)
            raise ValueError(
                f"a red value reaches the role {corridor.role!r} through the owner-facing "
                f"channel, which carries {carried}: configure the channel's roles first"
            )

    async def _refuse(self, tenant: Tenant, reason: str, by: Changer, detail: str) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=REFUSED,
                    refs=LedgerRefs(
                        tenant=tenant,
                        actor=by.identity,
                        run_id=by.run_id,
                        assignment_id=by.assignment_id,
                    ),
                    outcome=reason,
                ),
            )
        raise CorridorRefused(reason, detail)


def _findings(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'corridor'}: {e['msg']}" for e in error.errors()
    )


@dataclass(frozen=True)
class Looked:
    """What one look at a tenant found and raised."""

    judged: tuple[Judged, ...] = ()
    """The signals judged at this look: those whose process recorded something new."""
    incidents: tuple[str, ...] = ()
    reported: int = 0
    refused: int = 0


class SignalWatch:
    def __init__(
        self,
        corridors: Corridors,
        measurements: Measurements,
        incidents: RedIncidents,
        channels: ChannelOf,
        reports: ReportQueries,
        raising: RaiseReportHandler,
        clock: Clock,
        *,
        report_at: time = REPORT_AT,
    ) -> None:
        self._corridors = corridors
        self._measurements = measurements
        self._incidents = incidents
        self._channels = channels
        self._reports = reports
        self._raising = raising
        self._clock = clock
        self._report_at = report_at
        self._seen: dict[tuple[Tenant, str], int] = {}
        """The newest `step.finished` each corridor's process had at the last look: a look
        judges only a corridor whose process recorded something since."""

    async def judge(self, tenant: Tenant, corridor: Corridor) -> Judged:
        now = self._clock.now()
        reach = corridor.window if corridor.bounds == "median" else timedelta(0)
        since = now - corridor.fresh - reach
        attempts = await self._measurements.recorded(
            tenant, corridor.process, corridor.step, since=since
        )
        return rule.judge(corridor, attempts, now)

    async def judged(self, tenant: Tenant) -> list[tuple[Corridor, Judged]]:
        """Every signal in force, judged now."""
        return [(c, await self.judge(tenant, c)) for c in await self._corridors.current(tenant)]

    async def look(self, tenant: Tenant) -> Looked:
        """Judge every corridor whose process recorded something new; raise the incident and
        the report of a red value at once."""
        judged: list[Judged] = []
        incidents: list[str] = []
        reported = refused = 0
        channel = await self._channels.of(tenant)
        for corridor in await self._corridors.current(tenant):
            newest = await self._measurements.newest(tenant, corridor.process)
            key = (tenant, corridor.id)
            if newest is None or self._seen.get(key) == newest:
                continue
            one = await self.judge(tenant, corridor)
            judged.append(one)
            if one.level is Level.RED:
                incident = await self._incidents.raise_red(tenant, _red(one))
                incidents.append(incident)
                if channel is not None and corridor.role in channel.roles:
                    try:
                        await self._raising.execute(
                            self._red_report(tenant, corridor, one, incident, channel)
                        )
                        reported += 1
                    except ReportingError:
                        refused += 1
                        continue  # judged again at the next look
            self._seen[key] = newest
        return Looked(
            judged=tuple(judged),
            incidents=tuple(incidents),
            reported=reported,
            refused=refused,
        )

    def due(self) -> str | None:
        """The identifier of today's daily report once its hour has come; None before."""
        now = self._clock.now().astimezone(UTC)
        if now.time() < self._report_at:
            return None
        return rule.daily_id(now)

    async def daily(self, tenant: Tenant) -> Report | None:
        """Today's daily report, raised once from its hour; None before it, where it was
        raised already, where the tenant has no channel, or no corridor in force."""
        report_id = self.due()
        if report_id is None or await self._reports.one(tenant, report_id) is not None:
            return None
        channel = await self._channels.of(tenant)
        if channel is None:
            return None
        found = await self.judged(tenant)
        if not found:
            return None
        return await self._raising.execute(self._daily(tenant, report_id, channel, found))

    def _daily(
        self,
        tenant: Tenant,
        report_id: str,
        channel: OwnerChannel,
        found: Sequence[tuple[Corridor, Judged]],
    ) -> RaiseReport:
        now = self._clock.now()
        order = {Level.RED: 0, Level.YELLOW: 1, Level.UNMEASURED: 2}
        listed = sorted(
            ((c, j) for c, j in found if j.level is not Level.NORMAL),
            key=lambda cj: (order[cj[1].level], cj[0].signal),
        )
        deviating = sum(1 for _, j in listed if j.deviates)
        unmeasured = sum(1 for _, j in listed if j.level is Level.UNMEASURED)
        lines = [
            rule.line(c, j, run_url=None if j.run_id is None else run_url(channel, j.run_id))
            for c, j in listed
        ]
        if not deviating:
            lines.insert(0, rule.nothing_deviates(len(found) - unmeasured, unmeasured))
        book = channel.phrasebook
        starts: list[str] = []
        if book.intervene is not None:
            starts = sorted({p for c, _ in listed for p in c.interventions})
        offered = tuple(
            (rule.intervention_id(p), book.intervene.format(process=p), False)
            for p in starts
            if book.intervene is not None
        )
        steps = [
            "Open the case each line names: that is where a deviation is worked.",
        ]
        if offered:
            steps.append(
                "To intervene, answer in this thread with one of the offered starts; the "
                "reading is sent back, and the process starts only on your confirmation."
            )
        steps.append("Answer that it is done once you have read it.")
        reds = sum(1 for _, j in listed if j.level is Level.RED)
        standing = (
            f"{reds} red signals have open incidents; whatever they steer waits for a person."
            if reds
            else "Nothing stands still: a deviation waits for a person's look."
        )
        links = [(f"{c.signal}: case", c.case) for c, _ in listed]
        return RaiseReport(
            tenant=tenant,
            id=report_id,
            kind=ReportKind.SIGNALS,
            title=rule.daily_title(now, deviating, unmeasured),
            needed=lines,
            steps=steps,
            standing_still=(standing,),
            due=now.date(),
            offered=offered,
            links=links,
        )

    def _red_report(
        self,
        tenant: Tenant,
        corridor: Corridor,
        judged: Judged,
        incident: str,
        channel: OwnerChannel,
    ) -> RaiseReport:
        url = None if judged.run_id is None else run_url(channel, judged.run_id)
        links = [("Case", corridor.case)]
        if url is not None:
            links.append(("Run", url))
        return RaiseReport(
            tenant=tenant,
            id=rule.red_id(incident, judged),
            kind=ReportKind.FAILURE,
            title=f"The signal {corridor.signal} is red",
            needed=(rule.line(corridor, judged, run_url=url, incident=incident),),
            steps=(
                f"Work the case where it is worked: {corridor.case}",
                f"Close the incident with `taktusctl incident close {incident}` once it is "
                "worked; a further red value until then is recorded on it.",
            ),
            standing_still=(
                f"Incident {incident} is open. The daily report lists the signal until it is "
                "back within its corridor.",
            ),
            due=self._clock.now().date(),
            links=links,
        )


def _red(judged: Judged) -> RedSignal:
    """A red judgement names its run, its step, its time, its value and its threshold; the
    validation says so where one would not."""
    return RedSignal.model_validate(
        judged.model_dump(
            include={
                "signal",
                "corridor",
                "process_version",
                "run_id",
                "step_id",
                "at",
                "value",
                "median",
                "red_at",
            }
        )
    )
