from __future__ import annotations

import re
from collections.abc import Sequence

from taktus.adapters.driven.postgres._mapping import MAPPERS, Mapper
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Stored, Tenant, WrongTenant


def table_name(kind: type[Stored]) -> str:
    """`ProcessVersion` → `process_version`: the mapper an aggregate class is stored by."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", kind.__name__).lower()


class PostgresRepository[T: Stored]:
    """The repository port for one aggregate: the class the composition root binds, stored as
    its document through the mapper of the same name."""

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
        documents = await self._mapper.list(connection, tenant)
        return [self._kind.model_validate(document) for document in documents]
