# ruff: noqa: S607 — a test drives the engine's command line
"""The control plane image, built and inspected: it carries no worker code (DEC-0011), and no
worker image carries the control plane. Needs Docker; skips without it (fails in CI, where
Docker is required). The images come from tests/images.py, built only when their content
changed. `deploy/docker/verify.sh` asks the same question on the way to its run."""

from __future__ import annotations

import subprocess
from collections.abc import Callable


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


# --- connectors: images of their own (ADR-0158, issue #339) -------------------------------------


def test_the_control_plane_image_carries_no_connector_code(control_plane_image: str) -> None:
    """No connector served as an MCP server is in the control plane image: no connectors/
    directory, no package of theirs, and none importable. What stays is the port's side —
    the MCP client, the pool, the loopback and the directory connector (ADR-0158)."""
    listing = inside(
        control_plane_image,
        "test -e /app/connectors && echo has-connectors-dir; "
        "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o "
        "-name taktus_connectors -print 2>/dev/null; "
        "ls /app/src/taktus/adapters/driven/connectors; "
        "python -c 'import taktus_connectors' 2>&1 | tail -1; "
        "python -c 'import taktus.adapters.driven.connectors.mcp' && echo client-importable",
    )
    assert "has-connectors-dir" not in listing
    assert "/taktus_connectors" not in listing, listing
    assert "No module named 'taktus_connectors'" in listing, listing
    assert "client-importable" in listing, "the port's MCP client stays in the control plane"
    shipped = sorted(line for line in listing.splitlines() if line.isidentifier() and line != "mcp")
    assert shipped == ["directory", "loopback"], listing


def test_a_connector_image_carries_its_connector_and_nothing_of_the_control_plane(
    connector_image: Callable[[str], str],
) -> None:
    image = connector_image("stripe")
    listing = inside(
        image,
        "ls /app /app/taktus_connectors; test -e /app/src && echo has-src; "
        "python -c 'import taktus' 2>&1 | tail -1; "
        "python -m taktus_connectors.stripe --list-faults | head -1",
    )
    assert "has-src" not in listing
    assert "No module named 'taktus'" in listing, listing
    assert "serving.py" in listing and "stripe" in listing
    assert "github" not in listing and "slack" not in listing, "no other connector is in it"
    assert "C-01" in listing, "the connector runs from its image"
