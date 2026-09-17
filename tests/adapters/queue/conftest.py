"""One suite, two implementations of the queue and the leadership ports.

Every test takes `backend` and runs once against the memory adapters and once against
PostgreSQL in a container (`postgres_url`, tests/conftest.py). The assertions are the same; a
disagreement is a finding about the port. Without Docker the PostgreSQL half skips and says so.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.memory import MemoryLeadership, MemoryPersistence, MemoryQueue
from taktus.adapters.driven.postgres import (
    PostgresLeadership,
    PostgresPersistence,
    PostgresQueue,
)
from taktus.ports.leadership import Lead, Leadership
from taktus.ports.persistence import UnitOfWork
from taktus.ports.queue import Queue

IMPLEMENTATIONS = ("memory", "postgres")
LEASE_SECONDS = 5


@dataclass
class Backend:
    name: str
    work: UnitOfWork
    queue: Queue
    leadership: Leadership
    _new_tenant: Callable[[str], Awaitable[None]]
    _expire: Callable[[str, str], Awaitable[None]]
    _sever: Callable[[Lead], Awaitable[None]]

    async def tenant(self) -> str:
        tenant = f"t_{os.urandom(6).hex()}"
        await self._new_tenant(tenant)
        return tenant

    async def expire(self, tenant: str, job_id: str) -> None:
        """Make the job's claim older than the lease, as time would."""
        await self._expire(tenant, job_id)

    async def sever(self, lead: Lead) -> None:
        """The holder of the lead dies without releasing it."""
        await self._sever(lead)


@pytest.fixture
async def memory_backend() -> Backend:
    memory = MemoryPersistence()
    clock = SystemClock()
    queue = MemoryQueue(memory, clock, lease_seconds=LEASE_SECONDS, max_attempts=2)

    async def nothing(tenant: str) -> None:
        pass

    async def expire(tenant: str, job_id: str) -> None:
        from datetime import timedelta

        table = memory.table("job", tenant)
        row = table[job_id]
        assert row.claimed_at is not None
        table[job_id] = row.model_copy(
            update={"claimed_at": row.claimed_at - timedelta(seconds=LEASE_SECONDS + 1)}
        )

    async def sever(lead: Lead) -> None:
        lead.drop()  # type: ignore[attr-defined]

    return Backend("memory", memory, queue, MemoryLeadership(), nothing, expire, sever)


@pytest.fixture
async def postgres_backend(postgres_url: str) -> AsyncIterator[Backend]:
    postgres = PostgresPersistence(postgres_url, pool_size=3)
    queue = PostgresQueue(postgres, lease_seconds=LEASE_SECONDS, max_attempts=2)

    async def create_tenant(tenant: str) -> None:
        async with postgres.engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
            )
            await connection.execute(
                text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"),
                {"t": tenant},
            )

    async def expire(tenant: str, job_id: str) -> None:
        async with postgres.engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
            )
            await connection.execute(
                text(
                    "UPDATE job SET claimed_at = claimed_at - make_interval(secs => :s) "
                    "WHERE tenant = :t AND id = :j"
                ),
                {"s": LEASE_SECONDS + 1, "t": tenant, "j": job_id},
            )

    async def sever(lead: Lead) -> None:
        await lead.sever()  # type: ignore[attr-defined]

    try:
        yield Backend(
            "postgres",
            postgres,
            queue,
            PostgresLeadership(postgres.engine),
            create_tenant,
            expire,
            sever,
        )
    finally:
        await postgres.close()


@pytest.fixture(params=IMPLEMENTATIONS)
def backend(request: pytest.FixtureRequest) -> Backend:
    chosen: Backend = request.getfixturevalue(f"{request.param}_backend")
    return chosen


type Fixture = Any
