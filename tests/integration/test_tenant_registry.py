"""Tenants are created by a command and kept in the database (ADR-0104, issue #318).

A daemon runs every role against a database of this test's own, with no `TAKTUS_TENANTS`. An
administrator creates one tenant on the HTTP surface and another with `taktusctl tenant
create`, while the daemon runs. Without a restart, the new tenant is served by every role:
the scheduler fires its time trigger, the runner executes the run, and the HTTP surface admits
a reader of it. Each creation is the first entry of the new tenant's chain, and the identifier
is the one Taktus generated.

The database is the test's own because the shared one holds every other test's tenants, and
an instance that serves its whole registry would serve them too.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from sqlalchemy.engine import make_url

from taktus.adapters.driven.postgres.migrate import configuration
from taktus.components.run.domain.model import RunState
from taktus.composition.daemon import Wired

from .conftest import free_port
from .test_daemon_scaling import rule_only_bundle, settings, until
from .test_first_slice import PLAIN, taktusctl
from .test_time_triggers import (
    Daemon,
    ManualClock,
    _armed,
    _count,
    eventually,
    registered,
    runs_of,
)

KEY = "adm-a-random-value-for-this-test"


@pytest.fixture
async def own_database(postgres_url: str) -> AsyncIterator[str]:
    name = f"tenant_registry_{os.urandom(4).hex()}"
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


def tenant_command(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, **PLAIN, "TAKTUS_DATABASE_URL": url}
    environment.pop("TAKTUS_TENANTS", None)
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "tenant", *arguments],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


async def first_entry(wired: Wired, tenant: str) -> tuple[str, str | None]:
    async with wired.work.transaction(tenant):
        [first, *_] = await wired.ledger.entries(tenant)
    return first.kind, first.refs.actor


async def test_a_tenant_created_while_the_daemon_runs_is_served_by_every_role(
    own_database: str, tmp_path: Path
) -> None:
    key_file = tmp_path / "administration-key"
    key_file.write_text(KEY, encoding="utf-8")
    clock = ManualClock(datetime(2026, 10, 18, 10, 30, tzinfo=UTC))
    port = free_port()
    daemon = Daemon(
        settings(
            own_database,
            tmp_path,
            TAKTUS_INSTANCE="registry",
            TAKTUS_HTTP_PORT=str(port),
            TAKTUS_ROLES="api,runner,scheduler,automation",
            TAKTUS_TENANTS="",
            TAKTUS_ADMINISTRATION_KEY_FILE=str(key_file),
        ),
        clock,
    )
    await daemon.start()
    try:
        assert daemon.wired is not None
        wired = daemon.wired
        await until(lambda: daemon.leading)
        assert await wired.tenants.served() == ("default",)
        base = f"http://127.0.0.1:{port}"
        admin = {"Authorization": f"Bearer {KEY}"}

        async with httpx.AsyncClient(base_url=base, timeout=10) as http:
            created = await http.post(
                "/administration/tenants",
                json={"name": "Second tenant", "by": "idn_admin"},
                headers=admin,
            )
            assert created.status_code == 201, created.text
            tenant = created.json()["id"]
            assert tenant.startswith("tnt_") and len(tenant) == 24
            assert await first_entry(wired, tenant) == ("tenant.created", "idn_admin")

            # The scheduler: a trigger of the new tenant is armed and fires when due.
            bundle = rule_only_bundle(0)
            bundle["id"] = "hourly-in-a-new-tenant"
            bundle["triggers"] = [{"schedule": "hourly"}]
            version = await registered(wired, tenant, bundle)
            await eventually(lambda: _armed(wired, tenant))
            clock.current = datetime(2026, 10, 18, 11, 0, 30, tzinfo=UTC)
            await eventually(lambda: _count(wired, tenant, version.ref, 1))

            # The runner: the run the trigger started is executed.
            async def finished() -> bool:
                runs = await runs_of(wired, tenant, version.ref)
                return bool(runs) and all(r.state is RunState.FINISHED for r in runs)

            await eventually(finished)

            # The HTTP surface: a reader of the new tenant sees the run.
            _, reader = await wired.identities.add(tenant, "idn_reader", (tenant,))
            listed = await http.get("/runs", headers={"Authorization": f"Bearer {reader}"})
            assert listed.status_code == 200, listed.text
            [run] = await runs_of(wired, tenant, version.ref)
            assert run.id in {r["id"] for r in listed.json()["runs"]}

            # The command line creates one too, against the same database, while the daemon
            # runs; the daemon serves it at its next round.
            made = await asyncio.to_thread(tenant_command, own_database, "create", "Third")
            assert made.returncode == 0, made.stdout + made.stderr
            third = made.stdout.split()[1]
            assert third.startswith("tnt_") and third != tenant
            # Oldest first by creation time; this test's clock is not the database's, so the
            # order is not what is checked here (tests/components/identity/test_tenants.py).
            assert set(await wired.tenants.served()) == {"default", tenant, third}
            assert await first_entry(wired, third) == ("tenant.created", "idn_test")

            renamed = await asyncio.to_thread(
                tenant_command, own_database, "rename", third, "Third GmbH"
            )
            assert renamed.returncode == 0, renamed.stdout + renamed.stderr
            listing = await http.get("/administration/tenants", headers=admin)
            assert {(t["id"], t["name"]) for t in listing.json()["tenants"]} == {
                ("default", "default"),
                (tenant, "Second tenant"),
                (third, "Third GmbH"),
            }
    finally:
        await daemon.halt()
