"""One process's stores in one object, with the unit of work over them.

A transaction is a journal: what the block writes goes into the journal, reads inside the block
see the journal over the committed state, and the journal is applied when the block ends
without an exception — all of it, or nothing. That is what makes the memory implementation
answer the shared repository suite the way the database does, including rollback.

With a snapshot directory, every committed change writes the whole store of each kind it
touched to `<directory>/<kind>.json`, keyed by tenant, and the store reads it back on start.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self

from pydantic import ValidationError

from taktus.adapters.driven.memory import _snapshot
from taktus.ports.persistence import (
    NestedTransaction,
    NoTransaction,
    Projected,
    SpoiltTransaction,
    Stored,
    Tenant,
    UnreadableState,
    WrongTenant,
)
from taktus.shared.v1 import LedgerEntry, Provenance

LEDGER = "ledger"
PROVENANCE = "provenance"


@dataclass
class Transaction:
    tenant: Tenant
    puts: dict[tuple[str, str], Any] = field(default_factory=dict)  # (kind, id) → item
    appended: list[LedgerEntry] = field(default_factory=list)
    recorded: list[Provenance] = field(default_factory=list)
    spoilt: bool = False
    ended: list[Callable[[], None]] = field(default_factory=list)
    """What to undo when the transaction ends, committed or not: the locks it took."""
    projected: dict[str, tuple[Projected, bool]] = field(default_factory=dict)
    """The projections this transaction stored, by name, each with whether it replaces what
    was stored (ADR-0105)."""
    claimed: set[str] = field(default_factory=set)
    """The claims this transaction holds until it ends, by name: a second claim of one it holds
    is granted at once, as PostgreSQL grants a transaction's advisory lock again."""


class MemoryPersistence:
    def __init__(self, snapshot_dir: Path | None = None) -> None:
        self._snapshot_dir = snapshot_dir
        self._tables: dict[str, dict[Tenant, dict[str, Any]]] = {}
        self._ledger: dict[Tenant, list[LedgerEntry]] = {}
        self._provenance: dict[Tenant, list[Provenance]] = {}
        self._projections: dict[Tenant, dict[str, Projected]] = {}
        """Derived from the ledger and rebuilt from it, so never written to a snapshot."""
        self._current: ContextVar[Transaction | None] = ContextVar("transaction", default=None)
        self._claims: dict[str, asyncio.Lock] = {}
        if snapshot_dir is not None:
            self._ledger = _read(snapshot_dir / f"{LEDGER}.json", LedgerEntry)
            self._provenance = _read(snapshot_dir / f"{PROVENANCE}.json", Provenance)

    # --- the unit of work ----------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self, tenant: Tenant, *, consistent: bool = False) -> AsyncIterator[None]:
        """`consistent` asks nothing more of this store: its reads never suspend, so no other
        transaction commits between two reads that follow each other."""
        if self._current.get() is not None:
            raise NestedTransaction("a unit of work is already open; they do not nest")
        transaction = Transaction(tenant)
        token = self._current.set(transaction)
        try:
            yield
            if transaction.spoilt:
                raise SpoiltTransaction
            await self._commit(transaction)
        finally:
            self._current.reset(token)
            for end in transaction.ended:
                end()

    def current(self, tenant: Tenant) -> Transaction:
        transaction = self._current.get()
        if transaction is None:
            raise NoTransaction("persistence is used inside a unit of work; none is open")
        if transaction.tenant != tenant:
            raise WrongTenant(tenant, transaction.tenant)
        return transaction

    async def claim(self, transaction: Transaction, name: str) -> None:
        """Hold the claim `name` until `transaction` ends, waiting while another transaction
        holds it: what `pg_advisory_xact_lock` is to the database adapter."""
        if name in transaction.claimed:
            return
        lock = self._claims.setdefault(name, asyncio.Lock())
        await lock.acquire()
        transaction.claimed.add(name)
        transaction.ended.append(lock.release)

    async def _commit(self, transaction: Transaction) -> None:
        touched: set[str] = set()
        for (kind, id), item in transaction.puts.items():
            self._tables.setdefault(kind, {}).setdefault(transaction.tenant, {})[id] = item
            touched.add(kind)
        if transaction.appended:
            self._ledger.setdefault(transaction.tenant, []).extend(transaction.appended)
        if transaction.recorded:
            self._provenance.setdefault(transaction.tenant, []).extend(transaction.recorded)
        stored = self._projections.setdefault(transaction.tenant, {})
        for name, (value, replace) in transaction.projected.items():
            # Another transaction may have stored this projection meanwhile: without `replace`,
            # the one that read further wins, as the database adapter's conditional write does.
            if replace or name not in stored or stored[name].seq < value.seq:
                stored[name] = value
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
        if transaction.recorded:
            await _snapshot.write(
                self._snapshot_dir / f"{PROVENANCE}.json",
                {t: [r.document() for r in records] for t, records in self._provenance.items()},
            )

    # --- how much room it takes ------------------------------------------------------------

    async def state_bytes(self) -> int | None:
        """The snapshot files' size; None without a snapshot directory, where nothing is on
        disk (the `StateSize` port)."""
        directory = self._snapshot_dir
        if directory is None:
            return None

        def _size() -> int:
            if not directory.is_dir():
                return 0
            return sum(p.stat().st_size for p in directory.glob("*.json") if p.is_file())

        return await asyncio.to_thread(_size)

    # --- what the stores see -------------------------------------------------------------------

    def table(self, kind: str, tenant: Tenant) -> dict[str, Any]:
        return self._tables.setdefault(kind, {}).setdefault(tenant, {})

    def tenants_of(self, kind: str) -> list[Tenant]:
        """Every tenant that holds something of a kind: what the tenant store reads across
        tenants."""
        return list(self._tables.get(kind, {}))

    def chain(self, tenant: Tenant) -> list[LedgerEntry]:
        return self._ledger.setdefault(tenant, [])

    def provenance(self, tenant: Tenant) -> list[Provenance]:
        return self._provenance.setdefault(tenant, [])

    def projections(self, tenant: Tenant) -> dict[str, Projected]:
        return self._projections.setdefault(tenant, {})

    def load(self, kind: str, model: type[Stored]) -> None:
        """Read a kind's snapshot, once, when its repository is created."""
        if self._snapshot_dir is None or kind in self._tables:
            return
        stored = _read(self._snapshot_dir / f"{kind}.json", model)
        self._tables[kind] = {
            tenant: {item.id: item for item in items} for tenant, items in stored.items()
        }


class _Validated(Protocol):
    @classmethod
    def model_validate(cls, obj: Any) -> Self: ...


def _read[T: _Validated](path: Path, model: type[T]) -> dict[Tenant, list[T]]:
    """A snapshot file's documents by tenant. One this version cannot read — an earlier
    format, or a file that is not what was written — is refused naming the file; a snapshot
    is development state and is not migrated."""
    try:
        stored = _snapshot.read(path) or {}
        return {
            tenant: [model.model_validate(d) for d in documents]
            for tenant, documents in stored.items()
        }
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise UnreadableState(str(path), f"{where}: {first['msg']}") from error
    except (ValueError, TypeError, AttributeError) as error:
        raise UnreadableState(str(path), str(error) or type(error).__name__) from error
