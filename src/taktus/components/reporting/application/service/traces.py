"""The trace inside a step: read, shared with a role, kept for the tenant's retention and then
erased (ADR-0135, UC-6.14).

A trace is read only where its run is read: the run level's records answer whether there is
such a run and step, and the one predicate whether the reader may see it. A trace the reader
may not see is answered as one that does not exist.

The ledger records that a trace was shared, withdrawn, its retention set and lines erased —
by identifiers, the role as outcome, and nothing a line says.
"""

from __future__ import annotations

import re
from datetime import timedelta

from taktus.components.reporting.domain.model.levels import RunFacts, StepFacts
from taktus.components.reporting.domain.model.live import Reader, RunRef
from taktus.components.reporting.domain.model.trace import TraceEntry, TraceView
from taktus.components.reporting.domain.service import traces as tracing
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.ports.levels import LevelRecords
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.ports.traces import (
    LONGEST_RETENTION_DAYS,
    ROLE_PATTERN,
    TraceRetention,
    Traces,
)
from taktus.shared.v1 import LedgerRefs, Method

PAGE = 500
"""The most lines one read returns; a reader asks again after the last one."""

SHARED = "trace.shared"
UNSHARED = "trace.unshared"
RETENTION_CONFIGURED = "trace.retention_configured"
ERASED = "trace.erased"

FLIGHT = frozenset({"admitted", "running"})
"""The states of a step in which its worker reports: the run component's own names."""

TRACED = frozenset({Method.WORKER, Method.HUMAN})
"""The methods of a step that may hold a trace: a worker's, and a worker's step a person took
over and handed back, whose trace is what the worker did before (ADR-0128)."""


class BadRole(ValueError):
    """A share names no role: a role is a token such as `reviewer`."""


class StepTraces:
    def __init__(
        self,
        *,
        records: LevelRecords,
        traces: Traces,
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._records = records
        self._traces = traces
        self._work = work
        self._ledger = ledger
        self._clock = clock

    async def read(
        self, reader: Reader, run_id: str, step_id: str, *, after: int = 0
    ) -> TraceView | None:
        """The step's trace after the position `after`; None when there is no such step of a
        worker, or the reader may not see its trace."""
        found = await self._step(reader, run_id, step_id)
        if found is None:
            return None
        run, step, shared = found
        async with self._work.transaction(reader.tenant):
            lines = await self._traces.lines(
                reader.tenant, run_id, step_id, after=after, limit=PAGE
            )
        return TraceView(
            run_id=run.id,
            step_id=step.id,
            state=step.state,
            open=step.state in FLIGHT or len(lines) == PAGE,
            lines=tuple(
                TraceEntry(
                    position=line.position,
                    ts=line.ts,
                    type=line.type,
                    text=tracing.text_of(line),
                    detail=line.detail,
                )
                for line in lines
            ),
            after=lines[-1].position if lines else after,
            shared_with=tuple(shared),
            link=tracing.link(run_id, step_id),
        )

    async def share(self, reader: Reader, run_id: str, step_id: str, role: str) -> TraceView | None:
        """The trace shared with a role by a reader who may see it; None when they may not.
        `BadRole` for a role that is no role's name."""
        return await self._change(reader, run_id, step_id, role, share=True)

    async def unshare(
        self, reader: Reader, run_id: str, step_id: str, role: str
    ) -> TraceView | None:
        """A share withdrawn by a reader who may see the trace; None when they may not."""
        return await self._change(reader, run_id, step_id, role, share=False)

    async def retention(self, tenant: Tenant) -> TraceRetention:
        async with self._work.transaction(tenant):
            return await self._traces.retention(tenant)

    async def set_retention(self, tenant: Tenant, days: int, by: str) -> TraceRetention:
        """How long the tenant keeps a trace, set by `by`; a ledger entry beside it."""
        if not 1 <= days <= LONGEST_RETENTION_DAYS:
            raise ValueError(f"a retention is 1 to {LONGEST_RETENTION_DAYS} days, not {days}")
        retention = TraceRetention(days=days, configured_at=self._clock.now())
        async with self._work.transaction(tenant):
            await self._traces.set_retention(tenant, retention)
            await self._ledger.record(
                tenant,
                Fact(
                    kind=RETENTION_CONFIGURED,
                    refs=LedgerRefs(tenant=tenant, actor=by),
                    outcome="configured",
                ),
            )
        return retention

    async def erase(self, tenant: Tenant) -> int:
        """Every line whose retention ended, erased; how many. An erasure is a ledger entry."""
        async with self._work.transaction(tenant):
            retention = await self._traces.retention(tenant)
            before = self._clock.now() - timedelta(days=retention.days)
            erased = await self._traces.erase(tenant, before)
            if erased:
                await self._ledger.record(
                    tenant,
                    Fact(
                        kind=ERASED,
                        refs=LedgerRefs(tenant=tenant),
                        outcome="retention",
                    ),
                )
        return erased

    async def _change(
        self, reader: Reader, run_id: str, step_id: str, role: str, *, share: bool
    ) -> TraceView | None:
        if not re.fullmatch(ROLE_PATTERN, role):
            raise BadRole(f"{role!r} is no role: a role is a lowercase token such as reviewer")
        if await self._step(reader, run_id, step_id) is None:
            return None
        async with self._work.transaction(reader.tenant):
            changed = (
                await self._traces.share(reader.tenant, run_id, step_id, role)
                if share
                else await self._traces.unshare(reader.tenant, run_id, step_id, role)
            )
            if changed:
                await self._ledger.record(
                    reader.tenant,
                    Fact(
                        kind=SHARED if share else UNSHARED,
                        refs=LedgerRefs(
                            tenant=reader.tenant,
                            run_id=run_id,
                            step_id=step_id,
                            actor=reader.identity,
                        ),
                        outcome=role,
                    ),
                )
        return await self.read(reader, run_id, step_id)

    async def _step(
        self, reader: Reader, run_id: str, step_id: str
    ) -> tuple[RunFacts, StepFacts, list[str]] | None:
        run = await self._records.run(reader.tenant, run_id)
        if run is None:
            return None
        step = next((s for s in run.steps if s.id == step_id), None)
        if step is None or step.method not in TRACED:
            return None
        async with self._work.transaction(reader.tenant):
            shared = list(await self._traces.shared_with(reader.tenant, run_id, step_id))
        ref = RunRef(id=run.id, tenant=run.tenant, process_version=run.process_version)
        if not visibility.may_see_trace(reader, ref, shared):
            return None
        return run, step, shared
