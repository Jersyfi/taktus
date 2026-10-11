"""The workers the control plane is configured with, each opened the way its execution
settings say; and the telemetry, opened the way `TAKTUS_OTLP_*` says.

Four kinds (ADR-0002): a worker that is already running, reached by endpoint; a unit started
per job as a process of this machine; a unit started per job in a container; a unit started per
job as a Job in the cluster the control plane runs in. An instance names several workers in
`TAKTUS_WORKERS`, each of any kind, or configures one as before (ADR-0078). The daemon and
`taktusctl` share this so that neither has a wiring of its own. The adapter identifier the
ledger records is `worker.<name>`, or `worker.<kind>` for the one unnamed worker — never a
product name (ADR-0003).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Literal

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.execution import (
    ContainerExecution,
    KubernetesExecution,
    ProcessExecution,
)
from taktus.adapters.driven.models import OpenAiCompatibleModel, StaticModelPool
from taktus.adapters.driven.telemetry import (
    OpenTelemetryTelemetry,
    exporter_for,
    metric_exporter_for,
)
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.launched import LaunchedWorker
from taktus.composition.settings import (
    ExecutionKind,
    ExecutionSettings,
    ModelSettings,
    TelemetrySettings,
    WorkerSettings,
)
from taktus.ports.configuration import Configuration
from taktus.ports.connector import ActionConnector
from taktus.ports.execution import Execution, ExecutionUnit, ResourceLimits
from taktus.ports.worker import Worker

UNIT_NAME = "unit"


MODEL_ADAPTER = "model.endpoint"
"""The adapter identifier of the one configured model: reached by endpoint, never a product."""


def model_pool(settings: ModelSettings, *, timeout: float = 120.0) -> StaticModelPool:
    """The configured model as the run's pool, under `model.endpoint` for the purposes it
    serves; an empty pool when no endpoint is configured."""
    if settings.endpoint is None:
        return StaticModelPool()
    model = OpenAiCompatibleModel(
        settings.endpoint,
        settings.name,
        credential=settings.credential,
        timeout=timeout,
        billing=settings.billing,  # type: ignore[arg-type]  # validated by load_model
        output_cap=settings.output_cap,  # type: ignore[arg-type]
        provider_limit=settings.provider_limit,  # type: ignore[arg-type]
    )
    return StaticModelPool([(MODEL_ADAPTER, settings.purposes, model, settings.name)])


def connector_pool(
    connectors: Mapping[str, str],
    *,
    timeout: float = 120.0,
    also: Sequence[tuple[str, ActionConnector]] = (),
) -> StaticConnectorPool:
    """The configured connectors as the run's pool: one MCP client per entry of
    `TAKTUS_CONNECTORS`, registered under the adapter identifier `connector.<label>` — never a
    product name (ADR-0003) — and, after them, the connectors the instance brings itself
    (`also`: the loopback). The run resolves by the capabilities each declares."""
    return StaticConnectorPool(
        [
            (f"connector.{label}", McpActionConnector(endpoint, timeout=timeout))
            for label, endpoint in connectors.items()
        ]
        + list(also)
    )


def unit_of(settings: ExecutionSettings, name: str = UNIT_NAME) -> ExecutionUnit:
    """The execution unit as configured, for the launching kinds. `name` is the worker's, so
    that two launched workers keep their state and logs apart; the unnamed worker's unit is
    `unit`, as before."""
    if settings.unit is None:  # unreachable: load_execution refuses a launching kind without it
        raise ValueError("a launching execution kind names its unit")
    return ExecutionUnit(
        name=name,
        program=settings.unit,
        port=settings.unit_port,
        state_dir=settings.unit_state_dir,
        limits=ResourceLimits(
            cpus=settings.cpus,
            memory_bytes=settings.memory_mb * 1024 * 1024,
            wall_seconds=settings.wall_seconds,
        ),
        start_timeout_seconds=settings.start_timeout_seconds,
    )


def worker_unit(worker: WorkerSettings) -> ExecutionUnit:
    """The unit one configured worker launches, named after the worker."""
    return unit_of(worker.execution, worker.name or UNIT_NAME)


def memory_demand(workers: Sequence[WorkerSettings]) -> int | None:
    """The memory a worker step's unit takes on this platform — the largest limit among the
    launched units, since admission does not know yet which worker will serve the step — or
    None when every worker is reached by endpoint or runs as a Job in the cluster, outside what
    this platform observes. What admission against the platform asks for
    (`run/domain/service/capacity.py`)."""
    demands = [
        worker_unit(worker).limits.memory_bytes
        for worker in workers
        if worker.execution.kind not in (ExecutionKind.ENDPOINT, ExecutionKind.CLUSTER)
    ]
    return max(demands) if demands else None


def execution_of(
    settings: ExecutionSettings, configuration: Configuration, *, state_dir: Path
) -> Execution:
    """The execution adapter for one worker. `configuration` is the worker's own
    (`WorkerSettings.configuration`): the credentials it resolves are that worker's."""
    if settings.kind is ExecutionKind.PROCESS:
        return ProcessExecution(
            configuration, state_dir=state_dir, memory_unenforced=settings.memory_unenforced
        )
    if settings.kind is ExecutionKind.CLUSTER:
        if settings.namespace is None:  # unreachable: load_execution refuses cluster without it
            raise ValueError("the cluster kind names its execution namespace")
        return KubernetesExecution(
            configuration,
            namespace=settings.namespace,
            state_dir=state_dir,
            egress_image=settings.egress_image,
            enforce_egress=settings.egress_enforced,
            service_account=settings.service_account,
            state_claim=settings.state_claim,
        )
    return ContainerExecution(
        configuration,
        socket=settings.engine_socket,
        state_dir=state_dir,
        network=settings.network,
        egress_image=settings.egress_image,
    )


