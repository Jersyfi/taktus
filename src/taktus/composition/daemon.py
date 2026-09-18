"""`taktusd`: Taktus as a service. One image, the roles `TAKTUS_ROLES` names, one process.

Startup, in order: read and validate the settings (a wrong one is one sentence on stderr and
exit code 2); log the effective configuration with every secret masked; connect to the
database and — with `TAKTUS_MIGRATE_ON_START` — bring it to the current schema; refuse to serve
against a schema that is not at the revision this build needs (exit code 3: silent drift is
worse than a refusal); wire the adapters to the ports, once, here; start the roles.

Shutdown, on SIGTERM or SIGINT: stop accepting work; let every running step reach its boundary
— up to the hard ceiling `TAKTUS_SHUTDOWN_CEILING_SECONDS`, after which the process exits and
the run is recovered by the next runner from its last persisted boundary; release the claims;
exit 0. That is ADR-0013 A and ADR-0005 in operation, and `tests/integration/test_daemon_*`
proves it with a real signal.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import structlog
import uvicorn
from sqlalchemy.exc import DBAPIError

from taktus.adapters.driven.clock import SystemClock, SystemIdentifiers
from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.connectors.mcp import McpIntakeConnector
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import (
    PostgresLeadership,
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresQueue,
    PostgresRepository,
    SchemaOutOfDate,
    check_schema,
    upgrade,
)
from taktus.adapters.driven.postgres.url import described
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.adapters.driving.rest import build_app
from taktus.components.command.application.service import (
    CommissionPlanHandler,
    ReceiveIntakeHandler,
)
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.query import ProvenanceQuery
from taktus.components.run.application.service import (
    EngineOptions,
    RunEngine,
    Runner,
    RunnerOptions,
)
from taktus.components.run.domain.model import Run
from taktus.composition import roles
from taktus.composition.execution import open_worker, telemetry_of
from taktus.composition.logging import configure, log_effective_configuration
from taktus.composition.settings import Role, Settings, load
from taktus.ports.configuration import Configuration, ConfigurationError
from taktus.ports.leadership import Leadership
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Repository, UnitOfWork
from taktus.shared.v1 import Command, Plan

EXIT_CONFIGURATION = 2
EXIT_NOT_OPERABLE = 3

log = structlog.get_logger("taktusd")


@dataclass
class Wired:
    """Every port with its adapter, built once by `wire()`. What the roles and the HTTP
    surface are handed."""

    settings: Settings
    persistence: PostgresPersistence
    work: UnitOfWork
    runs: Repository[Run]
    ledger: Ledger
    provenance: ProvenanceQuery
    engine: RunEngine
    register_version: RegisterProcessVersionHandler
    commission: CommissionPlanHandler
    intake: ReceiveIntakeHandler
    leadership: Leadership
    clock: SystemClock
    ids: SystemIdentifiers
    runner: Runner | None = None
    leading: bool = field(default=False, init=False)
    """Whether this process holds the scheduler's lead right now."""

    @property
    def roles(self) -> list[str]:
        return sorted(r.value for r in self.settings.roles)

    @property
    def tenants(self) -> tuple[str, ...]:
        return self.settings.tenants

    async def ready(self) -> str | None:
        """None when the database answers and is at the schema this build needs; otherwise
        the reason, in one sentence. Readiness is a question, not a memory."""
        try:
            await check_schema(self.persistence.engine)
        except SchemaOutOfDate as error:
            return str(error)
        except Exception as error:  # the database did not answer; the reason is the message
            where = described(self.settings.database.reveal())
            return f"the database at {where} did not answer: {type(error).__name__}"
        return None


class NotOperable(Exception):
    """The daemon cannot serve as configured; the message says why and what to do."""


