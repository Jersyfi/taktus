"""The reference worker as a separate process, for the integration tests of the whole slice.

Deliberately its own small starter and not the conformance gate's: that gate is excluded from
`make test` and belongs to the contract; this belongs to the control plane. The worker is the
same file either way.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes.ports import free_port

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"


@pytest.fixture(autouse=True)
def identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing executes without an identity: the command line names one the tenant knows,
    here through `TAKTUS_IDENTITY`, and a test adds it to its state first
    (`fakes.identity.added_by_command_line`). These tests are about the run, not about who is
    asking; a test that is about the identity deletes the variable itself."""
    monkeypatch.setenv("TAKTUS_IDENTITY", "idn_test")


@pytest.fixture(autouse=True)
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests share one database, and every test tenant is in its registry. A daemon or a
    command line started here serves `default` alone, as before the registry (ADR-0104 §7):
    otherwise every runner would claim every other test's runs. A test about the registry
    gives the variable empty, against a database of its own. Once the variable is removed,
    the tests keep apart in another way."""
    monkeypatch.setenv("TAKTUS_TENANTS", "default")


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