@asynccontextmanager
async def open_worker(
    worker: WorkerSettings,
    configuration: Configuration,
    *,
    state_dir: Path,
    endpoint: str | None = None,
    stream_timeout: float = 3600.0,
) -> AsyncIterator[Worker]:
    """One configured worker. `endpoint` overrides the configured one for the unnamed worker of
    kind `endpoint` (`taktusctl run --worker`); a named worker's endpoint is its own."""
    settings = worker.execution
    if settings.kind is ExecutionKind.ENDPOINT:
        address = (endpoint if worker.name is None else None) or settings.endpoint
        async with HttpWorker(address, stream_timeout=stream_timeout) as w:
            yield w
        return
    execution = execution_of(settings, worker.configuration(configuration), state_dir=state_dir)
    async with LaunchedWorker(execution, worker_unit(worker), stream_timeout=stream_timeout) as w:
        yield w


@asynccontextmanager
async def open_workers(
    workers: Sequence[WorkerSettings],
    configuration: Configuration,
    *,
    state_dir: Path,
    endpoint: str | None = None,
    stream_timeout: float = 3600.0,
) -> AsyncIterator[list[tuple[str, Worker]]]:
    """Every configured worker with its adapter identifier, in the configured order: what the
    worker pool resolves a step against (ADR-0078). Each is an adapter of its own, so the
    removal test can withhold one and the conformance half is recorded for each."""
    async with AsyncExitStack() as stack:
        opened = [
            (
                worker.identifier,
                await stack.enter_async_context(
                    open_worker(
                        worker,
                        configuration,
                        state_dir=state_dir,
                        endpoint=endpoint,
                        stream_timeout=stream_timeout,
                    )
                ),
            )
            for worker in workers
        ]
        yield opened


def telemetry_of(settings: TelemetrySettings) -> OpenTelemetryTelemetry:
    """Real spans always; an exporter only where an endpoint is configured."""
    exporter = None
    metrics = None
    if settings.endpoint is not None:
        protocol: Literal["grpc", "http"] = "grpc" if settings.protocol == "grpc" else "http"
        exporter = exporter_for(
            settings.endpoint, protocol=protocol, headers=settings.parsed_headers()
        )
        metrics = metric_exporter_for(
            settings.endpoint, protocol=protocol, headers=settings.parsed_headers()
        )
    return OpenTelemetryTelemetry(
        service_name=settings.service_name, exporter=exporter, metric_exporter=metrics
    )
