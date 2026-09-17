"""The one worker the control plane is configured with, opened the way `TAKTUS_EXECUTION` says.

Three kinds (ADR-0002): a worker that is already running, reached by endpoint; a unit started
per job as a process of this machine; a unit started per job in a container. The daemon and
`taktusctl` share this so that neither has a wiring of its own. The adapter identifier the
ledger records is `worker.<kind>` — never a product name (ADR-0003).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from taktus.adapters.driven.execution import ProcessExecution
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.adapters.driven.workers.launched import LaunchedWorker
from taktus.composition.settings import ExecutionKind, ExecutionSettings
from taktus.ports.configuration import Configuration
from taktus.ports.execution import Execution, ExecutionUnit, ResourceLimits
from taktus.ports.worker import Worker

UNIT_NAME = "unit"


def adapter_identifier(kind: ExecutionKind) -> str:
    return f"worker.{kind.value}"


def unit_of(settings: ExecutionSettings) -> ExecutionUnit:
    """The execution unit as configured, for the launching kinds."""
    if settings.unit is None:  # unreachable: load_execution refuses a launching kind without it
        raise ValueError("a launching execution kind names its unit")
    return ExecutionUnit(
        name=UNIT_NAME,
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


def execution_of(
    settings: ExecutionSettings, configuration: Configuration, *, state_dir: Path
) -> Execution:
    if settings.kind is ExecutionKind.PROCESS:
        return ProcessExecution(configuration, state_dir=state_dir)
    raise NotImplementedError(settings.kind)  # container arrives with the next commit


@asynccontextmanager
async def open_worker(
    settings: ExecutionSettings,
    configuration: Configuration,
    *,
    state_dir: Path,
    endpoint: str | None = None,
    stream_timeout: float = 3600.0,
) -> AsyncIterator[tuple[str, Worker]]:
    """The configured worker with its adapter identifier. `endpoint` overrides the configured
    one for kind `endpoint` (`taktusctl run --worker`)."""
    if settings.kind is ExecutionKind.ENDPOINT:
        async with HttpWorker(endpoint or settings.endpoint, stream_timeout=stream_timeout) as w:
            yield adapter_identifier(settings.kind), w
        return
    execution = execution_of(settings, configuration, state_dir=state_dir)
    async with LaunchedWorker(execution, unit_of(settings), stream_timeout=stream_timeout) as w:
        yield adapter_identifier(settings.kind), w
