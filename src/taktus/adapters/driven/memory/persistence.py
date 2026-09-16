"""One process's stores in one object, with the unit of work over them.

A transaction is a journal: what the block writes goes into the journal, reads inside the block
see the journal over the committed state, and the journal is applied when the block ends
without an exception — all of it, or nothing. That is what makes the memory implementation
answer the shared repository suite the way the database does, including rollback.

With a snapshot directory, every committed change writes the whole store of each kind it
touched to `<directory>/<kind>.json`, keyed by tenant, and the store reads it back on start.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self

from taktus.adapters.driven.memory import _snapshot
from taktus.ports.persistence import NestedTransaction, NoTransaction, Tenant, WrongTenant
from taktus.shared.v1 import LedgerEntry

LEDGER = "ledger"


class Stored(Protocol):
    """What the memory store needs from an aggregate: its id, and the way to and from JSON."""

    @property
    def id(self) -> str: ...

    def document(self) -> dict[str, Any]: ...

    @classmethod
    def model_validate(cls, obj: Any) -> Self: ...


@dataclass
class Transaction:
    tenant: Tenant
    puts: dict[tuple[str, str], Any] = field(default_factory=dict)  # (kind, id) → item
    appended: list[LedgerEntry] = field(default_factory=list)


class MemoryPersistence:
    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir
        self._tables: dict[str, dict[Tenant, dict[str, Any]]] = {}
        self._ledger: dict[Tenant, list[LedgerEntry]] = {}
        self._current: ContextVar[Transaction | None] = ContextVar("transaction", default=None)
        if snapshot_dir is not None:
            stored = _snapshot.read(snapshot_dir / f"{LEDGER}.json") or {}
            for tenant, documents in stored.items():
                self._ledger[tenant] = [LedgerEntry.model_validate(d) for d in documents]

    # --- the unit of work ----------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self, tenant: Tenant) -> AsyncIterator[None]:
        if self._current.get() is not None:
            raise NestedTransaction("a unit of work is already open; they do not nest")
        transaction = Transaction(tenant)
        token = self._current.set(transaction)
        try:
            yield
            await self._commit(transaction)
        finally:
            self._current.reset(token)

    def current(self, tenant: Tenant) -> Transaction:
        transaction = self._current.get()
        if transaction is None:
            raise NoTransaction("persistence is used inside a unit of work; none is open")
        if transaction.tenant != tenant:
            raise WrongTenant(tenant, transaction.tenant)
        return transaction

    async def _commit(self, transaction: Transaction) -> None:
        touched: set[str] = set()
        for (kind, id), item in transaction.puts.items():
            self._tables.setdefault(kind, {}).setdefault(transaction.tenant, {})[id] = item
            touched.add(kind)
        if transaction.appended:
            self._ledger.setdefault(transaction.tenant, []).extend(transaction.appended)
        if self._snapshot_dir is None:
            return
        for kind in touched:
            await _snapshot.write(
                self._snapshot_dir / f"{kind}.json",
                {
                    tenant: [item.document() for item in items.values()]
                    for tenant, items in self._tables[kind].items()
                },
            )
        if transaction.appended:
            await _snapshot.write(
                self._snapshot_dir / f"{LEDGER}.json",
                {t: [e.document() for e in entries] for t, entries in self._ledger.items()},
            )

    # --- what the stores see -------------------------------------------------------------------

    def table(self, kind: str, tenant: Tenant) -> dict[str, Any]:
        return self._tables.setdefault(kind, {}).setdefault(tenant, {})

    def chain(self, tenant: Tenant) -> list[LedgerEntry]:
        return self._ledger.setdefault(tenant, [])

    def load(self, kind: str, model: type[Stored]) -> None:
        """Read a kind's snapshot, once, when its repository is created."""
        if self._snapshot_dir is None or kind in self._tables:
            return
        self._tables[kind] = {}
        stored = _snapshot.read(self._snapshot_dir / f"{kind}.json") or {}
        for tenant, documents in stored.items():
            items = [model.model_validate(d) for d in documents]
            self._tables[kind][tenant] = {item.id: item for item in items}
