"""What the stream of changes reads (ADR-0055).

**`LiveRecords`** reads the records of a tenant: its ledger, from which every change is read,
and its runs, from which a snapshot is made. The composition root binds it to the ledger store
and the run's repository; this component never imports the run.

**`States`** says which state an entry of a kind and an outcome led to. The run component and
the decision component publish it beside their state machines; the composition root joins them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from taktus.components.reporting.domain.model.live import RunRef, SnapshotRun, StateAfter
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Digest, LedgerEntry


@dataclass(frozen=True)
class TenantState:
    """Every run of a tenant, read at one position of its ledger and nothing after it."""

    seq: int
    """The sequence number of the newest entry the runs reflect; 0 for an empty ledger."""
    position: Digest | None
    """Its hash; None for an empty ledger."""
    runs: Sequence[tuple[RunRef, SnapshotRun]]


class LiveRecords(Protocol):
    async def state(self, tenant: Tenant) -> TenantState:
        """The runs and the position in one consistent read: the runs show exactly the entries
        up to the position (ADR-0055 §4)."""
        ...

    async def head(self, tenant: Tenant) -> int:
        """The newest sequence number of the tenant's ledger; 0 when it is empty."""
        ...

    async def position(self, tenant: Tenant, hash: str) -> int | None:
        """The sequence number of the tenant's entry with this hash; None when there is none."""
        ...

    async def after(self, tenant: Tenant, seq: int, *, limit: int) -> Sequence[LedgerEntry]:
        """At most `limit` entries after `seq`, in the ledger's order."""
        ...

    async def runs(self, tenant: Tenant, ids: Sequence[str]) -> Mapping[str, RunRef]:
        """The runs of the tenant with these ids; one the tenant does not hold is absent."""
        ...


class States(Protocol):
    def __call__(self, kind: str, outcome: str | None) -> StateAfter | None: ...
