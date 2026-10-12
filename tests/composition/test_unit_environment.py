"""The variables a launched worker's unit is configured with (ADR-0090): read per worker with the
instance's as the default, refused where a name carries a secret, carried into every unit the
worker starts, named in the configuration a maturity record states — and, end to end, the
coding worker that refused to start without its authentication mode starts with it."""

from __future__ import annotations

import shlex
import sys
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeWorker

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.execution import ProcessExecution
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.workers.launched import LaunchedWorker
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.ports import NotRunnable
from taktus.composition import conformance
from taktus.composition.execution import execution_of, unit_environments, worker_unit
from taktus.composition.pools import Pools
from taktus.composition.settings import load, load_workers
from taktus.ports.configuration import ConfigurationError
from taktus.ports.execution import (
    ExecutionError,
    ExecutionRefused,
    ExecutionUnit,
    Isolation,
    Job,
    JobRequest,
    ResourceLimits,
    variable_refusal,
)
from taktus.ports.worker import CredentialReference, WorkerError

ROOT = Path(__file__).resolve().parents[2]
CODING = ROOT / "workers" / "claudecode"
URL = "postgresql://taktus:pw@db.internal:5432/taktus"
ENVIRONMENT = {
    "TAKTUS_WORKERS": "coding,shell,remote",
    "TAKTUS_EXECUTION": "cluster",
    "TAKTUS_EXECUTION_NAMESPACE": "jobs",
    "TAKTUS_EXECUTION_UNIT": "worker:1",
    "TAKTUS_EXECUTION_UNIT_ENV": "LOG_FORMAT=json",
    "TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV": "CODING_AGENT_AUTH=api-key, CODING_AGENT_MODEL=m=1",
    "TAKTUS_WORKER_REMOTE_EXECUTION": "endpoint",
    "TAKTUS_WORKER_REMOTE_ENDPOINT": "http://remote:9000",
}


class RecordingExecution:
    """Records each request and refuses it, so that nothing is started."""

    def __init__(self) -> None:
        self.requests: list[JobRequest] = []

    @property
    def isolation(self) -> Isolation:
        return Isolation.CLUSTER

    def launch(self, request: JobRequest) -> AbstractAsyncContextManager[Job]:
        self.requests.append(request)
        return self._refused()

    @asynccontextmanager
    async def _refused(self) -> AsyncIterator[Job]:
        raise ExecutionRefused("recorded, not started")
        yield  # pragma: no cover


# --- the setting ------------------------------------------------------------------------------


def test_the_variables_are_read_per_worker_with_the_instances_as_the_default() -> None:
    loaded = load(
        EnvironmentConfiguration({"TAKTUS_DATABASE_URL": URL, **ENVIRONMENT}),
        default_instance="host-1",
    )
    coding, shell, _ = loaded.workers
    assert coding.execution.unit_env == (
        ("CODING_AGENT_AUTH", "api-key"),
        ("CODING_AGENT_MODEL", "m=1"),
    ), "a worker's own replace the instance's; a value may hold '='"
    assert shell.execution.unit_env == (("LOG_FORMAT", "json"),)
    assert worker_unit(coding).environment == coding.execution.unit_env, "carried on the unit"
    effective = dict(loaded.effective())
    assert effective["TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV"] == (
        "CODING_AGENT_AUTH=api-key,CODING_AGENT_MODEL=m=1"
    ), "the startup log names them, values included: they are configuration"
    unset = load(EnvironmentConfiguration({"TAKTUS_DATABASE_URL": URL}), default_instance="h")
    assert unset.workers[0].execution.unit_env == (), "none unless configured"


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("CODING_AGENT_AUTH", "is not NAME=value"),
        ("A=1,,B=2", "is not NAME=value"),
        ("=x", "is not NAME=value"),
        ("A=1,A=2", "A is set twice"),
        ("1A=x", "is not a variable name"),
        ("TAKTUS_UNIT_PORT=1", "TAKTUS_ namespace"),
        ("TAKTUS_CREDENTIAL_VCS_TOKEN_FILE=/x", "TAKTUS_ namespace"),
        ("SSL_CERT_FILE=/x", "names a file"),
        ("HTTPS_PROXY=http://elsewhere", "set by the execution adapter"),
        ("no_proxy=*", "set by the execution adapter"),
        ("HOME=/root", "set by the execution adapter"),
        ("ANTHROPIC_API_KEY=x", "reads as a secret's name"),
        ("GITHUB_TOKEN=x", "reads as a secret's name"),
        ("DB_PASSWORD=x", "reads as a secret's name"),
        ("client_secret=x", "reads as a secret's name"),
    ],
)
def test_a_name_that_carries_a_secret_or_is_the_adapters_is_refused(value: str, why: str) -> None:
    with pytest.raises(ConfigurationError, match="TAKTUS_EXECUTION_UNIT_ENV") as raised:
        load_workers(EnvironmentConfiguration({"TAKTUS_EXECUTION_UNIT_ENV": value}))
    assert why in str(raised.value)


