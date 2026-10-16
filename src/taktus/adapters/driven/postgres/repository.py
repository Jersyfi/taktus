"""A repository per aggregate over PostgreSQL, through the document mapping of `_mapping.py`."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from typing import Any

from taktus.adapters.driven.postgres._mapping import MAPPERS, Mapper, QueriedMapper
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Mark, NotQueryable, Stored, Tenant, WrongTenant

THREADED = 50
"""From how many documents on the aggregates are validated in a thread rather than on the loop."""


def table_name(kind: type[Stored]) -> str:
    """`ProcessVersion` → `process_version`: the mapper an aggregate class is stored by."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", kind.__name__).lower()


class PostgresRepository[T: Stored]:
    """The repository port for one aggregate: the class the composition root binds, stored as
    its document through the mapper of the same name. The queries of `Queried` are answered
    where the mapper offers them, and refused with `NotQueryable` where it does not."""

    def __init__(self, persistence: PostgresPersistence, kind: type[T]) -> None:
        name = table_name(kind)
        if name not in MAPPERS:
            raise LookupError(f"no table for {kind.__name__}; known: {', '.join(MAPPERS)}")
        self._persistence = persistence
        self._kind = kind
        self._mapper: Mapper = MAPPERS[name]

    async def get(self, tenant: Tenant, id: str) -> T | None:
        connection = self._persistence.connection(tenant)
        document = await self._mapper.get(connection, tenant, id)
        return None if document is None else self._kind.model_validate(document)

    async def put(self, tenant: Tenant, item: T) -> None:
        connection = self._persistence.connection(tenant)
        document = item.document()
        own = document.get("tenant")
        if own is not None and own != tenant:
            raise WrongTenant(own, tenant)
        await self._mapper.put(connection, tenant, document)

    async def list(self, tenant: Tenant) -> Sequence[T]:
        connection = self._persistence.connection(tenant)
        return await self._validated(await self._mapper.list(connection, tenant))

    async def newest(self, tenant: Tenant, *, limit: int, after: Mark | None = None) -> Sequence[T]:
        connection = self._persistence.connection(tenant)
        documents = await self._queried("created_at").newest(connection, tenant, limit, after)
        return await self._validated(documents)

    async def count(self, tenant: Tenant, by: Sequence[str]) -> Mapping[tuple[Any, ...], int]:
        connection = self._persistence.connection(tenant)
        return await self._queried(", ".join(by)).count(connection, tenant, by)

    async def having(self, tenant: Tenant, field: str, value: Any) -> Sequence[T]:
        connection = self._persistence.connection(tenant)
        documents = await self._queried(field).having(connection, tenant, field, value)
        return await self._validated(documents)

    async def _validated(self, documents: Sequence[dict[str, Any]]) -> Sequence[T]:
        """The aggregates of many documents, validated in a thread so that the event loop goes
        on serving meanwhile (#310); a few are validated where they are."""
        if len(documents) < THREADED:
            return [self._kind.model_validate(document) for document in documents]
        return await asyncio.to_thread(
            lambda: [self._kind.model_validate(document) for document in documents]
        )

    def _queried(self, field: str) -> QueriedMapper:
        if not isinstance(self._mapper, QueriedMapper):
            raise NotQueryable(self._kind.__name__, field)
        return self._mapper
