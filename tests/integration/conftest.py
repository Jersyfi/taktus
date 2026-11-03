"""The reference worker as a separate process, for the integration tests of the whole slice.

Deliberately its own small starter and not the conformance gate's: that gate is excluded from
`make test` and belongs to the contract; this belongs to the control plane. The worker is the
same file either way.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from alembic import command
from fakes.ports import free_port
from sqlalchemy.engine import make_url

from taktus.adapters.driven.postgres.migrate import configuration

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing executes without an identity: the command line names one the tenant knows,
    here through `TAKTUS_IDENTITY`, and a test adds it to its state first
    (`fakes.identity.added_by_command_line`). These tests are about the run, not about who is
    asking; a test that is about the identity deletes the variable itself."""
    monkeypatch.setenv("TAKTUS_IDENTITY", "idn_test")


@pytest.fixture(scope="session")
def template(postgres_server: str) -> Iterator[str]:
    """A database migrated once per session and never connected to again, so that PostgreSQL
    can copy it: the template of every integration test's own database."""
    name = f"integration_template_{os.urandom(4).hex()}"
    with administration(postgres_server) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')  # a name of this file's own
    command.upgrade(configuration(database(postgres_server, name)), "head")
    try:
        yield name
    finally:
        with administration(postgres_server) as connection:
            connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture
def postgres_url(postgres_server: str, template: str) -> Iterator[str]:
    """A database of this test's own, copied from the migrated template (#517). A daemon
    serves every tenant of its registry (ADR-0104); on a shared database it would serve, and
    claim the runs of, every other test's tenants. The copy takes a fraction of a second; the
    database is dropped when the test ends, whatever is still connected."""
    name = f"integration_{os.urandom(6).hex()}"
    with administration(postgres_server) as connection:
        connection.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    try:
        yield database(postgres_server, name)
    finally:
        with administration(postgres_server) as connection:
            connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@contextmanager
def administration(server: str) -> Iterator[psycopg.Connection[Any]]:
    """A connection outside a transaction, as CREATE and DROP DATABASE need."""
    plain = make_url(server).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as connection:
        yield connection


def database(server: str, name: str) -> str:
    """The URL of the database `name` on the server of `server`, in the form `server` had."""
    return make_url(server).set(database=name).render_as_string(hide_password=False)


@pytest.fixture
def worker_endpoint(tmp_path: Path) -> Iterator[str]:
    yield from reference_worker(tmp_path)


def reference_worker(tmp_path: Path, *options: str) -> Iterator[str]:
    """Start the reference worker with `options` added, yield its endpoint, stop it."""
    port = free_port()
    log = tmp_path / "worker.log"
    args = [
        sys.executable,
        str(WORKER),
        "--port",
        str(port),
        "--state-dir",
        str(tmp_path / "worker-state"),
        "--step-seconds",
        "0.1",
        *options,
    ]
    with log.open("wb") as handle:
        process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT)  # noqa: S603
    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"the worker exited early; see {log}")
            try:
                if httpx.get(f"{endpoint}/v1/health", timeout=1.0).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"the worker did not become ready; see {log}")
        yield endpoint
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