@asynccontextmanager
async def wire(settings: Settings, configuration: Configuration) -> AsyncIterator[Wired]:
    """`configuration` is read again at runtime for what is not a setting: the credential
    values a launched execution unit is given, at the moment a job starts."""
    url = settings.database.reveal()
    if settings.migrate_on_start:
        log.info("migrating", database=described(url))
        try:
            await upgrade(url)
        except Exception as error:
            raise NotOperable(f"the migrations failed against {described(url)}: {error}") from error
    persistence = PostgresPersistence(url, pool_size=settings.runner_concurrency + 4)
    try:
        try:
            await check_schema(persistence.engine)
        except SchemaOutOfDate as error:
            raise NotOperable(str(error)) from error
        except (OSError, DBAPIError) as error:
            raise NotOperable(f"cannot reach the database at {described(url)}: {error}") from error
        clock = SystemClock()
        ids = SystemIdentifiers()
        telemetry = telemetry_of(settings.telemetry)
        runs = PostgresRepository(persistence, Run)
        ledger = ChainedLedger(PostgresLedgerStore(persistence), clock)
        provenance_store = PostgresProvenanceStore(persistence)
        queue = PostgresQueue(persistence, lease_seconds=settings.lease_seconds)
        async with open_worker(settings.execution, configuration, state_dir=settings.state_dir) as (
            adapter,
            worker,
        ):
            engine = RunEngine(
                runs=runs,
                work=persistence,
                objects=MemoryObjectStore(settings.state_dir / "objects"),
                ledger=ledger,
                provenance=provenance_store,
                workers=StaticWorkerPool([(adapter, worker)]),
                clock=clock,
                ids=ids,
                telemetry=telemetry,
                queue=queue,
                options=EngineOptions(step_ceiling_seconds=settings.shutdown_ceiling_seconds),
            )
            wired = Wired(
                settings=settings,
                persistence=persistence,
                work=persistence,
                runs=runs,
                ledger=ledger,
                provenance=ProvenanceQuery(provenance_store, runs, ledger, persistence),
                engine=engine,
                register_version=RegisterProcessVersionHandler(
                    PostgresRepository(persistence, ProcessVersion), persistence
                ),
                commission=CommissionPlanHandler(
                    PostgresRepository(persistence, Command),
                    PostgresRepository(persistence, Plan),
                    persistence,
                    clock,
                    ids,
                ),
                intake=ReceiveIntakeHandler(
                    # Capability → connector is configuration (ADR-0003): TAKTUS_CONNECTORS.
                    {
                        channel: McpIntakeConnector(endpoint)
                        for channel, endpoint in settings.connectors.items()
                    },
                    PostgresRepository(persistence, IntakeEvent),
                    persistence,
                    telemetry,
                ),
                leadership=PostgresLeadership(persistence.engine),
                clock=clock,
                ids=ids,
            )
            if Role.RUNNER in settings.roles:
                wired.runner = Runner(
                    engine=engine,
                    queue=queue,
                    work=persistence,
                    clock=clock,
                    options=RunnerOptions(
                        tenants=settings.tenants,
                        claimant=settings.instance,
                        concurrency=settings.runner_concurrency,
                        poll_seconds=settings.poll_seconds,
                        heartbeat_seconds=max(settings.lease_seconds / 3, 1.0),
                    ),
                )
            try:
                yield wired
            finally:
                telemetry.shutdown()
    finally:
        await persistence.close()


async def serve(
    settings: Settings,
    *,
    configuration: Configuration | None = None,
    stop: asyncio.Event | None = None,
    on_wired: Callable[[Wired], None] | None = None,
) -> int:
    """Run the roles until `stop` — set by SIGTERM or SIGINT, or by the caller — and wind
    down. The exit code of the process. `on_wired` hands the wired services to a test that
    runs the daemon in-process."""
    stop = stop or asyncio.Event()
    _install_signal_handlers(stop)
    try:
        async with wire(settings, configuration or EnvironmentConfiguration()) as wired:
            if on_wired is not None:
                on_wired(wired)
            log.info(
                "taktusd serving",
                roles=sorted(r.value for r in settings.roles),
                instance=settings.instance,
                database=described(settings.database.reveal()),
            )
            tasks = _start_roles(wired, stop)
            server = await _start_http(wired, stop)
            await stop.wait()
            log.info("taktusd stopping", ceiling_seconds=settings.shutdown_ceiling_seconds)
            # New work is refused first — the surface goes, the runner claims nothing more —
            # then every running step reaches its boundary.
            server.should_exit = True
            await _wind_down(tasks, settings.shutdown_ceiling_seconds)
            log.info("taktusd stopped")
    except NotOperable as error:
        log.error("taktusd cannot serve", reason=str(error))
        return EXIT_NOT_OPERABLE
    return 0


