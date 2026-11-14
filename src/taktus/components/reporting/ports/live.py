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
from datetime import datetime
from typing import Protocol

from taktus.components.reporting.domain.model.live import RunRef, Scope, SnapshotRun, StateAfter
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Digest, LedgerEntry


@dataclass(frozen=True)
class TenantState:
    """The runs of a scope, read at one position of its tenant's ledger (ADR-0055 §4,
    ADR-0317)."""

    seq: int
    """The sequence number of the newest entry the runs reflect; 0 for an empty ledger."""
    position: Digest | None
    """Its hash; None for an empty ledger."""
    runs: Sequence[tuple[RunRef, SnapshotRun]]
    truncated: bool = False
    """The scope held more runs than were read."""


class LiveRecords(Protocol):
    async def state(self, tenant: Tenant, scope: Scope, *, limit: int) -> TenantState:
        """The position and the runs of the scope in one consistent read: the runs show every
        entry up to the position (ADR-0055 §4). Filtered where they are stored: one run for a
        run scope, the runs of the process for a process scope, the runs not yet ended for the
        tenant scope; at most `limit` of them, the newest, and none read at all for a `limit`
        of 0 (ADR-0317)."""
        ...

    async def recent(self, tenant: Tenant, since: datetime, *, limit: int) -> Sequence[LedgerEntry]:
        """The newest `limit` entries at most of the kinds that record a change of state,
        recorded at or after `since`, in the ledger's order (ADR-0317 §4)."""
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
