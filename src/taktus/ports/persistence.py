"""Persistence: repositories per component, the append-only stores of the ledger and of
provenance, and the unit of work that makes their writes one transaction.

A repository holds one kind of aggregate and knows nothing of what it means. Each component
names its own repositories by binding the type parameter (`Repository[ProcessVersion]`); the
adapter implements the protocol once per aggregate. A write through a repository is the only
write there is — no component writes into another's repository (ADR-0016).

**Every call names its tenant** (ADR-0020). The tenant is an explicit parameter, never a default
and never read from a context variable by business code: a repository cannot be called without
one, and the adapter refuses a tenant other than the one the open transaction was opened for.
An aggregate that carries its tenant as a field (a run does) carries the one it is stored
under; storing it under another is refused the same way.

**Every call happens inside a unit of work.** The application layer opens one with
`transaction(tenant)`; everything the repositories and the ledger store do inside the block is
one transaction, committed at the end of the block and rolled back on an exception. A store
that raises inside the block spoils the transaction: nothing of it is committed even if the
error is caught, and the block's end raises `SpoiltTransaction`. A repository used outside a
block raises `NoTransaction`, and blocks do not nest: one use case, one transaction. Neither
an adapter nor the domain opens one.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, Self

from taktus.shared.v1 import LedgerEntry, Provenance

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


class SpoiltTransaction(PersistenceError):
    """A store raised inside the unit of work and the error was caught there. Nothing of the
    block is committed — a database aborts the transaction at the first failed statement —
    and the block's end says so rather than returning as if it had committed."""

    def __init__(self) -> None:
        super().__init__(
            "a store raised inside this unit of work; the transaction was rolled back and "
            "nothing of it was committed"
        )


class DuplicateSequence(PersistenceError):
    """An entry was appended under a sequence number the tenant's chain already has."""

    def __init__(self, tenant: Tenant, seq: int) -> None:
        super().__init__(f"the chain of tenant {tenant!r} already has an entry with seq {seq}")


class DuplicateProvenance(PersistenceError):
    """A step run's provenance was recorded a second time. A completed step has exactly one
    record; a second one would let a result defect rewrite its own history (ADR-0021)."""

    def __init__(self, tenant: Tenant, run_id: str, step_id: str) -> None:
        super().__init__(
            f"tenant {tenant!r} already holds the provenance of step {step_id!r} of run {run_id!r}"
        )


class Identified(Protocol):
    """What a repository needs from an aggregate: its identifier."""

    @property
    def id(self) -> str: ...


class Stored(Identified, Protocol):
    """What an adapter needs from an aggregate on top of its identifier: the way to and from
    its JSON document. An adapter never imports a component's class (ADR-0003); the
    composition root binds the class, the adapter stores the document."""

    def document(self) -> dict[str, Any]: ...

    @classmethod
    def model_validate(cls, obj: Any) -> Self: ...


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

    async def append(self, tenant: Tenant, entry: LedgerEntry) -> None:
        """Raises `DuplicateSequence` when the chain already has the entry's seq."""
        ...

    async def last(self, tenant: Tenant) -> LedgerEntry | None:
        """The newest entry of the tenant's chain. Inside a transaction that then appends, the
        store makes sure no other transaction appends in between."""
        ...

    async def entries(self, tenant: Tenant) -> Sequence[LedgerEntry]:
        """Every entry of the tenant's chain, in sequence order."""
        ...


class ProvenanceStore(Protocol):
    """Where provenance records live (ADR-0021). Append-only, as the ledger store is: a record,
    once stored, is never changed or removed, and a step run is recorded once. Reading walks
    the chain: from the record that produced an artifact back through the records its inputs
    name, in one query of the store."""

    async def append(self, tenant: Tenant, record: Provenance) -> None:
        """Raises `DuplicateProvenance` when the step run is already recorded."""
        ...

    async def of_run(self, tenant: Tenant, run_id: str) -> Sequence[Provenance]:
        """Every record of one run, in the order of the ledger entries they belong to."""
        ...

    async def chain(self, tenant: Tenant, run_id: str, artifact_id: str) -> Sequence[Provenance]:
        """The record that produced the artifact in that run, followed by every record its
        inputs lead to, transitively, across runs of the tenant. Empty when no record of the
        run lists the artifact. One query."""
        ...


class UnitOfWork(Protocol):
    def transaction(self, tenant: Tenant) -> AbstractAsyncContextManager[None]:
        """One transaction for one tenant across every repository, the ledger store and the
        provenance store of the same persistence. Committed when the block ends, rolled back
        when it raises."""
        ...
