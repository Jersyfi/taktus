"""The backup outcomes over the database (ADR-0106): the rows the backup program writes with its
own login are read per tenant, the last success and every failure since, and a tenant's
transaction sees no other tenant's row. The application role may read them and write none."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from taktus.adapters.driven.postgres import PostgresBackupLog, PostgresPersistence

AT = datetime(2026, 10, 18, 3, 17, tzinfo=UTC)


@pytest.fixture
async def postgres(postgres_url: str) -> AsyncIterator[PostgresPersistence]:
    persistence = PostgresPersistence(postgres_url, pool_size=2)
    try:
        yield persistence
    finally:
        await persistence.close()


def fresh() -> str:
    return f"tnt_{os.urandom(10).hex()}"


def name(at: datetime) -> str:
    return "taktus-" + at.strftime("%Y%m%dT%H%M%SZ")


def outcome(sync_engine: Any, tenant: str, hours: int, reason: str | None) -> None:
    """As the backup program records it: its own login, outside row-level security."""
    at = AT + timedelta(hours=hours)
    with sync_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now()) "
                "ON CONFLICT DO NOTHING"
            ),
            {"t": tenant},
        )
        connection.execute(
            text(
                "INSERT INTO backup_outcome (tenant, name, at, outcome, reason) "
                "VALUES (:t, :n, :at, :o, :r)"
            ),
            {"t": tenant, "n": name(at), "at": at, "o": "ok" if reason is None else "failed",
             "r": reason},
        )  # fmt: skip


async def test_the_last_success_and_every_failure_since_of_one_tenant(
    postgres: PostgresPersistence, sync_engine: Any
) -> None:
    mine, other = fresh(), fresh()
    outcome(sync_engine, mine, 0, "store")
    outcome(sync_engine, mine, 24, None)
    outcome(sync_engine, mine, 48, "database")
    outcome(sync_engine, mine, 72, "store")
    outcome(sync_engine, other, 96, None)
    log = PostgresBackupLog(postgres)
    async with postgres.transaction(mine):
        history = await log.history(mine)
    assert history.last_ok is not None and history.last_ok.name == name(AT + timedelta(hours=24))
    assert [o.reason for o in history.failed] == ["store", "database"], "newest first"
    assert history.failed_count == 2
    nobody = fresh()
    async with postgres.transaction(nobody):
        assert (await log.history(nobody)).last_ok is None


async def test_the_application_role_reads_its_own_rows_and_writes_none(
    postgres: PostgresPersistence, sync_engine: Any
) -> None:
    mine, other = fresh(), fresh()
    outcome(sync_engine, other, 0, None)
    outcome(sync_engine, mine, 0, "objects")
    async with postgres.transaction(mine):
        connection = postgres.connection(mine)
        seen = (await connection.execute(text("SELECT tenant FROM backup_outcome"))).all()
    assert {row.tenant for row in seen} == {mine}, "row-level security keeps the rest out"
    with pytest.raises(DBAPIError, match="permission denied"):
        async with postgres.transaction(mine):
            await postgres.connection(mine).execute(
                text(
                    "INSERT INTO backup_outcome (tenant, name, at, outcome) "
                    "VALUES (:t, 'taktus-20261018T000000Z', now(), 'ok')"
                ),
                {"t": mine},
            )
