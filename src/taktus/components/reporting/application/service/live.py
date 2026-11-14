"""The stream of changes, read from the ledger (ADR-0055).

Two questions, both answered from the records and nothing else:

- **Where does a reader start?** One without a position, or whose position is unknown or more
  than 1,000 entries behind, starts from a snapshot, read together with its position. One
  whose position is known starts right after it, and receives every change it missed.
- **What happened after a sequence number?** One read of the tenant's ledger, for every stream a
  replica holds of the tenant. Each entry that records a change of state is projected and paired
  with its run, so that the scope and the predicate can be applied per reader when it is sent.

How often to ask, and how to hand the changes to the open streams, is the composition root's
(`composition/live.py`); this service holds no stream and no time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from taktus.components.reporting.domain.model.live import (
    Change,
    ProcessOf,
    Reader,
    RunRef,
    Scope,
    Snapshot,
)
from taktus.components.reporting.domain.service import visibility
from taktus.components.reporting.domain.service.live import (
    in_scope,
    needs_snapshot,
    project,
    visible,
)
from taktus.components.reporting.ports.live import LiveRecords, States
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import LedgerEntry

SNAPSHOT_RUNS = 1_000
"""The most runs one snapshot lists: the newest of the scope (ADR-0317 §1)."""
RECENT_MINUTES = 60
"""How far back the recent changes reach at most, and unless asked otherwise (ADR-0317 §4)."""
RECENT_CHANGES = 500
"""The most entries one read of the recent changes takes: the newest (ADR-0317 §4)."""

KNOWN_RUNS = 10_000
"""How many runs the service remembers where they belong before it forgets them all and reads
them again; a run's tenant and process version never change."""


@dataclass(frozen=True)
class Opening:
    """Where a stream starts: after `seq`, with a snapshot first or without one."""

    seq: int
    snapshot: Snapshot | None


@dataclass(frozen=True)
class Pending:
    """One change read from the ledger, with the run it belongs to: what the scope and the
    predicate are applied to when it is sent."""

    seq: int
    change: Change
    run: RunRef


@dataclass(frozen=True)
class Read:
    """What one read of a tenant's ledger found: the changes, and the sequence number it read
    up to — past every entry that is no change as well."""

    pending: tuple[Pending, ...]
    through: int


@dataclass(frozen=True)
class Recent:
    """The changes of the last minutes a reader may see, and whether the bound on the entries
    read may have cut older ones off: `complete` is false where it may have."""

    changes: tuple[Change, ...]
    complete: bool


class LiveChanges:
    def __init__(self, records: LiveRecords, states: States) -> None:
        self._records = records
        self._states = states
        self._known: dict[tuple[Tenant, str], RunRef] = {}

    async def open(
        self, reader: Reader, scope: Scope, position: str | None, *, listed: bool = True
    ) -> Opening:
        tenant = reader.tenant
        if position is not None:
            seq = await self._records.position(tenant, position)
            if not needs_snapshot(seq, await self._records.head(tenant)) and seq is not None:
                return Opening(seq=seq, snapshot=None)
        return await self.snapshot(reader, scope, listed=listed)

    async def snapshot(self, reader: Reader, scope: Scope, *, listed: bool = True) -> Opening:
        """The runs the reader may see in the scope, at one position: in the tenant scope those
        not yet ended, at most `SNAPSHOT_RUNS`, the newest. Without `listed`, the position
        alone, and no run is read (ADR-0317). A run withheld leaves no trace: it is not listed,
        and the position is a hash."""
        state = await self._records.state(
            reader.tenant, scope, limit=SNAPSHOT_RUNS if listed else 0
        )
        runs = tuple(
            shown
            for ref, shown in state.runs
            if in_scope(scope, ref) and visibility.may_see(reader, ref)
        )
        return Opening(
            seq=state.seq,
            snapshot=Snapshot(
                position=state.position,
                scope=scope,
                runs=runs,
                truncated=True if state.truncated else None,
                listed=None if listed else False,
            ),
        )

    async def recent(self, reader: Reader, scope: Scope, since: datetime) -> Recent:
        """The changes recorded since `since` that this reader receives in this scope, oldest
        first: the same projection, predicate and visibility as the stream, over the newest
        `RECENT_CHANGES` entries of the kinds that change a state (ADR-0317 §4)."""
        tenant = reader.tenant
        entries = await self._records.recent(tenant, since, limit=RECENT_CHANGES)
        read = await self._paired(tenant, entries)
        return Recent(
            changes=tuple(self.visible(reader, scope, read)),
            complete=len(entries) < RECENT_CHANGES,
        )

    async def read(self, tenant: Tenant, after: int, *, limit: int) -> Read:
        entries = await self._records.after(tenant, after, limit=limit)
        if not entries:
            return Read(pending=(), through=after)
        return Read(pending=await self._paired(tenant, entries), through=entries[-1].seq)

    async def _paired(self, tenant: Tenant, entries: Sequence[LedgerEntry]) -> tuple[Pending, ...]:
        """Each entry that changed a state, projected and paired with its run, which names the
        process and version the change carries (ADR-0317 §3)."""
        projected: list[tuple[int, Change]] = []
        for entry in entries:
            state = self._states(entry.kind, entry.outcome)
            if state is None:
                continue
            change = project(entry, state)
            if change is not None:
                projected.append((entry.seq, change))
        runs = await self._runs(tenant, [c.run for _, c in projected])
        return tuple(
            Pending(
                seq,
                change.model_copy(
                    update={"process": ProcessOf.of(runs[change.run].process_version)}
                ),
                runs[change.run],
            )
            for seq, change in projected
            if change.run in runs
        )

    @staticmethod
    def visible(reader: Reader, scope: Scope, pending: Sequence[Pending]) -> list[Change]:
        """The changes this reader receives now, with its roles as they are now."""
        return visible(reader, scope, ((p.change, p.run) for p in pending))

    async def _runs(self, tenant: Tenant, ids: Sequence[str]) -> dict[str, RunRef]:
        if len(self._known) > KNOWN_RUNS:
            self._known.clear()
        wanted = [i for i in dict.fromkeys(ids) if (tenant, i) not in self._known]
        if wanted:
            for run_id, ref in (await self._records.runs(tenant, wanted)).items():
                self._known[(tenant, run_id)] = ref
        return {i: self._known[(tenant, i)] for i in ids if (tenant, i) in self._known}
