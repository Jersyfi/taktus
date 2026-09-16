"""Starting the reference worker for the conformance gate.

The worker is a separate process, reached over HTTP, exactly as a foreign worker would be. The
suite never imports it. Each test gets its own instance on a free port with its own state
directory, its log captured to a file (for W-08) and a random credential value in its
environment (for W-08 as well) — the value is generated here, handed to the suite in memory, and
never written anywhere by the honest worker.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from taktus.conformance import Report, SuiteOptions, run_suite

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"
CREDENTIAL = "TAKTUS_CONFORMANCE_CREDENTIAL"


@dataclass
class RunningWorker:
    endpoint: str
    log: Path
    credential_value: str
    process: subprocess.Popen[bytes]

    def options(self) -> SuiteOptions:
        return SuiteOptions(
            endpoint=self.endpoint,
            credential_value=self.credential_value,
            worker_log=self.log,
            timeout=90.0,
            idle_timeout=30.0,
        )

    async def run_suite(self) -> Report:
        return await run_suite(self.options())


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        return int(port)


def faults() -> list[tuple[str, str]]:
    """Every fault the worker offers, with the check it breaks, from the worker itself."""
    output = subprocess.run(  # noqa: S603 — our own script, fixed arguments
        [sys.executable, str(WORKER), "--list-faults"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [(line.split("\t")[0], line.split("\t")[1]) for line in output.splitlines() if line]


type StartWorker = Callable[..., RunningWorker]


@pytest.fixture
def start_worker(tmp_path: Path) -> Iterator[StartWorker]:
    started: list[subprocess.Popen[bytes]] = []

    def start(*, profile: str = "quick", fault: str | None = None) -> RunningWorker:
        port = free_port()
        log = tmp_path / f"worker-{profile}-{fault or 'honest'}.log"
        value = "conf-" + secrets.token_hex(12)
        env = {**os.environ, CREDENTIAL: value}
        args = [
            sys.executable,
            str(WORKER),
            "--port",
            str(port),
            "--profile",
            profile,
            "--state-dir",
            str(tmp_path / "state"),
            "--step-seconds",
            "0.2",
            "--epoch-seconds",
            "0.3",
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                args, stdout=handle, stderr=subprocess.STDOUT, env=env
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"the worker exited early; see {log}")
            try:
                if httpx.get(f"{endpoint}/v1/health", timeout=1.0).status_code == 200:
                    return RunningWorker(endpoint, log, value, process)
            except httpx.HTTPError:
                time.sleep(0.1)
        raise RuntimeError(f"the worker did not become ready; see {log}")

    yield start
    for process in started:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
