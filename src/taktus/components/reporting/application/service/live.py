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

from taktus.components.reporting.domain.model.live import (
    Change,
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


class LiveChanges:
    def __init__(self, records: LiveRecords, states: States) -> None:
        self._records = records
        self._states = states
        self._known: dict[tuple[Tenant, str], RunRef] = {}

    async def open(self, reader: Reader, scope: Scope, position: str | None) -> Opening:
        tenant = reader.tenant
        if position is not None:
            seq = await self._records.position(tenant, position)
            if not needs_snapshot(seq, await self._records.head(tenant)) and seq is not None:
                return Opening(seq=seq, snapshot=None)
        return await self.snapshot(reader, scope)

    async def snapshot(self, reader: Reader, scope: Scope) -> Opening:
        """Every run the reader may see in the scope, at one position. A run withheld leaves
        no trace: it is not listed, and the position is a hash."""
        state = await self._records.state(reader.tenant)
        runs = tuple(
            shown
            for ref, shown in state.runs
            if in_scope(scope, ref) and visibility.may_see(reader, ref)
        )
        return Opening(
            seq=state.seq,
            snapshot=Snapshot(position=state.position, scope=scope, runs=runs),
        )

    async def read(self, tenant: Tenant, after: int, *, limit: int) -> Read:
        entries = await self._records.after(tenant, after, limit=limit)
        if not entries:
            return Read(pending=(), through=after)
        projected: list[tuple[int, Change]] = []
        for entry in entries:
            state = self._states(entry.kind, entry.outcome)
            if state is None:
                continue
            change = project(entry, state)
            if change is not None:
                projected.append((entry.seq, change))
        runs = await self._runs(tenant, [c.run for _, c in projected])
        pending = tuple(
            Pending(seq, change, runs[change.run])
            for seq, change in projected
            if change.run in runs
        )
        return Read(pending=pending, through=entries[-1].seq)

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
