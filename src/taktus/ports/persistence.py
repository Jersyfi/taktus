"""Persistence: repositories per component, the append-only store of the ledger, and the unit
of work that makes their writes one transaction.

A repository holds one kind of aggregate and knows nothing of what it means. Each component
names its own repositories by binding the type parameter (`Repository[ProcessVersion]`); the
adapter implements the protocol once per aggregate. A write through a repository is the only
write there is — no component writes into another's repository (ADR-0016).

**Every call names its tenant** (ADR-0020). The tenant is an explicit parameter, never a default
and never read from a context variable by business code: a repository cannot be called without
one, and the adapter refuses a tenant other than the one the open transaction was opened for.

**Every call happens inside a unit of work.** The application layer opens one with
`transaction(tenant)`; everything the repositories and the ledger store do inside the block is
one transaction, committed at the end of the block and rolled back on an exception. A
repository used outside a block raises `NoTransaction`, and blocks do not nest: one use case,
one transaction. Neither an adapter nor the domain opens one.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from taktus.shared.v1 import LedgerEntry

type Tenant = str
"""The identifier of a tenant. Until the identity component exists there is one, `default`."""


class PersistenceError(Exception):
    pass


class NoTransaction(PersistenceError):
    """A repository or the ledger store was used outside a unit of work."""


class WrongTenant(PersistenceError):
    """A call named a tenant other than the one the open transaction was opened for."""

    def __init__(self, asked: Tenant, open_for: Tenant) -> None:
        super().__init__(f"the transaction is open for tenant {open_for!r}, not {asked!r}")


class NestedTransaction(PersistenceError):
    """A unit of work was opened inside another one."""


class Identified(Protocol):
    """What a repository needs from an aggregate: its identifier."""

    @property
    def id(self) -> str: ...


class Repository[T: Identified](Protocol):
    async def get(self, tenant: Tenant, id: str) -> T | None: ...

    async def put(self, tenant: Tenant, item: T) -> None:
        """Store the item under its id, replacing what was there."""
        ...

    async def list(self, tenant: Tenant) -> Sequence[T]: ...


class LedgerStore(Protocol):
    """Where the chain lives, one chain per tenant. Append-only: an entry, once stored, is never
    changed or removed. The chain's rules — sequence, links, hashes — belong to the ledger
    component; the store keeps order, and it keeps two writers of one chain apart."""

    async def append(self, tenant: Tenant, entry: LedgerEntry) -> None: ...

    async def last(self, tenant: Tenant) -> LedgerEntry | None:
        """The newest entry of the tenant's chain. Inside a transaction that then appends, the
        store makes sure no other transaction appends in between."""
        ...

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        """Every entry of the tenant's chain, in sequence order."""
        ...


class UnitOfWork(Protocol):
    def transaction(self, tenant: Tenant) -> AbstractAsyncContextManager[None]:
        """One transaction for one tenant across every repository and the ledger store of the
        same persistence. Committed when the block ends, rolled back when it raises."""
        ...
