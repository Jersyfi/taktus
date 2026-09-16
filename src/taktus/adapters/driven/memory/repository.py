from __future__ import annotations

from collections.abc import Sequence

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Stored, Tenant, WrongTenant


class MemoryRepository[T: Stored]:
    """A dictionary per tenant behind the repository port, reading through the open
    transaction's journal."""

    def __init__(self, persistence: MemoryPersistence, model: type[T]) -> None:
        self._persistence = persistence
        self._model = model
        self._kind = model.__name__.lower()
        persistence.load(self._kind, model)

    async def get(self, tenant: Tenant, id: str) -> T | None:
        transaction = self._persistence.current(tenant)
        pending: T | None = transaction.puts.get((self._kind, id))
        if pending is not None:
            return pending  # frozen: handing out the object itself is safe
        return self._persistence.table(self._kind, tenant).get(id)

    async def put(self, tenant: Tenant, item: T) -> None:
        transaction = self._persistence.current(tenant)
        own = item.document().get("tenant")
        if own is not None and own != tenant:
            raise WrongTenant(own, tenant)
        transaction.puts[(self._kind, item.id)] = item

    async def list(self, tenant: Tenant) -> Sequence[T]:
        transaction = self._persistence.current(tenant)
        merged: dict[str, T] = dict(self._persistence.table(self._kind, tenant))
        for (kind, id), item in transaction.puts.items():
            if kind == self._kind:
                merged[id] = item
        return list(merged.values())
