"""What the database enforces on its own, without the adapter's cooperation: a raw statement
sees only its tenant, the ledger and the provenance refuse to change, the chain behind an
artifact is one statement, the schema matches the metadata, and two instances append to one
chain in sequence."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fakes import FakeClock
from sqlalchemy import event, text
from sqlalchemy.exc import ProgrammingError

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    SchemaOutOfDate,
    check_schema,
)
from taktus.adapters.driven.postgres._schema import metadata
from taktus.adapters.driven.postgres.migrate import current_revision, head_revision
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.domain.model import Run
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

pytestmark = pytest.mark.usefixtures("postgres_url")


@pytest.fixture
def postgres(postgres_backend: Backend) -> Backend:
    return postgres_backend


async def test_a_raw_statement_as_the_application_sees_only_its_tenant(
    postgres: Backend, sync_engine: Any
) -> None:
    a, b = await postgres.tenant(), await postgres.tenant()
    runs = postgres.repository(Run)
    async with postgres.work.transaction(a):
        await runs.put(a, samples.run("run_a", tenant=a))
    async with postgres.work.transaction(b):
        await runs.put(b, samples.run("run_b", tenant=b))

    def as_application(tenant: str | None, statement: str) -> list[Any]:
        with sync_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE taktus_app"))
            if tenant is not None:
                connection.execute(
                    text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
                )
            return list(connection.execute(text(statement)))

    # No filter in the statement: the policy filters. No tenant named: nothing at all.
    assert [r.id for r in as_application(a, "SELECT id FROM run")] == ["run_a"]
    assert [r.id for r in as_application(b, "SELECT id FROM run")] == ["run_b"]
    assert as_application(None, "SELECT id FROM run") == []
    assert as_application(a, "SELECT step_id FROM step_run WHERE run_id = 'run_b'") == []
    assert as_application(a, "SELECT id FROM tenant") == [(a,)]
    # Writing another tenant's row is refused by the policy, not by a query's good manners.
    with pytest.raises(ProgrammingError, match="row-level security"):
        as_application(
            a,
            f"INSERT INTO process (tenant, id, name) VALUES ('{b}', 'p', 'smuggled')",  # noqa: S608
        )
    with pytest.raises(ProgrammingError, match="row-level security"):
        as_application(a, f"UPDATE run SET tenant = '{b}' WHERE id = 'run_a'")  # noqa: S608


async def test_the_ledger_rejects_update_and_delete_at_the_database_level(
    postgres: Backend, sync_engine: Any
) -> None:
    tenant = await postgres.tenant()
    ledger = ChainedLedger(postgres.ledger_store, FakeClock(datetime(2026, 9, 16, tzinfo=UTC)))
    async with postgres.work.transaction(tenant):
        await ledger.record(tenant, Fact(kind="run.created", refs=LedgerRefs(run_id="r")))

    def attempt(role: str | None, statement: str) -> None:
        with sync_engine.begin() as connection:
            if role is not None:
                connection.execute(text(f"SET LOCAL ROLE {role}"))
            connection.execute(text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant})
            connection.execute(text(statement))

    # As the application: the privilege was never granted.
    with pytest.raises(ProgrammingError, match="permission denied"):
        attempt("taktus_app", "UPDATE ledger_entry SET kind = 'run.tampered'")
    with pytest.raises(ProgrammingError, match="permission denied"):
        attempt("taktus_app", "DELETE FROM ledger_entry")
    # As the login user, who owns the table: the trigger.
    with pytest.raises(ProgrammingError, match="append-only: UPDATE"):
        attempt(None, "UPDATE ledger_entry SET kind = 'run.tampered'")
    with pytest.raises(ProgrammingError, match="append-only: DELETE"):
        attempt(None, "DELETE FROM ledger_entry")
    with pytest.raises(ProgrammingError, match="append-only: TRUNCATE"):
        attempt(None, "TRUNCATE ledger_entry")
    async with postgres.work.transaction(tenant):
        verification = await ledger.verify(tenant)
        assert verification.intact and verification.entries == 1


async def test_provenance_rejects_update_and_delete_at_the_database_level(
    postgres: Backend, sync_engine: Any
) -> None:
    """A provenance record is written once (ADR-0021 §3): the application role was never
    granted more than insert and read, and the trigger stops the table's owner too."""
    from adapters.persistence.test_provenance_store import record

    tenant = await postgres.tenant()
    async with postgres.work.transaction(tenant):
        await postgres.provenance_store.append(tenant, record("prov_1", "r1", "a", 3))

    def attempt(role: str | None, statement: str) -> None:
        with sync_engine.begin() as connection:
            if role is not None:
                connection.execute(text(f"SET LOCAL ROLE {role}"))
            connection.execute(text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant})
            connection.execute(text(statement))

    with pytest.raises(ProgrammingError, match="permission denied"):
        attempt("taktus_app", "UPDATE provenance SET outputs = '[\"planted\"]'")
    with pytest.raises(ProgrammingError, match="permission denied"):
        attempt("taktus_app", "DELETE FROM provenance")
    with pytest.raises(ProgrammingError, match="written once: UPDATE"):
        attempt(None, "UPDATE provenance SET outputs = '[\"planted\"]'")
    with pytest.raises(ProgrammingError, match="written once: DELETE"):
        attempt(None, "DELETE FROM provenance")
    with pytest.raises(ProgrammingError, match="written once: TRUNCATE"):
        attempt(None, "TRUNCATE provenance")
    async with postgres.work.transaction(tenant):
        kept = await postgres.provenance_store.of_run(tenant, "r1")
        assert [r.outputs for r in kept] == [()]


