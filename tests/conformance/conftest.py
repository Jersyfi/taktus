"""Starting the reference adapters for the conformance gate.

The worker and the connector are separate processes, reached over HTTP and over MCP, exactly as
foreign adapters would be. The suite never imports them. Each test gets its own instance on a
free port, its log captured to a file (for W-08 and C-04) and random credential values in its
environment (for the same checks) — the values are generated here, handed to the suite in
memory, and never written anywhere by the honest adapters. The connector talks to the fake
repository service (`tests/fakes/repository_service.py`), started as a process of its own with
the same random token — or, in the app mode (ADR-0033), with the public half of a key generated
here, whose private half the connector reads from a file and signs with.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import random
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from taktus.adapters.driven.clock import SystemClock
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.adapters.driven.models.pool import StaticModelPool
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.application.service import RunConformance, RunConformanceHandler
from taktus.components.catalog.domain.model import AdapterMaturity, Configuration
from taktus.components.ledger.application.service import ChainedLedger
from taktus.composition.conformance import InstanceSuites, worker_target
from taktus.composition.pools import Pools
from taktus.composition.settings import load_execution
from taktus.conformance import (
    ConnectorSuiteOptions,
    Report,
    SuiteOptions,
    run_connector_suite,
    run_suite,
)
from taktus.shared.v1 import LedgerEntry

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "script" / "worker.py"
CODING_WORKER = ROOT / "workers" / "claudecode" / "worker.py"
FAKE_AGENT = ROOT / "workers" / "claudecode" / "fake_agent.py"
MLBENCH_WORKER = ROOT / "workers" / "mlbench" / "worker.py"
SECOND_CODING_WORKER = ROOT / "workers" / "codex" / "worker.py"
SECOND_FAKE_AGENT = ROOT / "workers" / "codex" / "fake_agent.py"
CODING_CREDENTIAL = {"api-key": "CODING_AGENT_API_KEY", "session": "CODING_AGENT_SESSION"}
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
APP_KEY_CREDENTIAL = "REPOSITORY_APP_KEY"


@dataclass
class RunningWorker:
    endpoint: str
    log: Path
    credential_value: str
    process: subprocess.Popen[bytes]
    credential_name: str = CREDENTIAL
    task: dict[str, object] | None = None  # None: TASK
    hosts: tuple[str, ...] = (HOST,)

    def options(self) -> SuiteOptions:
        return SuiteOptions(
            endpoint=self.endpoint,
            task=dict(self.task or TASK),
            hosts=self.hosts,
            credential_name=self.credential_name,
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


def coding_faults(worker: Path = CODING_WORKER) -> list[tuple[str, str]]:
    return _list_faults([sys.executable, str(worker), "--list-faults"])


def mlbench_faults() -> list[tuple[str, str]]:
    return _list_faults([sys.executable, str(MLBENCH_WORKER), "--list-faults"])


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

    def start(
        *, profile: str = "quick", fault: str | None = None, estimate_factor: float = 0.5
    ) -> RunningWorker:
        """`estimate_factor` below 1 makes the worker underestimate, so that the suite's tight
        run can make it cross a limit its estimate fits (W-14); above 1 it never can."""
        port = free_port()
        log = tmp_path / f"worker-{profile}-{fault or 'honest'}-{estimate_factor}.log"
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
            "--estimate-factor",
            str(estimate_factor),
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


@pytest.fixture
def start_coding_worker(tmp_path: Path) -> Iterator[StartWorker]:
    """The coding worker against the fake agent, in either authentication mode. The credential
    the suite references is the one the worker's authentication needs, with a random value
    that reaches the worker through its environment and the agent under its own variable —
    and must appear nowhere the suite can see (W-08). `agent_env` reaches the fake agent
    through the worker: the two variables that make it misbehave on purpose."""
    started: list[subprocess.Popen[bytes]] = []
    yield coding_starter(tmp_path, started, CODING_WORKER, FAKE_AGENT)
    stop_all(started)


@pytest.fixture
def start_second_coding_worker(tmp_path: Path) -> Iterator[StartWorker]:
    """The second coding worker (`workers/codex/`) against its own fake agent, started the
    way the first one is (#154)."""
    started: list[subprocess.Popen[bytes]] = []
    yield coding_starter(tmp_path, started, SECOND_CODING_WORKER, SECOND_FAKE_AGENT)
    stop_all(started)


def coding_starter(
    tmp_path: Path, started: list[subprocess.Popen[bytes]], worker: Path, agent: Path
) -> StartWorker:
    name_of = worker.parent.name

    def start(
        *, auth: str = "api-key", fault: str | None = None, agent_env: dict[str, str] | None = None
    ) -> RunningWorker:
        port = free_port()
        log = tmp_path / f"{name_of}-{auth}-{fault or 'honest'}.log"
        name = CODING_CREDENTIAL[auth]
        value = "conf-" + secrets.token_hex(12)
        env = {**os.environ, name: value, **(agent_env or {})}
        args = [
            sys.executable,
            str(worker),
            "--port",
            str(port),
            "--auth",
            auth,
            "--agent",
            f"{sys.executable} {agent}",
            "--state-dir",
            str(tmp_path / f"{name_of}-state-{auth}-{fault or 'honest'}"),
            "--estimate-steps",
            "8",
            "--estimate-currency",
            "0.5",
            "--agent-env",
            ",".join(agent_env or {}),
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                args, stdout=handle, stderr=subprocess.STDOUT, env=env
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/v1/health", log, "coding worker")
        return RunningWorker(endpoint, log, value, process, credential_name=name)

    return start


@pytest.fixture
def start_mlbench_worker(tmp_path: Path) -> Iterator[StartWorker]:
    """The ML bench, and a file server in this process that serves it a labelled dataset. The
    task trains on that dataset, read from the server's host, which the main run allows and
    the narrowed run withdraws (W-13). An epoch holds its place for 0.2 s and the estimate is
    half the expected demand, so that a stop lands mid-training (W-06) and a limit equal to the
    estimate is crossed (W-14)."""
    started: list[subprocess.Popen[bytes]] = []
    served = tmp_path / "served"
    served.mkdir()
    data = dataset_csv(rows=600, features=6, classes=3, seed=11)
    (served / "train.csv").write_bytes(data)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietFiles, directory=str(served))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{server.server_port}"
    task: dict[str, object] = {
        "goal": "Conformance run of the ML bench: train a classifier on the served dataset.",
        "acceptance": ["a model artifact with its metrics"],
        "inputs": {
            "operation": "train",
            "dataset": {
                "uri": f"http://{host}/train.csv",
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "rows": 600,
                "features": 6,
            },
            "epochs": 3,
            "seed": 7,
        },
    }

    def start(*, fault: str | None = None) -> RunningWorker:
        port = free_port()
        log = tmp_path / f"mlbench-{fault or 'honest'}.log"
        value = "conf-" + secrets.token_hex(12)
        env = {**os.environ, CREDENTIAL: value}
        args = [
            sys.executable,
            str(MLBENCH_WORKER),
            "--port",
            str(port),
            "--state-dir",
            str(tmp_path / f"mlbench-state-{fault or 'honest'}"),
            "--epoch-floor",
            "0.2",
            "--estimate-factor",
            "0.5",
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                args, stdout=handle, stderr=subprocess.STDOUT, env=env
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/v1/health", log, "ML bench")
        return RunningWorker(endpoint, log, value, process, task=task, hosts=(host,))

    yield start
    stop_all(started)
    server.shutdown()
    server.server_close()


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def dataset_csv(*, rows: int, features: int, classes: int, seed: int) -> bytes:
    """A labelled dataset a linear classifier can learn: one centre per class, rows scattered
    around it, drawn from the seed."""
    rng = random.Random(seed)  # noqa: S311 — test data drawn from a seed, not a secret
    centres = [[rng.uniform(-3, 3) for _ in range(features)] for _ in range(classes)]
    lines = [",".join([*(f"f{k}" for k in range(1, features + 1)), "label"])]
    for row in range(rows):
        label = row % classes
        values = [c + rng.gauss(0, 1.0) for c in centres[label]]
        lines.append(",".join([*(f"{v:.6f}" for v in values), f"class-{label}"]))
    return ("\n".join(lines) + "\n").encode()


def key_pair() -> tuple[str, str]:
    """An RSA key pair for the app, as PEM: the private half, the public half."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


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
    scenario: Path = SCENARIO

    def options(self) -> ConnectorSuiteOptions:
        with self.scenario.open(encoding="utf-8") as handle:
            scenario = json.load(handle)
        return ConnectorSuiteOptions(
            endpoint=self.endpoint,
            scenario=scenario,
            credential_values=self.credential_values,
            adapter_log=self.log,
            timeout=30.0,
            scenario_dir=self.scenario.parent,
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

    def start(*, fault: str | None = None, app: bool = False) -> RunningConnector:
        token = "tok-" + secrets.token_hex(12)
        secret = "whs-" + secrets.token_hex(12)
        name = f"{fault or 'honest'}{'-app' if app else ''}"
        service_env = {**os.environ, "FAKE_REPOSITORY_TOKENS": f"{token}:write"}
        connector_env = {**os.environ, ACTIONS_CREDENTIAL: token, INTAKE_CREDENTIAL: secret}
        values = {ACTIONS_CREDENTIAL: token, INTAKE_CREDENTIAL: secret}
        if app:
            # The app's key pair: the fake verifies with the public half, the connector signs
            # with the private half from a file. No token is in the connector's environment.
            private, public = key_pair()
            key_file = tmp_path / f"app-key-{name}.pem"
            key_file.write_text(private, encoding="utf-8")
            key_file.chmod(0o600)
            public_file = tmp_path / f"app-public-{name}.pem"
            public_file.write_text(public, encoding="utf-8")
            app_id = str(100000 + secrets.randbelow(900000))
            service_env = {**os.environ, "FAKE_REPOSITORY_APP": f"{app_id}:{public_file}"}
            connector_env = {
                **os.environ,
                INTAKE_CREDENTIAL: secret,
                "TAKTUS_REPOSITORY_APP_ID": app_id,
                "TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE": str(key_file),
            }
            connector_env.pop(ACTIONS_CREDENTIAL, None)
            values = {APP_KEY_CREDENTIAL: private, INTAKE_CREDENTIAL: secret}
        service_port = free_port()
        service_log = tmp_path / f"service-{name}.log"
        with service_log.open("wb") as handle:
            service = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [sys.executable, str(FAKE_SERVICE), "--port", str(service_port)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=service_env,
            )
        started.append(service)
        service_url = f"http://127.0.0.1:{service_port}"
        wait_ready(service, f"{service_url}/_fake/state", service_log, "fake service")

        port = free_port()
        log = tmp_path / f"connector-{name}.log"
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
                env=connector_env,
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/health", log, "connector")
        return RunningConnector(f"{endpoint}/mcp", log, service_url, values, process)

    yield start
    stop_all(started)


CHAT_CONNECTOR = ROOT / "src" / "taktus" / "adapters" / "driven" / "connectors" / "slack"
CHAT_SCENARIO = CHAT_CONNECTOR / "scenario.json"
FAKE_CHAT = ROOT / "tests" / "fakes" / "chat_service.py"
CHAT_ACTIONS = "CHAT_TOKEN"
CHAT_INTAKE = "CHAT_SIGNING_SECRET"


def chat_connector_faults() -> list[tuple[str, str]]:
    """Every fault the chat connector offers, with the check it breaks, from the connector."""
    return _list_faults(
        [sys.executable, "-m", "taktus.adapters.driven.connectors.slack", "--list-faults"]
    )


@pytest.fixture
def start_chat_connector(tmp_path: Path) -> Iterator[StartConnector]:
    """The fake chat service and the chat connector, each a process of its own. The token the
    connector reads under CHAT_TOKEN is the one the fake accepts; the signing secret reaches the
    connector through the file `TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE` names, as every
    secret does, and the suite signs with the same value."""
    started: list[subprocess.Popen[bytes]] = []

    def start(*, fault: str | None = None) -> RunningConnector:
        token = "tok-" + secrets.token_hex(12)
        secret = "sig-" + secrets.token_hex(12)
        name = fault or "honest"
        secret_file = tmp_path / f"chat-signing-secret-{name}"
        secret_file.write_text(secret, encoding="utf-8")
        secret_file.chmod(0o600)
        service_env = {**os.environ, "FAKE_CHAT_TOKENS": f"{token}:write"}
        connector_env = {
            **os.environ,
            CHAT_ACTIONS: token,
            "TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE": str(secret_file),
        }
        connector_env.pop(CHAT_INTAKE, None)
        connector_env.pop("TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE", None)
        service_port = free_port()
        service_log = tmp_path / f"chat-service-{name}.log"
        with service_log.open("wb") as handle:
            service = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [sys.executable, str(FAKE_CHAT), "--port", str(service_port)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=service_env,
            )
        started.append(service)
        service_url = f"http://127.0.0.1:{service_port}"
        wait_ready(service, f"{service_url}/_fake/state", service_log, "fake chat service")

        port = free_port()
        log = tmp_path / f"chat-connector-{name}.log"
        args = [
            sys.executable,
            "-m",
            "taktus.adapters.driven.connectors.slack",
            "--port",
            str(port),
            "--target",
            service_url,
        ]
        if fault:
            args += ["--fault", fault]
        with log.open("wb") as handle:
            process = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
                args, stdout=handle, stderr=subprocess.STDOUT, env=connector_env
            )
        started.append(process)
        endpoint = f"http://127.0.0.1:{port}"
        wait_ready(process, f"{endpoint}/health", log, "chat connector")
        values = {CHAT_ACTIONS: token, CHAT_INTAKE: secret}
        return RunningConnector(
            f"{endpoint}/mcp", log, service_url, values, process, scenario=CHAT_SCENARIO
        )

    yield start
    stop_all(started)


# --- the instance runs the suite and records it (ADR-0044) ----------------------------------------


@dataclass
class Recorded:
    """What the instance recorded after it ran a suite: the maturity record, the ledger entry,
    and the evidence the entry's digest names — the report with its configuration."""

    maturity: AdapterMaturity
    entry: LedgerEntry
    evidence: dict[str, Any]
    current: Configuration | None

    @property
    def report(self) -> dict[str, Any]:
        report: dict[str, Any] = self.evidence["report"]
        return report

    def failed(self) -> set[str]:
        return {c["id"] for c in self.report["checks"] if c["status"] == "failed"}


async def record(
    adapter: str,
    pools: Pools,
    environment: dict[str, str],
    *,
    worker: str | None = None,
    connectors: dict[str, str] | None = None,
    model_endpoint: str | None = None,
    state_dir: Path,
) -> Recorded:
    """The instance's own path: `InstanceSuites` over the pools and the configuration, the
    catalog's handler over memory stores — the one writer of the conformance half."""
    settings = EnvironmentConfiguration(environment)
    clock = SystemClock()
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), clock)
    objects = MemoryObjectStore()
    target = None
    if worker is not None:
        execution = load_execution(EnvironmentConfiguration({"TAKTUS_WORKER": worker}))
        target = worker_target(execution, settings, state_dir=state_dir)
    handler = RunConformanceHandler(
        InstanceSuites(
            pools=pools,
            settings=settings,
            worker=target,
            connectors=connectors or {},
            model_endpoint=model_endpoint,
        ),
        MemoryRepository(persistence, AdapterMaturity),
        persistence,
        ledger,
        objects,
        clock,
    )
    maturity, entry = await handler.execute(RunConformance(adapter, "t", actor="idn_test"))
    assert entry.content_digest is not None
    evidence = json.loads(await objects.get(entry.content_digest) or b"{}")
    try:
        current = await pools.configuration(adapter)
    except Exception:  # a declaration the run cannot read resolves nothing
        current = None
    return Recorded(maturity, entry, evidence, current)


