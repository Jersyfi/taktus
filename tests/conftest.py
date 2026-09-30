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

import images
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


def built(image: images.Image) -> str:
    """The content tag of a test image, built first only when its content changed
    (tests/images.py).

    A build that fails, times out or stalls fails the test with the diagnosis — the image, the
    step it stopped in, the last lines, the log — locally as in CI: a hung build is a finding,
    not a skip. The first test that needs the image reports it in full; every later one in the
    session fails with one line pointing there. Without Docker the test has already skipped
    (or failed under TAKTUS_REQUIRE_DATABASE) through `engine_socket`."""
    try:
        return images.ensure(image)
    except images.ImageBuildError as error:
        message = str(error)
    pytest.fail(message, pytrace=False)  # outside the handler: the diagnosis once, not chained


@pytest.fixture
def reference_worker_image(engine_socket: str) -> str:
    """The reference worker's own image, from workers/script/Dockerfile."""
    return built(images.REFERENCE_WORKER)


@pytest.fixture
def control_plane_image(engine_socket: str) -> str:
    """The control plane image, from deploy/docker/Dockerfile."""
    return built(images.CONTROL_PLANE)


@pytest.fixture
def hog_image(engine_socket: str) -> str:
    """A unit that takes more memory than its limit, from tests/adapters/execution/hog/."""
    return built(images.HOG)
