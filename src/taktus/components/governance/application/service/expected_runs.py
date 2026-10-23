"""Use cases of the watch over expected runs (ADR-0107, UC-4.16): the watch itself, an
incident closed by a person, the tenant's configuration, and what is open.

The watch reads the tenant's ledger without reading the chain (`LedgerStore.of_process`,
`latest_of_process`), applies the rule of `domain/service/expected_runs.py`, and writes what
the rule found: an incident raised, a further miss or a late run recorded on one, a crossing of
the empty share. Each write is the incident and its ledger entry in one transaction.

What was expected comes from the process component, through the composition root: this
component never reads a process (`composition/expected_runs.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from taktus.components.governance.domain.model.incident import (
    Incident,
    IncidentKind,
    IncidentState,
    WatchConfiguration,
    incident_id,
    shipped_watch,
)
from taktus.components.governance.domain.service.expected_runs import (
    BEATS,
    COURSE,
    ENDS,
    OVERRUN_HORIZON,
    EmptyShare,
    Miss,
    Watched,
    empty_share,
    missed_gap,
    missed_slots,
    overruns,
    seen,
)
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import LedgerStore, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry, LedgerRefs

RAISED = "incident.raised"
RECORDED = "incident.recorded"
CLOSED = "incident.closed"
EMPTY_SHARE = "watch.empty_share"
EXCEEDED = "exceeded"
BACK = "ok"
INSTANT = timedelta(microseconds=1)


@dataclass(frozen=True)
class Watch:
    """What one look at a tenant found and wrote."""

    raised: tuple[Incident, ...] = ()
    recorded: tuple[str, ...] = ()
    """The incidents a further miss or a late run was recorded on, by identifier."""
    blind: tuple[EmptyShare, ...] = ()
    """Every process whose share of empty ends is exceeded now."""
    crossed: tuple[EmptyShare, ...] = field(default=())
    """Of the processes counted, those whose share crossed into or out of exceeded at this look."""


@dataclass(frozen=True)
class CloseIncident:
    tenant: Tenant
    incident_id: str
    by: str
    """The identity that closes it: the actor of `incident.closed`, never a field of it."""


@dataclass(frozen=True)
class ConfigureWatch:
    """What a tenant sets of its watch; what it leaves out stays. Who sets it is the actor of
    the ledger entry, given beside it (`ExpectedRuns.configure`), never a field beside these
    figures (principle 14)."""

    tenant: Tenant
    grace: timedelta | None = None
    empty_share: float | None = None
    empty_window: timedelta | None = None
    empty_minimum: int | None = None
    repeated_calls: int | None = None
    repeated_model_calls: int | None = None
    evaluation_tolerance: float | None = None
    evaluation_subjects: bool | None = None


class UnknownIncident(LookupError):
    def __init__(self, tenant: str, incident: str) -> None:
        super().__init__(f"tenant {tenant!r} has no incident {incident!r}")


class ExpectedRuns:
    def __init__(
        self,
        incidents: Repository[Incident],
        configurations: Repository[WatchConfiguration],
        ledger_store: LedgerStore,
        ledger: Ledger,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._incidents = incidents
        self._configurations = configurations
        self._store = ledger_store
        self._ledger = ledger
        self._work = work
        self._clock = clock

    async def configuration(self, tenant: Tenant) -> WatchConfiguration:
        """The tenant's configuration, or the shipped default where it configured none."""
        async with self._work.transaction(tenant):
            found = await self._configurations.get(tenant, tenant)
        return found or shipped_watch(tenant)

    async def configure(self, command: ConfigureWatch, *, by: str) -> WatchConfiguration:
        """Set what the command names, keep the rest. A configuration that does not hold is
        refused as a ValueError and changes nothing."""
        current = await self.configuration(command.tenant)
        changes = {
            name: value
            for name, value in (
                ("grace", command.grace),
                ("empty_share", command.empty_share),
                ("empty_window", command.empty_window),
                ("empty_minimum", command.empty_minimum),
                ("repeated_calls", command.repeated_calls),
                ("repeated_model_calls", command.repeated_model_calls),
                ("evaluation_tolerance", command.evaluation_tolerance),
                ("evaluation_subjects", command.evaluation_subjects),
            )
            if value is not None
        }
        configured = WatchConfiguration.model_validate(
            {**current.model_dump(), **changes, "configured_at": self._clock.now()}
        )
        async with self._work.transaction(command.tenant):
            await self._configurations.put(command.tenant, configured)
            await self._ledger.record(
                command.tenant,
                Fact(
                    kind="watch.configured",
                    refs=LedgerRefs(tenant=command.tenant, actor=by),
                    outcome="configured",
                ),
            )
        return configured

    async def incidents(self, tenant: Tenant, *, every: bool = False) -> list[Incident]:
        """The open incidents, newest first; with `every`, the closed ones too."""
        async with self._work.transaction(tenant):
            found = list(await self._incidents.list(tenant))
        found.sort(key=lambda i: (i.raised_at, i.id), reverse=True)
        return [i for i in found if every or i.state is IncidentState.OPEN]

    async def blind(self, tenant: Tenant) -> list[str]:
        """The process versions whose share of empty ends is exceeded now, as the newest
        crossing of each process says (ADR-0107 §5)."""
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, (EMPTY_SHARE,))
        newest: dict[str, LedgerEntry] = {}
        for entry in entries:
            version = entry.refs.process_version
            if entry.kind == EMPTY_SHARE and version is not None:
                newest[version.split("@", 1)[0]] = entry
        return sorted(
            e.refs.process_version or "" for e in newest.values() if e.outcome == EXCEEDED
        )

    async def close(self, command: CloseIncident) -> Incident:
        """A person closes the incident. One closed already stays as it is."""
        tenant = command.tenant
        async with self._work.transaction(tenant):
            incident = await self._incidents.get(tenant, command.incident_id)
            if incident is None:
                raise UnknownIncident(tenant, command.incident_id)
            if incident.state is IncidentState.CLOSED:
                return incident
            closed = incident.closed(self._clock.now())
            await self._incidents.put(tenant, closed)
            await self._entry(tenant, closed, CLOSED, "closed", actor=command.by)
        return closed

    async def watch(
        self, tenant: Tenant, watched: Sequence[Watched], configuration: WatchConfiguration
    ) -> Watch:
        """One look at the tenant's processes (ADR-0107 §3 to §5)."""
        now = self._clock.now()
        grace = configuration.grace
        raised: list[Incident] = []
        recorded: list[str] = []
        blind: list[EmptyShare] = []
        crossed: list[EmptyShare] = []
        for process in watched:
            async with self._work.transaction(tenant):
                misses = await self._misses(tenant, process, grace, now)
                ends = await self._store.of_process(
                    tenant, process.process_id, ENDS, since=now - configuration.empty_window
                )
                last = await self._store.latest_of_process(
                    tenant, process.process_id, BEATS, at_or_before=now
                )
                prior = await self._store.latest_of_process(
                    tenant, process.process_id, (EMPTY_SHARE,), at_or_before=now
                )
            for miss in misses:
                done = await self._raise(tenant, process, miss, now)
                if isinstance(done, Incident):
                    raised.append(done)
                elif done is not None:
                    recorded.append(done)
            if last is not None:
                recorded.extend(await self._late(tenant, process, seen_entry=last, now=now))
            share = empty_share(
                process, ends, configuration.empty_share, configuration.empty_minimum
            )
            if share.exceeded:
                blind.append(share)
            was = prior is not None and prior.outcome == EXCEEDED
            if share.exceeded != was:
                await self._crossing(tenant, process, share)
                crossed.append(share)
        return Watch(
            raised=tuple(raised),
            recorded=tuple(recorded),
            blind=tuple(blind),
            crossed=tuple(crossed),
        )

    async def _misses(
        self, tenant: Tenant, process: Watched, grace: timedelta, now: datetime
    ) -> list[Miss]:
        found: list[Miss] = []
        if process.slots:
            earliest = min(slot.at for slot in process.slots)
            beats = await self._store.of_process(tenant, process.process_id, BEATS, since=earliest)
            before = {
                slot.at: await self._store.latest_of_process(
                    tenant, process.process_id, BEATS, at_or_before=slot.at - INSTANT
                )
                for slot in process.slots
            }
            found.extend(missed_slots(process, grace, beats, before))
        if process.gap is not None:
            last = await self._store.latest_of_process(
                tenant, process.process_id, BEATS, at_or_before=now
            )
            gap = missed_gap(process, grace, last, now)
            if gap is not None:
                found.append(gap)
        if process.bound is not None:
            course = await self._store.of_process(
                tenant,
                process.process_id,
                COURSE,
                since=now - process.bound - grace - OVERRUN_HORIZON,
            )
            found.extend(overruns(process, grace, course, now))
        return found

    async def _raise(
        self, tenant: Tenant, process: Watched, miss: Miss, now: datetime
    ) -> Incident | str | None:
        """A new incident; or the identifier of the open one a further miss was recorded on;
        or None when the miss is known already."""
        overdue = miss.run_id is not None
        kind = IncidentKind.OVERDUE if overdue else IncidentKind.MISSING
        key = (
            miss.run_id
            if overdue and miss.run_id
            else f"{miss.rule}:{miss.expected_at.isoformat()}"
        )
        iid = incident_id(tenant, kind, process.process_id, key)
        async with self._work.transaction(tenant):
            if await self._incidents.get(tenant, iid) is not None:
                return None
            if not overdue:
                theirs = [
                    i
                    for i in await self._incidents.list(tenant)
                    if i.kind is IncidentKind.MISSING and i.process_id == process.process_id
                ]
                if any(miss.expected_at in i.missed for i in theirs):
                    return None  # recorded on an incident already, open or closed
                still_open = [i for i in theirs if i.state is IncidentState.OPEN]
                if still_open:
                    target = max(still_open, key=lambda i: i.raised_at)
                    again = target.missed_again(miss.expected_at, miss.deadline, now)
                    await self._incidents.put(tenant, again)
                    await self._entry(tenant, again, RECORDED, "missed")
                    return again.id
            incident = Incident(
                id=iid,
                tenant=tenant,
                kind=kind,
                process_id=process.process_id,
                process_version=process.process_version,
                expected_at=miss.expected_at,
                last_run=miss.last_run,
                run_id=miss.run_id,
                rule=miss.rule,
                facts=dict(miss.facts),
                raised_at=now,
            )
            if not overdue:
                incident = incident.missed_again(miss.expected_at, miss.deadline, now)
            await self._incidents.put(tenant, incident)
            await self._entry(tenant, incident, RAISED, "overdue" if overdue else "missed")
        return incident

    async def _late(
        self, tenant: Tenant, process: Watched, *, seen_entry: LedgerEntry, now: datetime
    ) -> list[str]:
        """Record, on every open missing-run incident of the process, a run that happened after
        its newest miss. It closes nothing (ADR-0107 §4)."""
        recorded: list[str] = []
        async with self._work.transaction(tenant):
            for incident in await self._incidents.list(tenant):
                if (
                    incident.kind is not IncidentKind.MISSING
                    or incident.process_id != process.process_id
                    or incident.state is not IncidentState.OPEN
                ):
                    continue
                deadline = incident.waits_for_a_run
                if deadline is None or seen_entry.ts <= deadline:
                    continue
                late = incident.happened(seen(seen_entry), now)
                await self._incidents.put(tenant, late)
                await self._entry(tenant, late, RECORDED, "happened", run_id=seen_entry.refs.run_id)
                recorded.append(late.id)
        return recorded

    async def _crossing(self, tenant: Tenant, process: Watched, share: EmptyShare) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=EMPTY_SHARE,
                    refs=LedgerRefs(tenant=tenant, process_version=process.process_version),
                    outcome=EXCEEDED if share.exceeded else BACK,
                ),
            )

    async def _entry(
        self,
        tenant: Tenant,
        incident: Incident,
        kind: str,
        outcome: str,
        *,
        actor: str | None = None,
        run_id: str | None = None,
    ) -> None:
        about = run_id or incident.run_id
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=tenant,
                    process_version=incident.process_version,
                    incident_id=incident.id,
                    run_id=about,
                    actor=actor,
                ),
                outcome=outcome,
            ),
        )
