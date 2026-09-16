"""One suite, two implementations of the persistence port.

Every test in this directory takes the `backend` fixture and runs once against the in-memory
adapter and once against PostgreSQL in a container. The assertions are the same; if the two
disagree, the port is a leaky abstraction and that is the finding. PostgreSQL comes from
testcontainers, migrated once per session; when Docker is not available the PostgreSQL half
skips and says so. `TAKTUS_TEST_DATABASE_URL` points the suite at an existing, empty database
instead of a container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresRepository,
)
from taktus.adapters.driven.postgres.migrate import configuration
from taktus.adapters.driven.postgres.url import for_sqlalchemy
from taktus.ports.persistence import LedgerStore, Repository, Stored, UnitOfWork

IMPLEMENTATIONS = ("memory", "postgres")


def docker_available() -> str | None:
    """None when Docker can run a container, otherwise the reason it cannot."""
    if shutil.which("docker") is None:
        return "docker is not on the path"
    try:
        completed = subprocess.run(
            ["docker", "info"],  # noqa: S607
            capture_output=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "docker info did not answer within 20 seconds"
    if completed.returncode != 0:
        return "the Docker daemon is not reachable (docker info failed)"
    return None


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A migrated database for the whole session: an existing one from the environment, or a
    container. Tests keep apart through fresh tenants, so nothing is cleaned between them."""
    given = os.environ.get("TAKTUS_TEST_DATABASE_URL")
    if given:
        command.upgrade(configuration(given), "head")
        yield given
        return
    reason = docker_available()
    if reason is not None:
        pytest.skip(f"PostgreSQL tests need Docker for a container: {reason}")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        url = container.get_connection_url()
        command.upgrade(configuration(url), "head")
        yield url


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


@pytest.fixture(params=IMPLEMENTATIONS)
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    if request.param == "memory":
        memory = MemoryPersistence()

        async def no_tenant_to_create(tenant: str) -> None:
            pass

        yield Backend(
            "memory",
            memory,
            MemoryLedgerStore(memory),
            lambda kind: MemoryRepository(memory, kind),
            no_tenant_to_create,
        )
        return

    url: str = request.getfixturevalue("postgres_url")
    postgres = PostgresPersistence(url, pool_size=2)

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
