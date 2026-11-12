"""Ports for the servers a test starts, never the same for two tests of one session.

A port the system chose for a socket that was then closed is free only until someone else takes
it, and the parallel workers of a session (`pytest-xdist`) each asked the system at once: two
tests got the same port, one server exited early, and another test's readiness check was
answered by the wrong server (#360). Each worker therefore counts through a range of its own,
below the range the system hands out by itself (Linux from 32768, macOS from 49152), and skips a
port something else holds. It starts at a place of its own in that range, so that two sessions on
one machine — two checkouts tested at once — count through different ports; CI runs one session
per machine.
"""

from __future__ import annotations

import itertools
import os
import socket

BASE = 20_000
TOP = 32_768
"""Where the system's own range begins on Linux; every worker's range ends below it."""
_workers = os.environ.get("PYTEST_XDIST_WORKER_COUNT", "")
_count = max(int(_workers), 1) if _workers.isdigit() else 8
SPAN = (TOP - BASE) // _count
"""Per worker: the range divided by as many workers as the session runs, so that no two share
ports — `-n auto` on a machine of more than eight cores once wrapped worker 8 onto worker 0."""
_worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0").removeprefix("gw")
_start = BASE + (int(_worker) if _worker.isdigit() else 0) % _count * SPAN
_first = _start + os.getpid() % SPAN
_ports = itertools.cycle([*range(_first, _start + SPAN), *range(_start, _first)])


def free_port() -> int:
    """A port no other test of this session was given and nothing holds now."""
    for _ in range(SPAN):
        port = next(_ports)
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"every port from {_start} to {_start + SPAN - 1} is held")
