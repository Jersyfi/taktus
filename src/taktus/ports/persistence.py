"""Persistence: repositories per component, and the append-only store of the ledger.

A repository holds one kind of aggregate and knows nothing of what it means. Each component
names its own repositories by binding the type parameter (`Repository[ProcessVersion]`); the
adapter implements the protocol once, generically. A write through a repository is the only
write there is — no component writes into another's repository (ADR-0016).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from taktus.shared.v1 import LedgerEntry


class Identified(Protocol):
    """What a repository needs from an aggregate: its identifier."""

    @property
    def id(self) -> str: ...


class Repository[T: Identified](Protocol):
    async def get(self, id: str) -> T | None: ...

    async def put(self, item: T) -> None:
        """Store the item under its id, replacing what was there."""
        ...

    async def list(self) -> Sequence[T]: ...


class LedgerStore(Protocol):
    """Where the chain lives. Append-only: an entry, once stored, is never changed or removed.
    The chain's rules — sequence, links, hashes — belong to the ledger component; the store
    keeps order."""

    async def append(self, entry: LedgerEntry) -> None: ...

    async def last(self) -> LedgerEntry | None: ...

    async def entries(self) -> Sequence[LedgerEntry]:
        """Every entry, in sequence order."""
        ...
