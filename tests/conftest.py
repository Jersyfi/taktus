"""Fixtures every test directory may need: a migrated PostgreSQL database, once per session.

PostgreSQL comes from testcontainers; when Docker is not available, every test that asks for
the database skips and says why. `TAKTUS_TEST_DATABASE_URL` points the tests at an existing,
empty database instead of a container — CI without Docker, or a developer's own instance.
Tests keep apart through tenants (the adapter suite makes a fresh one per test; the
integration tests run as `default` and identify their runs by id), so nothing is cleaned
between them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator

import pytest


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
    from alembic import command

    from taktus.adapters.driven.postgres.migrate import configuration

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
