"""Blocked-time accounts, read (ADR-0015, ADR-0043): every block that ended, its sums, and a
person's own waits.

Everything here is read from the tenant's ledger and the records its `step.waited` entries name
by digest, and from nothing else. A rehearsal's blocks are left out: a rehearsal acts on nothing
outside, and its waits are not the work's (ADR-0030).

Three reads, and no fourth:

- `blocks` — every block, with its account, its cause, the run, the step and the process
  version it held up, and how long it lasted. A block on a person names no one;
- `sums` — blocked time per account, per process and per period, with the share of the work it
  held up. No person is a key, and the order is by key, never by a figure;
- `own` — the waits on a person that `reader` ended by answering. The reader is the identity
  the caller authenticated; a figure of waiting on a person is joined to a name only for the
  person it names (ADR-0015, protective rule; principle 14).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

from taktus.components.run.domain.service.blocked import (
    RECORD_KIND,
    Block,
    BlockedSum,
    Period,
    parse,
    period_of,
    process_of,
    sums,
)
from taktus.ports.ledger import Ledger
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import LedgerEntry

ANSWERS = frozenset({"step.confirmed", "step.performed"})
"""The entries that end a wait on a person, each naming who answered as its actor."""


class BlockedTime:
    def __init__(self, ledger: Ledger, objects: ObjectStore, work: UnitOfWork) -> None:
        self._ledger = ledger
        self._objects = objects
        self._work = work

    async def blocks(self, tenant: Tenant) -> tuple[Block, ...]:
        """Every block that ended in the tenant, oldest first."""
        return tuple(block for _, block in await self._recorded(await self._entries(tenant)))

    async def sums(self, tenant: Tenant, period: Period = "day") -> tuple[BlockedSum, ...]:
        """Blocked time per account, per process and per period."""
        entries = await self._entries(tenant)
        active: dict[tuple[str, str], set[str]] = defaultdict(set)
        for entry in entries:
            if entry.refs.run_id is None or entry.refs.process_version is None:
                continue
            key = (process_of(entry.refs.process_version), period_of(entry.ts, period))
            active[key].add(entry.refs.run_id)
        recorded = [block for _, block in await self._recorded(entries)]
        return sums(recorded, {k: frozenset(v) for k, v in active.items()}, period)

    async def own(self, tenant: Tenant, reader: str) -> tuple[Block, ...]:
        """The waits on a person that `reader` ended: each block of `wait.human` whose step the
        reader answered, in the entry right after the block's record."""
        entries = await self._entries(tenant)
        answered_by: dict[int, str | None] = {}
        pending: dict[tuple[str, str], int] = {}
        for entry in entries:
            run_id, step_id = entry.refs.run_id, entry.refs.step_id
            if run_id is None or step_id is None:
                continue
            if entry.kind == RECORD_KIND:
                pending[(run_id, step_id)] = entry.seq
            elif entry.kind in ANSWERS and (run_id, step_id) in pending:
                answered_by[pending.pop((run_id, step_id))] = entry.refs.actor
        return tuple(
            block
            for entry, block in await self._recorded(entries)
            if block.account == "wait.human" and answered_by.get(entry.seq) == reader
        )

    async def _entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        async with self._work.transaction(tenant):
            return await self._ledger.entries(tenant)

    async def _recorded(self, entries: Sequence[LedgerEntry]) -> list[tuple[LedgerEntry, Block]]:
        """The blocks the entries name, each with its entry. A record whose content is gone
        cannot be read; it is left out, and the ledger still shows the entry."""
        found: list[tuple[LedgerEntry, Block]] = []
        for entry in entries:
            if entry.kind != RECORD_KIND or entry.rehearsal or entry.content_digest is None:
                continue
            content = await self._objects.get(entry.content_digest)
            if content is None:
                continue
            found.append((entry, parse(json.loads(content))))
        return found
