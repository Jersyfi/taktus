"""Fixtures every test directory may need: a migrated PostgreSQL database, once per session.

PostgreSQL comes from testcontainers; when Docker is not available, every test that asks for
the database skips and says why. `TAKTUS_TEST_DATABASE_URL` points the tests at an existing,
empty database instead of a container — CI without Docker, or a developer's own instance.
Tests keep apart through tenants (the adapter suite makes a fresh one per test; the
integration tests run as `default` and identify their runs by id), so nothing is cleaned
between them.

A skip is for a developer's machine. Where the database tests must run — CI — the environment
sets `TAKTUS_REQUIRE_DATABASE=1`, and a missing Docker is then a failure, not a skip: a gate
that goes green because it could not look is broken, not strict (DEC-0004).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

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
        message = f"PostgreSQL tests need Docker for a container: {reason}"
        if os.environ.get("TAKTUS_REQUIRE_DATABASE"):
            pytest.fail(message + " — and TAKTUS_REQUIRE_DATABASE says they may not skip")
        pytest.skip(message)
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        url = container.get_connection_url()
        command.upgrade(configuration(url), "head")
        yield url


@pytest.fixture(scope="session")
def engine_socket() -> str:
    """The container engine's socket, for the container execution adapter's tests. Without
    Docker they skip and say why — unless `TAKTUS_REQUIRE_DATABASE` says Docker is required
    here, as it does in CI, in which case they fail."""
    reason = docker_available()
    if reason is not None:
        message = f"the container execution tests need Docker: {reason}"
        if os.environ.get("TAKTUS_REQUIRE_DATABASE"):
            pytest.fail(message + " — and TAKTUS_REQUIRE_DATABASE says they may not skip")
        pytest.skip(message)
    host = os.environ.get("DOCKER_HOST", "")
    if host.startswith("unix://"):
        return host.removeprefix("unix://")
    return "/var/run/docker.sock"


@pytest.fixture(scope="session")
def reference_worker_image(engine_socket: str) -> str:
    """The reference worker's own image, built once from workers/script/Dockerfile."""
    root = Path(__file__).resolve().parents[1]
    tag = "taktus-worker-script:test"
    dockerfile = root / "workers" / "script" / "Dockerfile"
    subprocess.run(  # noqa: S603 — our own Dockerfile, fixed arguments
        ["docker", "build", "-q", "-f", str(dockerfile), "-t", tag, str(root)],  # noqa: S607
        check=True,
        capture_output=True,
        timeout=600,
    )
    return tag