def test_a_credential_the_worker_is_configured_with_is_refused_as_a_variable(
    tmp_path: Path,
) -> None:
    """A credential whose name no word gives away — a session — is still a secret: the
    configuration supplies it as one, so it is refused as a plain variable of that worker."""
    (tmp_path / "session").write_text("s\n", encoding="utf-8")
    environment = {
        **ENVIRONMENT,
        "TAKTUS_WORKER_CODING_CREDENTIAL_CODING_AGENT_SESSION_FILE": str(tmp_path / "session"),
    }
    with pytest.raises(ConfigurationError, match="TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV"):
        load_workers(
            EnvironmentConfiguration(
                {**environment, "TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV": "CODING_AGENT_SESSION=1"}
            )
        )
    # Another worker's credential is not this worker's: the shell may use the name.
    shell = load_workers(
        EnvironmentConfiguration(
            {**environment, "TAKTUS_EXECUTION_UNIT_ENV": "CODING_AGENT_SESSION=1"}
        )
    )[1]
    assert shell.execution.unit_env == (("CODING_AGENT_SESSION", "1"),)


def test_the_unit_refuses_what_the_setting_refuses() -> None:
    """The port holds the rule too, so that a unit built without the settings cannot carry a
    secret's name either."""
    limits = ResourceLimits(cpus=1, memory_bytes=1024, wall_seconds=1)
    with pytest.raises(ValueError, match="reads as a secret's name"):
        ExecutionUnit(name="u", program="p", limits=limits, environment=(("VCS_TOKEN", "x"),))
    assert variable_refusal("CODING_AGENT_AUTH") is None
    assert variable_refusal("KEYBOARD_LAYOUT") is None, "a word, not a segment"


# --- where they go ----------------------------------------------------------------------------


async def test_every_unit_of_the_worker_carries_them_a_probe_and_the_suites_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configuration = EnvironmentConfiguration(ENVIRONMENT)
    coding = load_workers(configuration)[0]
    execution = RecordingExecution()
    worker = LaunchedWorker(execution, worker_unit(coding))
    with pytest.raises(WorkerError, match="recorded, not started"):
        await worker.capabilities()

    def recording(*_: Any, **__: Any) -> RecordingExecution:
        return execution

    monkeypatch.setattr(conformance, "execution_of", recording)
    target = conformance.worker_target(
        coding, coding.configuration(configuration), state_dir=tmp_path
    )
    with pytest.raises(NotRunnable, match="could not be started"):
        async with target():
            pass
    probe, suite = execution.requests
    for request in (probe, suite):
        assert dict(request.unit.environment)["CODING_AGENT_AUTH"] == "api-key"