def _on_signal(signum: int, stop: asyncio.Event) -> None:
    log.info("signal received", signal=signal.Signals(signum).name)
    stop.set()


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, _on_signal, signum, stop)
        except (NotImplementedError, RuntimeError):  # not the main thread, or no loop support
            pass


async def _start_http(wired: Wired, stop: asyncio.Event) -> uvicorn.Server:
    """Every process serves health and readiness under the prefix; the `api` role adds the
    rest (commit by commit: intake and the read API). The server takes no signal of its own:
    the daemon's handlers are installed again once it has started, because the server
    installs its own on startup and would otherwise take the daemon's away."""
    settings = wired.settings
    app = build_app(wired, prefix=settings.path_prefix, full=Role.API in settings.roles)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.http_host,
            port=settings.http_port,
            log_config=None,
            access_log=False,
            lifespan="off",
        )
    )
    task = asyncio.create_task(server.serve(), name="http")
    while not server.started:
        if task.done():
            error = task.exception()
            raise NotOperable(
                f"the HTTP server did not start on {settings.http_host}:{settings.http_port}"
                + (f": {error}" if error else "; the port is in use, most likely")
            )
        await asyncio.sleep(0.01)
    _install_signal_handlers(stop)
    log.info(
        "http serving",
        host=settings.http_host,
        port=settings.http_port,
        prefix=settings.path_prefix,
    )
    return server


def _start_roles(wired: Wired, stop: asyncio.Event) -> list[asyncio.Task[None]]:
    settings = wired.settings
    tasks: list[asyncio.Task[None]] = []
    if wired.runner is not None:
        tasks.append(asyncio.create_task(roles.run_runner(wired.runner, stop), name="runner"))
    if Role.SCHEDULER in settings.roles:

        def on_lead(leading: bool) -> None:
            wired.leading = leading

        tasks.append(
            asyncio.create_task(
                roles.run_scheduler(
                    wired.leadership,
                    wired.clock,
                    stop,
                    poll_seconds=settings.poll_seconds,
                    on_lead=on_lead,
                ),
                name="scheduler",
            )
        )
    if Role.AUTOMATION in settings.roles:
        tasks.append(
            asyncio.create_task(
                roles.run_automation(wired.clock, stop, poll_seconds=settings.poll_seconds),
                name="automation",
            )
        )
    return tasks


async def _wind_down(tasks: list[asyncio.Task[None]], ceiling_seconds: int) -> None:
    """Every role gets until the ceiling to land; a role still running after it is cancelled
    and the process leaves — the run it held is recovered by the next runner."""
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=ceiling_seconds)
    for task in pending:
        log.warning("role did not stop within the ceiling; leaving", role=task.get_name())
        task.cancel()
    for task in done:
        if (error := task.exception()) is not None:
            log.error("role failed", role=task.get_name(), error=repr(error))


def main() -> None:
    configuration = EnvironmentConfiguration()
    try:
        settings = load(configuration, default_instance=f"{socket.gethostname()}-{os.getpid()}")
    except ConfigurationError as error:
        sys.stderr.write(f"taktusd: {error}\n")
        sys.exit(EXIT_CONFIGURATION)
    configure(settings.log_level)
    log_effective_configuration(settings)
    sys.exit(asyncio.run(serve(settings, configuration=configuration)))


if __name__ == "__main__":
    main()
