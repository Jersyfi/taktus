"""A claim takes at most its batch, whatever plan PostgreSQL chooses (migration 0010, NTC-0027).

The plan of the claim depends on the table's statistics. When they say the job table is empty —
a fresh database, or one not analysed since it filled — PostgreSQL may run the claim's inner
query once per row of the table, and before revision 0010 one claim with a batch of two then
took every due job. The shared test database has statistics from every other test, so this
test makes a database of its own, analyses its job table while it is empty, and claims.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url

from taktus.adapters.driven.postgres import PostgresPersistence, PostgresQueue
from taktus.adapters.driven.postgres.migrate import configuration
from taktus.ports.queue import RUN_EXECUTE, Job

TENANT = "t_plan"


@pytest.fixture
async def fresh_url(postgres_url: str) -> AsyncIterator[str]:
    name = f"claim_plan_{os.urandom(4).hex()}"
    admin = make_url(postgres_url).set(drivername="postgresql")
    plain = admin.render_as_string(hide_password=False)
    async with await psycopg.AsyncConnection.connect(plain, autocommit=True) as connection:
        await connection.execute(f'CREATE DATABASE "{name}"')
    url = admin.set(database=name).render_as_string(hide_password=False)
    command.upgrade(configuration(url), "head")
    try:
        yield url
    finally:
        async with await psycopg.AsyncConnection.connect(plain, autocommit=True) as connection:
            await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


async def test_a_claim_takes_at_most_its_batch_when_the_statistics_say_empty(
    fresh_url: str,
) -> None:
    persistence = PostgresPersistence(fresh_url, pool_size=2)
    queue = PostgresQueue(persistence)
    try:
        async with persistence.engine.begin() as connection:
            await connection.execute(text("ANALYZE job"))  # empty: the plan that rescans
            await connection.execute(
                text("SELECT set_config('taktus.tenant', :t, true)"), {"t": TENANT}
            )
            await connection.execute(
                text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"),
                {"t": TENANT},
            )
        async with persistence.transaction(TENANT):
            for n in range(10):
                await queue.enqueue(
                    TENANT, Job(id=f"job_{n:02d}", kind=RUN_EXECUTE, payload={"run_id": str(n)})
                )
        async with persistence.transaction(TENANT):
            claimed = [j.id for j in await queue.claim(TENANT, "a", 2)]
        assert claimed == ["job_00", "job_01"], "the batch, the oldest first, and no more"
        async with persistence.transaction(TENANT):
            assert [j.id for j in await queue.claim(TENANT, "b", 3)] == [
                "job_02",
                "job_03",
                "job_04",
            ]
    finally:
        await persistence.close()