async def test_the_chain_behind_an_artifact_is_one_statement(postgres: Backend) -> None:
    from adapters.persistence.test_provenance_store import record

    tenant = await postgres.tenant()
    store = postgres.provenance_store
    async with postgres.work.transaction(tenant):
        await store.append(tenant, record("prov_0", "r0", "fetch", 2, outputs=("source",)))
        await store.append(
            tenant, record("prov_1", "r1", "a", 10, result=1, reads=(("r0", "fetch", "source"),))
        )
        await store.append(
            tenant,
            record("prov_2", "r1", "b", 13, outputs=("final",), reads=(("r1", "a", None),)),
        )
    statements: list[str] = []

    def count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    engine = postgres.work.engine.sync_engine  # type: ignore[attr-defined]
    async with postgres.work.transaction(tenant):
        event.listen(engine, "before_cursor_execute", count)
        try:
            walked = await store.chain(tenant, "r1", "final")
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert [r.step_id for r in walked] == ["b", "a", "fetch"]
    assert len(statements) == 1, statements
    assert "WITH RECURSIVE" in statements[0]


def test_the_migrated_schema_matches_the_adapter_s_metadata(sync_engine: Any) -> None:
    """The migrations are the history, `_schema.py` the current shape; a change to one without
    the other is a red test here."""
    with sync_engine.connect() as connection:
        drift = compare_metadata(MigrationContext.configure(connection), metadata)
    assert drift == [], drift


async def test_the_revision_check_names_what_is_missing(
    postgres_url: str, sync_engine: Any
) -> None:
    persistence = PostgresPersistence(postgres_url, pool_size=1)
    try:
        await check_schema(persistence.engine)
        assert await current_revision(persistence.engine) == head_revision() == "0003"
        with sync_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '0000'"))
        try:
            with pytest.raises(SchemaOutOfDate, match=r"at schema revision 0000.*needs 0003"):
                await check_schema(persistence.engine)
        finally:
            with sync_engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num = '0003'"))
    finally:
        await persistence.close()


async def test_two_instances_append_to_one_chain_in_sequence(postgres_url: str) -> None:
    """Two persistence objects are two instances. Each records into the same tenant's chain
    at the same time; the store's claim in `last` makes them take turns, so that both land,
    in sequence, and the chain verifies."""
    one = PostgresPersistence(postgres_url, pool_size=2)
    two = PostgresPersistence(postgres_url, pool_size=2)
    tenant = f"t_{datetime.now(UTC).timestamp():.0f}_race"
    async with one.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now())"), {"t": tenant}
        )
    clock = FakeClock(datetime(2026, 9, 16, tzinfo=UTC))
    ledgers = [
        ChainedLedger(PostgresLedgerStore(one), clock),
        ChainedLedger(PostgresLedgerStore(two), clock),
    ]

    async def record(instance: PostgresPersistence, ledger: ChainedLedger, n: int) -> None:
        for i in range(n):
            async with instance.transaction(tenant):
                await ledger.record(
                    tenant, Fact(kind="run.created", refs=LedgerRefs(run_id=f"r{i}"))
                )
                await asyncio.sleep(0)  # give the other instance its chance to interleave

    try:
        await asyncio.gather(record(one, ledgers[0], 20), record(two, ledgers[1], 20))
        async with one.transaction(tenant):
            verification = await ledgers[0].verify(tenant)
            assert verification.entries == 40
            assert verification.intact, verification.findings
    finally:
        await one.close()
        await two.close()
