"""A role's profile, gathered for the reporting component's view (UC-15.7, ADR-0167 §3 to §5).

The facts come from six components that never import each other: the process component's
active versions and value streams, the governance component's anchors, the decision
component's open requests, the run component's runs and blocks, and the identity component's
roles. This module gathers them and hands them to `reporting/domain/service/profiles.py`, which
derives the profile and stores nothing.

Every read takes `visible`, the processes the reader may see (ADR-0055 §5): a process outside it
contributes no step, no wait and no run. Only the runs created in the window are read, newest
first, and the reading stops at the first one older (ADR-0094). A rehearsal is no run of the
work, and is left out.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from taktus.components.decision.domain.model import Request
from taktus.components.governance.application.service import AnchorsInForce
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.application.service.streams import ValueStreams
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.service import profiles as views
from taktus.components.run.application.query.blocked_time import BlockedTime
from taktus.components.run.domain.model import Run, StepState
from taktus.ports.clock import Clock
from taktus.ports.persistence import Mark, Queried, Repository, Tenant, UnitOfWork
from taktus.shared.v1 import Method

PAGE = 200
"""The runs read at a time, newest first, until one is older than the window."""


class RoleProfiles:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        streams: ValueStreams,
        anchors: AnchorsInForce,
        requests: Repository[Request],
        runs: Queried[Run],
        blocked: BlockedTime,
        identities: IdentityDirectory,
        work: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._streams = streams
        self._anchors = anchors
        self._requests = requests
        self._runs = runs
        self._blocked = blocked
        self._identities = identities
        self._work = work
        self._clock = clock

    async def index(
        self, tenant: Tenant, reader: str, held: frozenset[str], visible: frozenset[str], days: int
    ) -> views.RoleIndex:
        return views.index(await self._facts(tenant, reader, held, visible, days))

    async def profile(
        self,
        tenant: Tenant,
        role: str,
        reader: str,
        held: frozenset[str],
        visible: frozenset[str],
        days: int,
    ) -> views.RoleProfile | None:
        """None where neither the structure nor the processes know the role."""
        facts = await self._facts(tenant, reader, held, visible, days)
        if role not in views.roles(facts):
            return None
        return views.profile(facts, role)

    async def _facts(
        self, tenant: Tenant, reader: str, held: frozenset[str], visible: frozenset[str], days: int
    ) -> views.Facts:
        async with self._work.transaction(tenant):
            processes = [p for p in await self._processes.list(tenant) if p.id in visible]
            versions = [
                v
                for p in sorted(processes, key=lambda p: p.id)
                if p.active_version is not None
                and (v := await self._versions.get(tenant, f"{p.id}@{p.active_version}"))
                is not None
            ]
            requests = [r for r in await self._requests.list(tenant) if r.open]
        streams = await self._streams.current(tenant)
        anchors = (await self._anchors.of(tenant)).anchors
        ended = [
            b
            for b in await self._blocked.blocks(tenant)
            if str(b.account) == "wait.human" and b.process in visible
        ]
        since = self._clock.now() - timedelta(days=days)
        ended = [b for b in ended if b.until >= since]
        open_now = [
            w
            for w in await self._blocked.waiting(tenant)
            if str(w.account) == "wait.human" and w.process_version.split("@", 1)[0] in visible
        ]
        own: dict[str, float] = dict.fromkeys(held, 0.0)
        for block in await self._blocked.own(tenant, reader):
            role = block.role or views.OWNER
            if role in held and block.until >= since and block.process in visible:
                own[role] = own.get(role, 0.0) + block.seconds
        return views.Facts(
            processes=tuple(_process(v) for v in versions),
            streams=tuple(
                views.StreamFacts(
                    stream=s.stream,
                    name=s.name,
                    role=s.role,
                    processes=tuple(p for p in s.processes if p in visible),
                )
                for s in streams
            ),
            anchors=tuple(
                views.AnchorFacts(id=a.id, class_=str(a.class_), act=a.act, decider=a.decider.role)
                for a in anchors
            ),
            requests=tuple(
                views.RequestFacts(decider=r.decider, due=r.request.due) for r in requests
            ),
            waits=tuple(
                views.WaitFacts(process=b.process, step=b.step_id, role=b.role, seconds=b.seconds)
                for b in ended
            ),
            open_waits=tuple(
                views.OpenWaitFacts(
                    process=w.process_version.split("@", 1)[0], step=w.step_id, role=w.role
                )
                for w in open_now
            ),
            ran=await self._ran(tenant, visible, since),
            holders=await self._identities.role_holders(tenant),
            units=await self._identities.role_units(tenant),
            own=own,
            days=days,
        )

    async def _ran(
        self, tenant: Tenant, visible: frozenset[str], since: datetime
    ) -> tuple[views.Ran, ...]:
        counted: dict[tuple[str, str], list[int]] = {}
        after: Mark | None = None
        while True:
            async with self._work.transaction(tenant):
                page = await self._runs.newest(tenant, limit=PAGE, after=after)
            for run in page:
                if run.created_at < since:
                    return _counted(counted)
                process = run.process_version.split("@", 1)[0]
                if run.rehearsal or process not in visible:
                    continue
                for step_run in run.step_runs:
                    if step_run.state is not StepState.SUCCEEDED:
                        continue
                    tally = counted.setdefault((process, step_run.step_id), [0, 0])
                    tally[1 if step_run.method is Method.HUMAN else 0] += 1
            if len(page) < PAGE:
                return _counted(counted)
            last = page[-1]
            after = Mark(created_at=last.created_at, id=last.id)


def _counted(counted: Mapping[tuple[str, str], list[int]]) -> tuple[views.Ran, ...]:
    return tuple(
        views.Ran(process=p, step=s, automatic=t, manual=h)
        for (p, s), (t, h) in sorted(counted.items())
    )


def _process(version: ProcessVersion) -> views.ProcessFacts:
    steps = []
    for step in version.ordered():
        work = version.work.get(step.id) or {}
        fallback = step.fallback
        human_fallback = fallback is not None and fallback.to is Method.HUMAN
        task = work.get("task") if step.method is Method.HUMAN else None
        ask = work.get("ask")
        steps.append(
            views.StepFacts(
                id=step.id,
                method=step.method.value,
                reason=step.reason,
                role=step.role,
                expertise=tuple(step.expertise or ()),
                task=task if isinstance(task, str) and task else None,
                fallback_human=human_fallback,
                fallback_when=fallback.when if fallback is not None and human_fallback else None,
                fallback_role=fallback.role if fallback is not None and human_fallback else None,
                fallback_expertise=tuple(fallback.expertise or ())
                if fallback is not None and human_fallback
                else (),
                checks=tuple(
                    views.CheckFacts(kind=str(c.kind), role=c.role) for c in step.checks or ()
                ),
                ask_role=(
                    str(ask.get("role") or views.OWNER) if isinstance(ask, Mapping) else None
                ),
            )
        )
    return views.ProcessFacts(process=version.process_id, version=version.ref, steps=tuple(steps))
