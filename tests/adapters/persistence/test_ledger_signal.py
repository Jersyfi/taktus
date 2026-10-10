"""The ledger signal over a PostgreSQL notification (ADR-0055 §2, migration 0027).

An insert into the ledger notifies by a trigger, so that no writer can forget it: once per
tenant a statement wrote, when its transaction commits, with the tenant and nothing else. A
transaction rolled back notifies nothing. The listening connection, lost, is opened again; a
snapshot read with `consistent` sees one state.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from fakes import FakeClock

from adapters.persistence.conftest import Backend
from taktus.adapters.driven.postgres import PostgresLedgerSignal
from taktus.adapters.driven.postgres.signal import APPLICATION_NAME
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

pytestmark = pytest.mark.usefixtures("postgres_url")


@pytest.fixture
def postgres(postgres_backend: Backend) -> Backend:
    return postgres_backend


@pytest.fixture
async def heard(postgres_url: str) -> AsyncIterator[tuple[PostgresLedgerSignal, list[str]]]:
    signal = PostgresLedgerSignal(postgres_url, check_seconds=0.2, retry_seconds=0.1)
    tenants: list[str] = []

    async def listen() -> None:
        async for tenant in signal.tenants():
            tenants.append(tenant)

    listening = asyncio.create_task(listen())
    async with asyncio.timeout(10):
        await signal.listening.wait()
    yield signal, tenants
    listening.cancel()


def fact(run: str) -> Fact:
    return Fact(kind="run.created", refs=LedgerRefs(run_id=run))


async def eventually(condition: Any, seconds: float = 5) -> None:
    async with asyncio.timeout(seconds):
        while not condition():  # noqa: ASYNC110 — the notification arrives on another connection
            await asyncio.sleep(0.02)


async def test_a_commit_notifies_its_tenant_once_and_a_rollback_nothing(
    postgres: Backend, heard: tuple[PostgresLedgerSignal, list[str]]
) -> None:
    _, tenants = heard
    ledger = ChainedLedger(postgres.ledger_store, FakeClock())
    kept, dropped = await postgres.tenant(), await postgres.tenant()
    with pytest.raises(RuntimeError):
        async with postgres.work.transaction(dropped):
            await ledger.record(dropped, fact("run_x"))
            raise RuntimeError("rolled back")
    async with postgres.work.transaction(kept):
        await ledger.record(kept, fact("run_1"))
        await ledger.record(kept, fact("run_2"))
    await eventually(lambda: kept in tenants)
    await asyncio.sleep(0.3)
    assert tenants.count(kept) == 1, "one per tenant and transaction"
    assert dropped not in tenants, "a rolled-back entry sends nothing"


async def test_a_lost_listening_connection_is_opened_again(
    postgres: Backend, postgres_url: str, heard: tuple[PostgresLedgerSignal, list[str]]
) -> None:
    signal, tenants = heard
    async with await psycopg.AsyncConnection.connect(postgres_url, autocommit=True) as admin:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = %s",
            (APPLICATION_NAME,),
        )
    await eventually(lambda: not signal.listening.is_set(), seconds=5)
    await eventually(signal.listening.is_set, seconds=5)
    tenant = await postgres.tenant()
    async with postgres.work.transaction(tenant):
        await ChainedLedger(postgres.ledger_store, FakeClock()).record(tenant, fact("run_1"))
    await eventually(lambda: tenant in tenants)


async def test_a_consistent_read_sees_one_state_whatever_commits_meanwhile(
    postgres: Backend,
) -> None:
    """What a snapshot and its position are read in (ADR-0055 §4): an entry committed between
    two of its reads is in neither."""
    tenant = await postgres.tenant()
    ledger = ChainedLedger(postgres.ledger_store, FakeClock())
    async with postgres.work.transaction(tenant):
        await ledger.record(tenant, fact("run_1"))
    committed = asyncio.Event()

    async def meanwhile() -> None:
        async with postgres.work.transaction(tenant):
            await ledger.record(tenant, fact("run_2"))
        committed.set()

    async with postgres.work.transaction(tenant, consistent=True):
        first = await postgres.ledger_store.head(tenant)
        await asyncio.create_task(meanwhile(), context=contextvars.Context())
        assert committed.is_set()
        assert await postgres.ledger_store.head(tenant) == first == 1
        assert [e.seq for e in await postgres.ledger_store.after(tenant, 0, limit=5)] == [1]
    async with postgres.work.transaction(tenant):
        assert await postgres.ledger_store.head(tenant) == 2
