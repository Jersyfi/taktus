# ruff: noqa: S603, S607 — a test drives the container engine's command line, fixed arguments
"""One release, two variants, no route outside (UC-10.1, ADR-0284 §7).

The control plane image of this checkout runs the shipped first process,
`examples/processes/first-process.yaml`, unchanged, in two variants that differ in configuration
only:

- **alone** — a container with no network at all, its state in files under a directory;
- **with a database** — a container and a database on a network that has no route outside.

In both, a connection to an address outside fails, the process runs to its end, and the same
steps are executed with the same methods. The run waits for a person at every step (level 2);
each is confirmed as the operator would, with `taktusctl run --resume --approve`.

Inside the container, on Linux, the hardware is read where the kernel lists it: the processors,
the memory, and the graphics and accelerator devices, which are none in an ordinary container.

Needs Docker; skips without it (fails in CI, where Docker is required). The image comes from
tests/images.py, built only when its content changed.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

PROCESS = "examples/processes/first-process.yaml"
IDENTITY = "idn_anywhere"
STEP = re.compile(r"^\s+\d+\s+(\S+)\s+(\S+)\s+\S+\s+(\S+)")
WAITING = re.compile(r"--approve (\S+)\s*$", re.MULTILINE)
OUTSIDE = (
    "import socket\n"
    "try:\n"
    "    socket.create_connection(('192.0.2.1', 443), timeout=3)\n"
    "except OSError as error:\n"
    "    print('closed:', type(error).__name__)\n"
    "else:\n"
    "    print('open')\n"
)
"""A connection to an address outside: 192.0.2.1 is reserved for documentation (RFC 5737), so
an open route would at worst time out, and never reach anyone."""
MIGRATE = (
    "import os\n"
    "from alembic import command\n"
    "from taktus.adapters.driven.postgres.migrate import configuration\n"
    "url = open(os.environ['TAKTUS_DATABASE_URL_FILE']).read().strip()\n"
    "command.upgrade(configuration(url), 'head')\n"
)


def docker(
    *args: str, check: bool = True, timeout: float = 180
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=timeout
    )
    if check and completed.returncode != 0:
        raise AssertionError(f"docker {' '.join(args)}\n{completed.stdout}\n{completed.stderr}")
    return completed


class Variant:
    """One way of running the same image: its network and its configuration."""

    def __init__(self, image: str, network: str, mounts: list[str], environment: dict[str, str]):
        self.image = image
        self.network = network
        self.mounts = mounts
        self.environment = {"TAKTUS_IDENTITY": IDENTITY, "NO_COLOR": "1", **environment}

    def run(self, entrypoint: str, *args: str) -> subprocess.CompletedProcess[str]:
        flags = ["--rm", "--network", self.network, "--entrypoint", entrypoint]
        for mount in self.mounts:
            flags += ["-v", mount]
        for name, value in self.environment.items():
            flags += ["-e", f"{name}={value}"]
        return docker("run", *flags, self.image, *args, check=False)

    def ctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run("taktusctl", *args)


def executed(variant: Variant) -> list[tuple[str, str, str]]:
    """The first process run to its end: every waiting step confirmed. The steps as the last
    invocation printed them — id, method, state."""
    added = variant.ctl("identity", "add", IDENTITY)
    assert added.returncode == 0, added.stdout + added.stderr
    shown = variant.ctl("run", "--process", PROCESS)
    run_id = re.search(r"^run (run_\S+)", shown.stdout, re.MULTILINE)
    assert run_id is not None, shown.stdout + shown.stderr
    for _ in range(6):
        if shown.returncode == 0:
            break
        assert shown.returncode == 3, shown.stdout + shown.stderr
        step = WAITING.search(shown.stdout)
        assert step is not None, shown.stdout
        shown = variant.ctl(
            "run", "--process", PROCESS, "--resume", run_id.group(1), "--approve", step.group(1)
        )
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert re.search(r"state\s+finished", shown.stdout), shown.stdout
    block = shown.stdout.split("\nsteps\n", 1)[1].split("\n\n", 1)[0]
    return [match.groups() for line in block.splitlines() if (match := STEP.match(line))]


@pytest.fixture
def alone(control_plane_image: str, tmp_path: Path) -> Variant:
    state = tmp_path / "state"
    state.mkdir()
    state.chmod(0o777)  # the image's user, 999, writes there
    return Variant(control_plane_image, "none", [f"{state}:/state"], {"TAKTUS_STATE_DIR": "/state"})


@pytest.fixture
def with_a_database(control_plane_image: str, tmp_path: Path) -> Iterator[Variant]:
    name = f"taktus-anywhere-{uuid.uuid4().hex[:8]}"
    docker("network", "create", "--internal", name)
    database = f"{name}-db"
    try:
        docker(
            "run", "-d", "--rm", "--network", name, "--name", database,
            "-e", "POSTGRES_USER=taktus", "-e", "POSTGRES_DB=taktus",
            "-e", "POSTGRES_PASSWORD=anywhere", "postgres:16-alpine",
        )  # fmt: skip
        deadline = time.monotonic() + 60
        while docker("exec", database, "pg_isready", "-U", "taktus", check=False).returncode:
            assert time.monotonic() < deadline, "the database did not become ready"
            time.sleep(1)
        url = tmp_path / "database_url"
        url.write_text(f"postgresql://taktus:anywhere@{database}:5432/taktus\n", encoding="utf-8")
        url.chmod(0o644)
        variant = Variant(
            control_plane_image,
            name,
            [f"{url}:/run/secrets/database_url:ro"],
            {"TAKTUS_DATABASE_URL_FILE": "/run/secrets/database_url"},
        )
        migrated = variant.run("python", "-c", MIGRATE)
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        yield variant
    finally:
        docker("rm", "-f", database, check=False)
        docker("network", "rm", name, check=False)


def test_the_same_process_runs_unchanged_in_two_variants_with_no_route_outside(
    alone: Variant, with_a_database: Variant
) -> None:
    for variant in (alone, with_a_database):
        reach = variant.run("python", "-c", OUTSIDE)
        assert reach.stdout.startswith("closed:"), reach.stdout + reach.stderr
    first = executed(alone)
    second = executed(with_a_database)
    assert first == second, (first, second)
    assert [step for step, _, _ in first] == ["greet", "settle", "confirm"]
    assert {state for _, _, state in first} == {"succeeded"}
    assert alone.ctl("run", "--help").returncode == 0  # one image: the same command line in both


def test_inside_a_linux_container_the_hardware_is_read_from_the_kernel(alone: Variant) -> None:
    shown = alone.ctl("hardware", "--json")
    assert shown.returncode == 0, shown.stdout + shown.stderr
    machine = json.loads(shown.stdout)["inventory"]
    assert machine["system"].startswith("Linux")
    assert machine["processors"]["count"] >= 1
    assert machine["memory_bytes"] > 0 and machine["memory_source"] == "/proc/meminfo MemTotal"
    assert machine["accelerators_unobserved"] is None, "on Linux the device classes are read"
