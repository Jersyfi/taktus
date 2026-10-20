"""A ledger that refuses a read of the tenant's whole chain (ADR-0105, #522)."""

from __future__ import annotations

from typing import Any

from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant


class NoWholeReads:
    """The ledger it wraps, except that `entries` without a run raises: a service handed this
    reads the entries of a run, of some kinds or a projection, or it fails."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger
        self.reads = 0
        """How many reads of the entries of one run went through."""

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Any:
        if run_id is None:
            raise AssertionError("a read of the tenant's whole ledger")
        self.reads += 1
        return await self._ledger.entries(tenant, run_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ledger, name)
