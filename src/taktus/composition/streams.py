"""The organisation seen as value streams, gathered for the reporting component's view
(UC-15.6, ADR-0159 §4 to §6).

The facts come from four components that never import each other: the process component's
value streams and active versions, the run component's runs and blocks, and the identity
component's roles and where in the structure their holders sit. This module gathers them and
hands them to `reporting/domain/service/streams.py`, which draws the map and the swimlanes and
stores nothing. A declaration is the process component's own act.

Every read takes `visible`, the processes the reader may see (ADR-0055 §5): a process outside
it is left out of every stream, every figure and every count. Only the runs that finished in the
window are read, newest first, and the reading stops at the first one older: it costs what it
returns (ADR-0094). A rehearsal is no run of the work, and is left out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta

from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.application.service.streams import DeclareStream, ValueStreams
from taktus.components.process.domain.model import Process, ProcessVersion, ValueStream
from taktus.components.reporting.domain.service import streams as views
from taktus.components.run.application.query.blocked_time import BlockedTime
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.clock import Clock
from taktus.ports.persistence import Mark, Queried, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Method

PAGE = 200
"""The runs read at a time, newest first, until one is older than the window."""


class StreamReads:
    def __init__(
        self,
        *,
        streams: ValueStreams,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        runs: Queried[Run],
        blocked: BlockedTime,
        identities: IdentityDirectory,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._streams = streams
        self._processes = processes
        self._versions = versions
        self._runs = runs
        self._blocked = blocked
        self._identities = identities
        self._work = work
        self._clock = clock

    async def declare(self, command: DeclareStream) -> ValueStream:
        """The process component's declaration (`ValueStreams.declare`)."""
        return await self._streams.declare(command)

    async def map(self, tenant: Tenant, visible: frozenset[str], days: int) -> views.StreamMap:
        streams = [_facts(s, visible) for s in await self._streams.current(tenant)]
        processes = await self._processes_of(tenant, visible, days)
        return views.stream_map(streams, processes, await self._roles(tenant), days)

    async def lanes(
        self, tenant: Tenant, stream: str, visible: frozenset[str], days: int
    ) -> views.StreamLanes | None:
        """None where the tenant declared no such stream."""
        found = next((s for s in await self._streams.current(tenant) if s.stream == stream), None)
        if found is None:
            return None
        processes = await self._processes_of(tenant, visible, days)
        return views.stream_lanes(_facts(found, visible), processes, await self._roles(tenant))

    async def _roles(self, tenant: Tenant) -> dict[str, views.RoleFacts]:
        holders = await self._identities.role_holders(tenant)
        units = await self._identities.role_units(tenant)
        return {
            role: views.RoleFacts(holders=count, units=units.get(role, ()))
            for role, count in holders.items()
        }

    async def _processes_of(
        self, tenant: Tenant, visible: frozenset[str], days: int
    ) -> list[views.ProcessFacts]:
        async with self._work.transaction(tenant):
            processes = [p for p in await self._processes.list(tenant) if p.id in visible]
            versions = {
                p.id: await self._versions.get(tenant, f"{p.id}@{p.active_version}")
                for p in processes
                if p.active_version is not None
            }
        runs = await self._finished(tenant, visible, days)
        blocks = await self._blocked.blocks(tenant)
        held: dict[str, dict[str, float]] = {}
        waits: dict[str, dict[str, float]] = {}
        for block in blocks:
            per_run = held.setdefault(block.run_id, {})
            per_run[str(block.account)] = per_run.get(str(block.account), 0.0) + block.seconds
            if str(block.account) == "wait.human" and block.role is not None:
                per_role = waits.setdefault(block.process, {})
                per_role[block.role] = per_role.get(block.role, 0.0) + block.seconds
        facts: list[views.ProcessFacts] = []
        for process in sorted(processes, key=lambda p: p.id):
            version = versions.get(process.id)
            facts.append(
                views.ProcessFacts(
                    process=process.id,
                    name=process.name,
                    version=None if version is None else version.ref,
                    level=None if version is None else version.autonomy_level,
                    steps=() if version is None else tuple(_steps(version)),
                    runs=tuple(
                        views.RunFacts(
                            lead_seconds=(run.updated_at - run.created_at).total_seconds(),
                            blocked=held.get(run.id, {}),
                        )
                        for run in runs.get(process.id, ())
                    ),
                    waits=waits.get(process.id, {}),
                )
            )
        return facts

    async def _finished(
        self, tenant: Tenant, visible: frozenset[str], days: int
    ) -> Mapping[str, Sequence[Run]]:
        since = self._clock.now() - timedelta(days=days)
        found: dict[str, list[Run]] = {}
        after: Mark | None = None
        while True:
            async with self._work.transaction(tenant):
                page = await self._runs.newest(tenant, limit=PAGE, after=after)
            for run in page:
                if run.created_at < since:
                    return found
                process = run.process_version.split("@", 1)[0]
                if run.state is RunState.FINISHED and not run.rehearsal and process in visible:
                    found.setdefault(process, []).append(run)
            if len(page) < PAGE:
                return found
            last = page[-1]
            after = Mark(created_at=last.created_at, id=last.id)


def _facts(stream: ValueStream, visible: frozenset[str]) -> views.StreamFacts:
    return views.StreamFacts(
        stream=stream.stream,
        revision=stream.revision,
        name=stream.name,
        kind=stream.kind.value,
        trigger=stream.trigger,
        outcome=stream.outcome,
        role=stream.role,
        processes=tuple(p for p in stream.processes if p in visible),
    )


def _steps(version: ProcessVersion) -> list[views.StepFacts]:
    found: list[views.StepFacts] = []
    for step in version.ordered():
        human = step.method is Method.HUMAN
        fallback = step.fallback
        found.append(
            views.StepFacts(
                id=step.id,
                method=step.method.value,
                exactness=None if step.exactness is None else step.exactness.value,
                role=(step.role or views.OWNER) if human else None,
                fallback_role=None
                if fallback is None or fallback.to is not Method.HUMAN
                else (fallback.role or views.OWNER),
            )
        )
    return found
