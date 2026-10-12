"""The hosts a worker's own service needs, as the composition carries them (ADR-0089): into the
conformance suite's unit, and into the configuration a maturity record names."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeWorker

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.catalog.ports import NotRunnable
from taktus.composition import conformance
from taktus.composition.execution import service_hosts
from taktus.composition.pools import Pools
from taktus.composition.settings import load_workers
from taktus.ports.execution import ExecutionRefused, Isolation, Job, JobRequest


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


ENVIRONMENT = {
    "TAKTUS_WORKERS": "coding,shell",
    "TAKTUS_EXECUTION": "cluster",
    "TAKTUS_EXECUTION_NAMESPACE": "jobs",
    "TAKTUS_EXECUTION_UNIT": "worker:1",
    "TAKTUS_WORKER_CODING_EXECUTION_SERVICE_HOSTS": "model.example.net",
    "TAKTUS_WORKER_SHELL_EXECUTION": "endpoint",
    "TAKTUS_WORKER_SHELL_ENDPOINT": "http://shell:9000",
    "TAKTUS_WORKER_SHELL_EXECUTION_SERVICE_HOSTS": "ignored.example.net",
}


async def test_the_suites_unit_reaches_the_suites_hosts_and_the_service_hosts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    execution = RecordingExecution()

    def recording(*_: Any, **__: Any) -> RecordingExecution:
        return execution

    monkeypatch.setattr(conformance, "execution_of", recording)
    configuration = EnvironmentConfiguration(
        {**ENVIRONMENT, "TAKTUS_CONFORMANCE_WORKER_HOSTS": "repo.example.org, model.example.net"}
    )
    coding = load_workers(configuration)[0]
    target = conformance.worker_target(
        coding, coding.configuration(configuration), state_dir=tmp_path
    )
    with pytest.raises(NotRunnable, match="could not be started"):
        async with target():
            pass
    (request,) = execution.requests
    assert request.autonomy_level == 1
    assert request.allowed_hosts == ("repo.example.org", "model.example.net")


def test_only_a_launched_worker_names_service_hosts() -> None:
    """A worker reached by endpoint is reached wherever whoever runs it put it: no unit is
    started for it, and nothing it names is enforced, so nothing is recorded."""
    workers = load_workers(EnvironmentConfiguration(ENVIRONMENT))
    assert service_hosts(workers) == {"worker.coding": ("model.example.net",)}


async def test_the_configuration_a_record_names_states_the_service_hosts() -> None:
    worker = FakeWorker()
    pools = Pools(
        StaticWorkerPool(
            [("worker.coding", worker), ("worker.shell", FakeWorker())],
            hosts={"worker.coding": ("model.example.net",)},
        ),
        StaticConnectorPool([]),
        StaticModelPool(),
    )
    coding = await pools.configuration("worker.coding")
    shell = await pools.configuration("worker.shell")
    assert coding is not None and coding.hosts == ("model.example.net",)
    assert shell is not None and shell.hosts is None, "none named: as before"
    assert "hosts" not in shell.document(), "a configuration without them reads as before"
    first = Pools(pools.workers.first("worker.coding"), pools.connectors, pools.models)
    without = Pools(pools.workers.without("worker.shell"), pools.connectors, pools.models)
    assert await first.configuration("worker.coding") == coding
    assert await without.configuration("worker.coding") == coding
