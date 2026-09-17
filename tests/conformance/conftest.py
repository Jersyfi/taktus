"""Starting the reference adapters for the conformance gate.

The worker and the connector are separate processes, reached over HTTP and over MCP, exactly as
foreign adapters would be. The suite never imports them. Each test gets its own instance on a
free port, its log captured to a file (for W-08 and C-04) and random credential values in its
environment (for the same checks) — the values are generated here, handed to the suite in
memory, and never written anywhere by the honest adapters. The connector talks to the fake
repository service (`tests/fakes/repository_service.py`), started as a process of its own with
the same random token.
"""

from __future__ import annotations

import json
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

from taktus.conformance import (
    ConnectorSuiteOptions,
    Report,
    SuiteOptions,
    run_connector_suite,
    run_suite,
)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"
CONNECTOR = ROOT / "src" / "taktus" / "adapters" / "driven" / "connectors" / "github"
SCENARIO = CONNECTOR / "scenario.json"
FAKE_SERVICE = ROOT / "tests" / "fakes" / "repository_service.py"
CREDENTIAL = "TAKTUS_CONFORMANCE_CREDENTIAL"
# The reference worker reaches nothing by itself; the task declares the host its commands
# would need, so that the main run allows it and W-13 has a host to withdraw.
HOST = "registry.example"
TASK: dict[str, object] = {
    "goal": "Conformance run of the reference worker: do the profile's default work.",
    "acceptance": ["the stream ends with assignment.finished"],
    "inputs": {"hosts": [HOST]},
}
ACTIONS_CREDENTIAL = "REPOSITORY_TOKEN"
INTAKE_CREDENTIAL = "REPOSITORY_WEBHOOK_SECRET"


@dataclass
class RunningWorker:
    endpoint: str
    log: Path
    credential_value: str
    process: subprocess.Popen[bytes]

    def options(self) -> SuiteOptions:
        return SuiteOptions(
            endpoint=self.endpoint,
            task=dict(TASK),
            hosts=(HOST,),
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
    return _list_faults([sys.executable, str(WORKER), "--list-faults"])


def connector_faults() -> list[tuple[str, str]]:
    """Every fault the connector offers, with the check it breaks, from the connector itself."""
    return _list_faults(
        [sys.executable, "-m", "taktus.adapters.driven.connectors.github", "--list-faults"]
    )


def _list_faults(command: list[str]) -> list[tuple[str, str]]:
    output = subprocess.run(  # noqa: S603 — our own code, fixed arguments
        command, capture_output=True, text=True, check=True
    ).stdout
    return [(line.split("\t")[0], line.split("\t")[1]) for line in output.splitlines() if line]


def wait_ready(process: subprocess.Popen[bytes], url: str, log: Path, what: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the {what} exited early; see {log}")
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"the {what} did not become ready; see {log}")


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
    stop_all(started)


def stop_all(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@dataclass
class RunningConnector:
    endpoint: str
    log: Path
    service_url: str
    credential_values: dict[str, str]
    process: subprocess.Popen[bytes]

    def options(self) -> ConnectorSuiteOptions:
        with SCENARIO.open(encoding="utf-8") as handle:
            scenario = json.load(handle)
        return ConnectorSuiteOptions(
            endpoint=self.endpoint,
            scenario=scenario,
            credential_values=self.credential_values,
            adapter_log=self.log,
            timeout=30.0,
            scenario_dir=SCENARIO.parent,
        )

    async def run_suite(self) -> Report:
        return await run_connector_suite(self.options())


type StartConnector = Callable[..., RunningConnector]


@pytest.fixture
def start_connector(tmp_path: Path) -> Iterator[StartConnector]:
    """The fake service and the connector, each a process of its own. The token the connector
    reads under REPOSITORY_TOKEN is the one the fake accepts; the webhook secret is shared with
    the suite, which signs with it."""
    started: list[subprocess.Popen[bytes]] = []

    def start(*, fault: str | None = None) -> RunningConnector:
        token = "tok-" + secrets.token_hex(12)
        secret = "whs-" + secrets.token_hex(12)
        service_port = free_port()
        service_log = tmp_path / f"service-{fault or 'honest'}.log"
        with service_log.open("wb") as handle:
            service = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [sys.executable, str(FAKE_SERVICE), "--port", str(service_port)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "FAKE_REPOSITORY_TOKENS": f"{token}:write"},
            )
        started.append(service)
        service_url = f"http://127.0.0.1:{service_port}"
        wait_ready(service, f"{service_url}/_fake/state", service_log, "fake service")

        port = free_port()
        log = tmp_path / f"connector-{fault or 'honest'}.log"
        args = [
            sys.executable,
            "-m",
            "taktus.adapters.driven.connectors.github",
            "--port",
            str(port),
            "--target",
            service_url,
            "--repository",
            "conformance/target",
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
                args,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, ACTIONS_CREDENTIAL: token, INTAKE_CREDENTIAL: secret},
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/health", log, "connector")
        return RunningConnector(
            f"{endpoint}/mcp",
            log,
            service_url,
            {ACTIONS_CREDENTIAL: token, INTAKE_CREDENTIAL: secret},
            process,
        )

    yield start
    stop_all(started)
