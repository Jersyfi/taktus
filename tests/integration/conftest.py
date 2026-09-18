"""The reference worker as a separate process, for the integration tests of the whole slice.

Deliberately its own small starter and not the conformance gate's: that gate is excluded from
`make test` and belongs to the contract; this belongs to the control plane. The worker is the
same file either way.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"


@pytest.fixture(autouse=True)
def provisional_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing executes without an identity: the command line takes the provisional operator
    identity from the environment (DEC-0013), and these tests are about the run, not about
    who is asking. A test that is about the identity deletes the variable itself."""
    monkeypatch.setenv("TAKTUS_PROVISIONAL_IDENTITY", "default=idn_test")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def worker_endpoint(tmp_path: Path) -> Iterator[str]:
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
