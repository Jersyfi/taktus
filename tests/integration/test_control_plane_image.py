# ruff: noqa: S607 — a test drives the engine's command line
"""The control plane image, built and inspected: it carries no worker code (DEC-0011), and no
worker image carries the control plane. Needs Docker; skips without it (fails in CI, where
Docker is required). `deploy/docker/verify.sh` asks the same question on the way to its run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = "taktus:test"


@pytest.fixture(scope="module")
def control_plane_image(engine_socket: str) -> str:
    command = [
        "docker",
        "build",
        "-q",
        "-f",
        str(ROOT / "deploy/docker/Dockerfile"),
        "-t",
        CONTROL_PLANE,
        str(ROOT),
    ]
    # A build pulls base images and packages; one transient failure is retried once, and a
    # second one fails the test with the engine's own words.
    for attempt in (1, 2):
        completed = subprocess.run(  # noqa: S603 — our own Dockerfile, fixed arguments
            command, capture_output=True, text=True, timeout=900, check=False
        )
        if completed.returncode == 0:
            return CONTROL_PLANE
        if attempt == 2:
            pytest.fail(f"docker build failed twice:\n{completed.stderr[-2000:]}")
    return CONTROL_PLANE  # unreachable


def inside(image: str, script: str) -> str:
    completed = subprocess.run(  # noqa: S603 — a fixed script in our own image
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return completed.stdout


def test_the_control_plane_image_carries_no_worker_code(control_plane_image: str) -> None:
    listing = inside(
        control_plane_image,
        "test -e /app/workers && echo has-workers-dir; "
        "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o "
        "\\( -path '*/workers/*' -not -path '*/src/taktus/*' -o -name fake_agent.py \\) "
        "-print 2>/dev/null; "
        # Every worker of this repository says so in its first lines; the worker *port* of the
        # control plane (src/taktus/ports/worker.py) does not, and belongs there.
        "grep -rl 'separate deployable, as every worker is' /app 2>/dev/null; "
        "ls /app",
    )
    assert "has-workers-dir" not in listing
    assert "/workers/" not in listing and "fake_agent.py" not in listing
    assert "separate deployable" not in listing
    assert "src" in listing and "contracts" in listing, "the control plane itself is there"


def test_the_control_plane_image_runs_the_daemon_and_the_command_line(
    control_plane_image: str,
) -> None:
    assert "taktusctl" in inside(control_plane_image, "ls /app/.venv/bin")
    assert "usage" in inside(control_plane_image, "taktusctl --help").lower()


def test_the_reference_worker_image_carries_no_control_plane(reference_worker_image: str) -> None:
    listing = inside(reference_worker_image, "ls /app; test -e /app/src && echo has-src; true")
    assert "has-src" not in listing and "worker.py" in listing