def test_only_a_launched_worker_names_its_units_variables() -> None:
    workers = load_workers(EnvironmentConfiguration(ENVIRONMENT))
    assert unit_environments(workers) == {
        "worker.coding": ("CODING_AGENT_AUTH", "CODING_AGENT_MODEL"),
        "worker.shell": ("LOG_FORMAT",),
    }, "names only, and none for the endpoint worker, whose environment is whoever runs it"


async def test_the_configuration_a_record_names_states_the_variables_names() -> None:
    pools = Pools(
        StaticWorkerPool(
            [("worker.coding", FakeWorker()), ("worker.shell", FakeWorker())],
            environment={"worker.coding": ("CODING_AGENT_AUTH",)},
        ),
        StaticConnectorPool([]),
        StaticModelPool(),
    )
    coding = await pools.configuration("worker.coding")
    shell = await pools.configuration("worker.shell")
    assert coding is not None and coding.environment == ("CODING_AGENT_AUTH",)
    assert "api-key" not in str(coding.document()), "never a value"
    assert shell is not None and "environment" not in shell.document(), "none: as before"
    first = Pools(pools.workers.first("worker.coding"), pools.connectors, pools.models)
    without = Pools(pools.workers.without("worker.shell"), pools.connectors, pools.models)
    assert await first.configuration("worker.coding") == coding
    assert await without.configuration("worker.coding") == coding


# --- the coding worker, launched --------------------------------------------------------------


@pytest.mark.parametrize("configured", [True, False])
async def test_a_launched_coding_worker_starts_with_its_authentication_in_its_units_variables(
    tmp_path: Path, configured: bool
) -> None:
    """The gap of the installed instance (#288): launched, the coding worker gets the launch
    convention and nothing else, and exits before ready. With `CODING_AGENT_AUTH` in its unit's
    variables it starts and answers. The fake agent stands in for the real one."""
    program = shlex.join(
        [sys.executable, str(CODING / "worker.py"), "--agent", f"{sys.executable} "]
    ) + shlex.quote(str(CODING / "fake_agent.py"))
    environment = {
        "TAKTUS_EXECUTION": "process",
        "TAKTUS_EXECUTION_UNIT": program,
        "TAKTUS_EXECUTION_MEMORY_UNENFORCED": "true",
        "TAKTUS_EXECUTION_START_TIMEOUT_SECONDS": "30",
    }
    if configured:
        environment["TAKTUS_EXECUTION_UNIT_ENV"] = "CODING_AGENT_AUTH=api-key"
    configuration = EnvironmentConfiguration(environment)
    (worker,) = load_workers(configuration)
    execution = execution_of(
        worker.execution, worker.configuration(configuration), state_dir=tmp_path
    )
    launched = LaunchedWorker(execution, worker_unit(worker))
    if not configured:
        with pytest.raises(WorkerError, match="could not be started") as raised:
            await launched.capabilities()
        assert isinstance(raised.value.__cause__, ExecutionError), "it exited before ready"
        logs = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("job-*.log"))  # noqa: ASYNC240
        assert "--auth (or CODING_AGENT_AUTH) is required" in logs
        return
    capabilities = await launched.capabilities()
    assert "code.edit" in capabilities.capabilities


async def test_a_credential_under_a_configured_variables_name_is_refused_at_launch(
    tmp_path: Path,
) -> None:
    unit = ExecutionUnit(
        name="u",
        program="true",
        limits=ResourceLimits(cpus=1, memory_bytes=64 * 1024 * 1024, wall_seconds=5),
        environment=(("CODING_AGENT_SESSION", "1"),),
    )
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path, memory_unenforced=True
    )
    request = JobRequest(
        job_id="j",
        unit=unit,
        autonomy_level=1,
        credentials=(CredentialReference(name="CODING_AGENT_SESSION", injected_as="env"),),
    )
    with pytest.raises(ExecutionRefused, match="either configuration or a credential"):
        async with execution.launch(request):
            pass
