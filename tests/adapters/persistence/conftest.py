"""One suite, two implementations of the persistence port.

Every test in this directory takes the `backend` fixture and runs once against the in-memory
adapter and once against PostgreSQL in a container (`postgres_url`, tests/conftest.py). The
assertions are the same; if the two disagree, the port is a leaky abstraction and that is the
finding. When Docker is not available the PostgreSQL half skips and says so.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresRepository,
)
from taktus.adapters.driven.postgres.url import for_sqlalchemy
from taktus.ports.persistence import LedgerStore, Repository, Stored, UnitOfWork

IMPLEMENTATIONS = ("memory", "postgres")


@dataclass
class Backend:
    """The port as one implementation offers it, plus what a test needs around it."""

    name: str
    work: UnitOfWork
    ledger_store: LedgerStore
    _repository: Any
    _new_tenant: Any
    tenants: list[str] = field(default_factory=list)

    def repository[T: Stored](self, kind: type[T]) -> Repository[T]:
        repository: Repository[T] = self._repository(kind)
        return repository

    async def tenant(self) -> str:
        """A tenant nobody else uses, created where the implementation needs it to exist."""
        tenant = f"t_{os.urandom(6).hex()}"
        await self._new_tenant(tenant)
        self.tenants.append(tenant)
        return tenant


@pytest.fixture
async def memory_backend() -> Backend:
    memory = MemoryPersistence()

    async def no_tenant_to_create(tenant: str) -> None:
        pass

    return Backend(
        "memory",
        memory,
        MemoryLedgerStore(memory),
        lambda kind: MemoryRepository(memory, kind),
        no_tenant_to_create,
    )


@pytest.fixture
async def postgres_backend(postgres_url: str) -> AsyncIterator[Backend]:
    postgres = PostgresPersistence(postgres_url, pool_size=2)

    async def create_tenant(tenant: str) -> None:
        # As the login user, inside a transaction that names the tenant, so that the forced
        # row-level security on `tenant` lets the row in whoever the login user is.
        async with postgres.engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
            )
            await connection.execute(
                text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"),
                {"t": tenant},
            )

    try:
        yield Backend(
            "postgres",
            postgres,
            PostgresLedgerStore(postgres),
            lambda kind: PostgresRepository(postgres, kind),
            create_tenant,
        )
    finally:
        await postgres.close()


@pytest.fixture(params=IMPLEMENTATIONS)
def backend(request: pytest.FixtureRequest) -> Backend:
    """The port as each implementation offers it: every test that takes this runs twice."""
    chosen: Backend = request.getfixturevalue(f"{request.param}_backend")
    return chosen


@pytest.fixture
def sync_engine(postgres_url: str) -> Iterator[Any]:
    """A plain connection as the login user, for what only the database can show: what a raw
    statement sees, and what the ledger's trigger does."""
    engine = create_engine(
        for_sqlalchemy(postgres_url), connect_args={"options": "-c timezone=UTC"}
    )
    try:
        yield engine
    finally:
        engine.dispose()
