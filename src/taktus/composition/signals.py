"""Signals against their corridors, wired (ADR-0109, UC-6.13): what a step recorded, read for
the reporting component; a red value handed to the governance component; an intervention started
as a command; and the scheduler's tick.

The components never import each other; this is where they meet.

- `RecordedMeasurements` reads one step's `step.finished` entries of one process from the ledger
  store without reading the chain, a rehearsal's left out (ADR-0107). For each it reads the
  result from the object store by the entry's digest, and the step run's provenance record.
- `DeclaredSteps` reads the method and exactness the process's active version declares.
- `GovernanceIncidents` raises the incident of a red value through `SignalIncidents`.
- `CommandInterventions` starts a process for a person: a command, commissioned as a plan of
  the active version and submitted as a run, as a change in dialogue is (`proposals.py`).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog

from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.governance.application.service import RaiseRed, SignalIncidents
from taktus.components.governance.domain.model import Incident
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.application.service import Corridors, SignalWatch
from taktus.components.reporting.domain.model import Corridor, Recorded
from taktus.components.reporting.ports import (
    Declared,
    InterventionRefused,
    RedSignal,
)
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.composition.owner_channel import OwnerChannelWiring
from taktus.composition.tenancy import this_round
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver, ServedTenants
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import (
    LedgerStore,
    ProvenanceStore,
    Repository,
    Tenant,
    UnitOfWork,
)
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, Provenance, ReplyTo, StepId

INTERVAL_SECONDS = 60
"""How often the scheduler looks: a red value reaches its role within a minute of being
recorded, and a look reads one entry per corridor while nothing new was measured."""

MEASURED = "step.finished"
SUCCEEDED = frozenset({"succeeded", "skipped", "declined"})
"""The outcomes of a step that ended with a result; a skipped or declined one holds no number."""
FAILED = "failed"

log = structlog.get_logger("taktusd")


class RecordedMeasurements:
    def __init__(
        self,
        ledger_store: LedgerStore,
        objects: ObjectStore,
        provenance: ProvenanceStore,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._clock = clock
        self._store = ledger_store
        self._objects = objects
        self._provenance = provenance
        self._work = work

    async def newest(self, tenant: Tenant, process: str) -> int | None:
        async with self._work.transaction(tenant):
            entry = await self._store.latest_of_process(
                tenant, process, (MEASURED,), at_or_before=self._clock.now()
            )
        return None if entry is None else entry.seq

    async def recorded(
        self, tenant: Tenant, process: str, step: StepId, *, since: datetime
    ) -> Sequence[Recorded]:
        records: dict[str, dict[str, Provenance]] = {}
        found: list[Recorded] = []
        async with self._work.transaction(tenant):
            entries = await self._store.of_process(tenant, process, (MEASURED,), since=since)
            for entry in entries:
                run_id = entry.refs.run_id
                version = entry.refs.process_version
                if entry.refs.step_id != step or run_id is None or version is None:
                    continue
                if entry.outcome not in SUCCEEDED and entry.outcome != FAILED:
                    continue  # stopped at its boundary, or waiting: it has not ended
                if run_id not in records:
                    records[run_id] = {
                        r.step_id: r for r in await self._provenance.of_run(tenant, run_id)
                    }
                record = records[run_id].get(step)
                result: Any = None
                if entry.outcome in SUCCEEDED and entry.content_digest is not None:
                    content = await self._objects.get(entry.content_digest)
                    result = _parsed(content)
                found.append(
                    Recorded(
                        run_id=run_id,
                        step_id=step,
                        process_version=version,
                        seq=entry.seq,
                        at=entry.ts,
                        succeeded=entry.outcome in SUCCEEDED,
                        method=None if record is None else record.method,
                        exactness=None if record is None else record.exactness,
                        provenance=record is not None,
                        result=result,
                    )
                )
        return found


def _parsed(content: bytes | None) -> Any:
    if content is None:
        return None
    try:
        return json.loads(content)
    except ValueError:
        return None


class DeclaredSteps:
    def __init__(
        self,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._work = work

    async def declared(self, tenant: Tenant, process: str, step: StepId) -> Declared | None:
        async with self._work.transaction(tenant):
            found = await self._processes.get(tenant, process)
            if found is None or found.active_version is None:
                return None
            version = await self._versions.get(tenant, f"{process}@{found.active_version}")
        if version is None:
            return None
        for one in version.steps:
            if one.id == step:
                return Declared(method=one.method, exactness=one.exactness)
        return None


class GovernanceIncidents:
    def __init__(self, incidents: SignalIncidents) -> None:
        self._incidents = incidents

    async def raise_red(self, tenant: Tenant, red: RedSignal) -> str:
        incident = await self._incidents.raise_red(
            RaiseRed(
                tenant=tenant,
                signal=red.signal,
                corridor=red.corridor,
                process_version=red.process_version,
                run_id=red.run_id,
                step_id=red.step_id,
                at=red.at,
                value=red.value,
                median=red.median,
                red_at=red.red_at,
            )
        )
        return incident.id


class CommandInterventions:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._work = work
        self._clock = clock
        self._ids = ids

    async def start(
        self, tenant: Tenant, process: str, *, by: str, report: str, channel: str, address: str
    ) -> str:
        async with self._work.transaction(tenant):
            found = await self._processes.get(tenant, process)
            version = (
                None
                if found is None or found.active_version is None
                else await self._versions.get(tenant, f"{process}@{found.active_version}")
            )
        if version is None:
            raise InterventionRefused(f"{process} has no active version in {tenant}")
        if version.limits is None:
            raise InterventionRefused(f"{version.ref} declares no limits to run under")
        if any(i.required for i in version.inputs.values()):
            raise InterventionRefused(f"{version.ref} needs inputs a reply does not give")
        placed = await self._identities.identity(tenant, by)
        if placed is None:
            raise InterventionRefused(f"{by!r} is not known to {tenant}")
        command = Command(
            id=self._ids.new("cmd"),
            channel=channel,
            identity=placed.identity,
            org_path=placed.org_path,
            intent=Intent(raw=f"start {process}", recognised="signal.intervention"),
            context={"report": report},
            reply_to=ReplyTo(channel=channel, address=address),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=f"intervene with {process}",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        run = await self._engine.submit(
            StartRun(
                org_unit=command.org_unit,
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits)),
                process_version=version.ref,
                actor=placed.identity,
                tenant=tenant,
                actions=version.autonomy.action_levels,
            )
        )
        return run.id


def signals_tick(
    watch: SignalWatch,
    tenants: ServedTenants,
    clock: Clock,
    *,
    interval_seconds: int = INTERVAL_SECONDS,
) -> Callable[[], Awaitable[None]]:
    """What the scheduler calls on every tick: once the interval has passed since the last look
    — the first tick looks at once — every tenant's signals are judged, and its daily report is
    raised once its hour has come. A look that fails is logged and made again at the next
    interval: judging never stops the scheduler."""
    last: list[datetime] = []

    async def tick() -> None:
        now = clock.now()
        if last and now - last[0] < timedelta(seconds=interval_seconds):
            return
        last[:] = [now]
        for tenant in await this_round(tenants, "scheduler"):
            try:
                looked = await watch.look(tenant)
                daily = await watch.daily(tenant)
            except Exception as error:  # a look must never take the scheduler down
                log.error(
                    "signals not judged; the next look tries again",
                    tenant=tenant,
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for incident in looked.incidents:
                log.error("a signal is red: incident raised", tenant=tenant, incident=incident)
            if daily is not None:
                log.info("the daily report of signals is raised", tenant=tenant, report=daily.id)

    return tick


@dataclass(frozen=True)
class SignalWiring:
    """Everything an entry point needs of the signals, built once."""

    corridors: Corridors
    watch: SignalWatch


def signal_wiring(
    of: Callable[[Any], Any],
    *,
    ledger_store: LedgerStore,
    ledger: Ledger,
    objects: ObjectStore,
    provenance: ProvenanceStore,
    work: UnitOfWork,
    clock: Clock,
    identities: IdentityResolver,
    owner: OwnerChannelWiring,
) -> SignalWiring:
    """The corridors and the watch over them. `of` gives the repository of an aggregate, as
    the entry point stores it."""
    corridors = Corridors(
        of(Corridor),
        work,
        ledger,
        clock,
        identities,
        DeclaredSteps(of(Process), of(ProcessVersion), work),
        owner.channel,
    )
    watch = SignalWatch(
        corridors,
        RecordedMeasurements(ledger_store, objects, provenance, work, clock),
        GovernanceIncidents(SignalIncidents(of(Incident), ledger, work, clock)),
        owner.channel,
        owner.queries,
        owner.raising,
        clock,
    )
    return SignalWiring(corridors=corridors, watch=watch)