async def record_worker(worker: RunningWorker, tmp_path: Path) -> Recorded:
    """The instance runs the worker suite against `worker.endpoint`, configured as the suite's
    own options are: the task, the host, the credential and the worker's log."""
    task = tmp_path / "conformance-task.json"
    task.write_text(json.dumps(TASK), encoding="utf-8")
    variable = "TAKTUS_CREDENTIAL_" + worker.credential_name.upper()
    environment = {
        "TAKTUS_CONFORMANCE_WORKER_TASK": str(task),
        "TAKTUS_CONFORMANCE_WORKER_HOSTS": HOST,
        "TAKTUS_CONFORMANCE_WORKER_CREDENTIAL": worker.credential_name,
        variable: worker.credential_value,
        "TAKTUS_CONFORMANCE_WORKER_LOG": str(worker.log),
        "TAKTUS_CONFORMANCE_TIMEOUT": "90",
        "TAKTUS_CONFORMANCE_IDLE_TIMEOUT": "30",
    }
    async with HttpWorker(worker.endpoint) as http:
        pools = Pools(
            StaticWorkerPool([("worker.endpoint", http)]),
            StaticConnectorPool([]),
            StaticModelPool(),
        )
        return await record(
            "worker.endpoint", pools, environment, worker=worker.endpoint, state_dir=tmp_path
        )


async def record_connector(connector: RunningConnector, tmp_path: Path) -> Recorded:
    """The instance runs the connector suite against `connector.channel.repo`, with the
    scenario, the credential values and the connector's log configured."""
    environment = {
        "TAKTUS_CONFORMANCE_CONNECTOR_CHANNEL_REPO_SCENARIO": str(connector.scenario),
        "TAKTUS_CONFORMANCE_CONNECTOR_CHANNEL_REPO_LOG": str(connector.log),
        "TAKTUS_CONFORMANCE_TIMEOUT": "30",
        **{
            "TAKTUS_CREDENTIAL_" + name.upper(): value
            for name, value in connector.credential_values.items()
        },
    }
    adapter = "connector.channel.repo"
    pools = Pools(
        StaticWorkerPool([]),
        StaticConnectorPool([(adapter, McpActionConnector(connector.endpoint))]),
        StaticModelPool(),
    )
    return await record(
        adapter,
        pools,
        environment,
        connectors={"channel.repo": connector.endpoint},
        state_dir=tmp_path,
    )
