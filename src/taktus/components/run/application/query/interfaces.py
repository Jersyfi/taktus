"""Failed calls through an interface, read (ADR-0047): what a broken interface is noticed from.

Every `interface.failed` entry of the tenant's ledger, oldest first: the adapter the call went
through, the cause token, the run and the step, and when. Read from the ledger and from nothing
else. A rehearsal's entries are left out: a rehearsal runs on a configuration altered on purpose,
such as the removal test's, and what it meets is not the work's (ADR-0030).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from taktus.components.run.domain.service.interfaces import RECORD_KIND
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import Value


class FailedCall(Value):
    """One failed call that speaks about its interface, as the ledger entry records it."""

    seq: int = Field(ge=1)
    """The entry's place in the tenant's chain: what orders two calls at the same moment."""
    at: datetime
    adapter: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)


class InterfaceFailures:
    def __init__(self, ledger: Ledger, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._work = work

    async def failures(self, tenant: Tenant) -> tuple[FailedCall, ...]:
        async with self._work.transaction(tenant):
            entries = await self._ledger.entries(tenant)
        return tuple(
            FailedCall(
                seq=entry.seq,
                at=entry.ts,
                adapter=entry.adapter,
                cause=entry.outcome,
                run_id=entry.refs.run_id,
                step_id=entry.refs.step_id,
            )
            for entry in entries
            if entry.kind == RECORD_KIND
            and not entry.rehearsal
            and entry.adapter is not None
            and entry.outcome is not None
            and entry.refs.run_id is not None
            and entry.refs.step_id is not None
        )
