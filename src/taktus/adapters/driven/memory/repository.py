from __future__ import annotations

import builtins
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from taktus.adapters.driven.memory.persistence import MemoryPersistence
from taktus.ports.persistence import Mark, NotQueryable, Stored, Tenant, WrongTenant


class MemoryRepository[T: Stored]:
    """A dictionary per tenant behind the repository port, reading through the open
    transaction's journal. It answers the queries of `Queried` by reading every aggregate's
    document: the same answers as the database, not in the same time."""

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

    async def newest(self, tenant: Tenant, *, limit: int, after: Mark | None = None) -> Sequence[T]:
        items = sorted(await self.list(tenant), key=lambda item: item.id)
        items.sort(key=self._created, reverse=True)
        if after is not None:
            items = [
                item
                for item in items
                if self._created(item) < after.created_at
                or (self._created(item) == after.created_at and item.id > after.id)
            ]
        return items[:limit]

    async def count(self, tenant: Tenant, by: Sequence[str]) -> Mapping[tuple[Any, ...], int]:
        for field in by:
            if "." in field:
                raise NotQueryable(self._kind, field)
        counted: Counter[tuple[Any, ...]] = Counter()
        for item in await self.list(tenant):
            document = item.document()
            counted[tuple(self._values(document, field)[0] for field in by)] += 1
        return dict(counted)

    async def having(self, tenant: Tenant, field: str, value: Any) -> Sequence[T]:
        return [
            item
            for item in await self.list(tenant)
            if value in self._values(item.document(), field)
        ]

    def _created(self, item: T) -> datetime:
        created = item.document().get("created_at")
        if created is None:
            raise NotQueryable(self._kind, "created_at")
        return datetime.fromisoformat(created)

    def _values(self, document: dict[str, Any], field: str) -> builtins.list[Any]:
        """The values a field holds in a document: one for a field, one per element for a
        field of a list's elements; a field the document leaves out holds None."""
        head, _, rest = field.partition(".")
        if not rest:
            return [document.get(head)]
        elements = document.get(head)
        if not isinstance(elements, builtins.list):
            raise NotQueryable(self._kind, field)
        return [value for element in elements for value in self._values(element, rest)]
