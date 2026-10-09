"""The read side: the requests addressed to a decider, one request, the response times a reader
may see (ADR-0042, ADR-0015).

**Nothing waits silently.** The decider's list holds every request not yet applied whose role
the reader holds, the oldest due first, and says of each whether it is past its due date. The
run's own history carries the same request in its ledger entries and in the reason the run
waits.
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.decision.domain.model import RegisterEntry, Request
from taktus.components.decision.domain.service import response_times
from taktus.components.decision.ports import Deciders
from taktus.ports.clock import Clock
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


@dataclass(frozen=True)
class Addressed:
    request: Request
    overdue: bool


class DecisionQueries:
    def __init__(
        self,
        requests: Repository[Request],
        register: Repository[RegisterEntry],
        work: UnitOfWork,
        clock: Clock,
        deciders: Deciders,
    ) -> None:
        self._requests = requests
        self._register = register
        self._work = work
        self._clock = clock
        self._deciders = deciders

    async def addressed_to(self, tenant: Tenant, identity: str) -> list[Addressed]:
        """The requests not yet applied whose role the identity holds, oldest due first."""
        decider = await self._deciders.place(tenant, identity)
        if decider is None:
            return []
        async with self._work.transaction(tenant):
            requests = await self._requests.list(tenant)
        today = self._clock.now().date()
        waiting = [r for r in requests if r.open and r.decider in decider.roles]
        waiting.sort(key=lambda r: (r.request.due, r.raised_at))
        return [Addressed(r, r.overdue(today)) for r in waiting]

    async def one(self, tenant: Tenant, request_id: str) -> Addressed | None:
        async with self._work.transaction(tenant):
            request = await self._requests.get(tenant, request_id)
        if request is None:
            return None
        return Addressed(request, request.overdue(self._clock.now().date()))

    async def entries(self, tenant: Tenant) -> list[RegisterEntry]:
        """The tenant's decision register, oldest decision first."""
        async with self._work.transaction(tenant):
            entries = await self._register.list(tenant)
        return sorted(entries, key=lambda e: e.decided_at)

    async def response_times(self, tenant: Tenant, reader: str) -> response_times.ResponseTimes:
        """What `reader` may see: their own times, and aggregates by role and department over
        enough deciders. Nobody reads another person's times under that person's name."""
        entries = await self.entries(tenant)
        departments: dict[str, str | None] = {}
        for decided_by in {e.decided_by for e in entries}:
            placed = await self._deciders.place(tenant, decided_by)
            departments[decided_by] = None if placed is None else placed.department
        return response_times.read(reader, entries, lambda who: departments.get(who))
