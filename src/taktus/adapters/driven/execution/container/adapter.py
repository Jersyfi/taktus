"""The `container` adapter: one execution unit per job, in a container, behind a wall.

The default in operation (ADR-0002). Every job gets:

- **a container of its own** from the unit's image, with the image's own command behind a
  launcher (`launch.sh`) that this adapter places into it; no capability, no privilege
  escalation, a process limit, a memory limit without swap, a CPU limit — the engine kills a
  job that exceeds the memory limit, and this adapter kills one that exceeds the wall clock;
- **a network of its own**, internal: no route out, no route in. The only other member is the
  job's **egress container** (`egress.py`), which sits on that network and on the network the
  control plane reaches. Inbound, it forwards the unit's port so the control plane can talk to
  the worker contract; outbound, it is an HTTP proxy that admits exactly `allowed_hosts` and
  refuses everything else. An empty list — the default — means the unit reaches nothing;
- **credentials in memory only**: the unit's container starts with a tmpfs, the launcher waits,
  this adapter writes each value into that tmpfs through an exec whose environment carries it,
  the launcher exports the env kind and removes the files, and the unit starts. No value is on
  a volume, in an image layer, in the container's recorded configuration, on a command line,
  or in a log;
- **a workspace that dies with the job**: the container's own filesystem, removed with the
  container. The unit's *state* — its checkpoints — is one named volume per unit, mounted at
  the unit's state directory, and it outlives jobs so that a resumed assignment finds them;
- **no socket**: the engine's socket is never mounted into a job. The list of mounts is the
  state volume and nothing else.

The control plane reaches the unit through the egress container: on a developer's machine at a
port it publishes on 127.0.0.1; from a control plane that runs in a container, by name on the
network both share (`TAKTUS_EXECUTION_NETWORK`). A cluster adapter is the same shape with a pod
instead of two containers and a network policy instead of a proxy; the port does not change.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from taktus.adapters.driven.execution._common import (
    ResolvedCredential,
    resolve_credentials,
    wait_until_healthy,
)
from taktus.adapters.driven.execution.container.engine import Engine, EngineError, config_of
from taktus.ports.configuration import Configuration
from taktus.ports.execution import (
    UNIT_PORT_VARIABLE,
    UNIT_STATE_DIR_VARIABLE,
    ExecutionError,
    Isolation,
    JobExit,
    JobRequest,
)

HERE = Path(__file__).resolve().parent
LAUNCHER = "/taktus/launch"
EGRESS_SCRIPT = "/taktus/egress.py"
CREDENTIALS_DIR = "/run/taktus/credentials"
PROXY_PORT = 3128
PIDS_LIMIT = 512
EGRESS_MEMORY_BYTES = 64 * 1024 * 1024

log = structlog.get_logger("taktus.execution.container")


@dataclass
class ContainerJob:
    id: str
    endpoint: str
    unit: str
    """The unit container's id."""
    egress: str
    network: str
    engine: Engine = field(repr=False)
    killed: JobExit | None = None

    async def exit(self) -> JobExit | None:
        if self.killed is not None:
            return self.killed
        state = ((await self.engine.inspect(self.unit)) or {}).get("State") or {}
        if not state or state.get("Running"):
            return None
        if state.get("OOMKilled"):
            return JobExit(
                code=int(state.get("ExitCode") or 137),
                killed="memory",
                reason="the memory limit was exceeded and the engine killed the unit",
            )
        code = int(state.get("ExitCode") or 0)
        return JobExit(code=code, reason=f"the unit exited with {code}")


class ContainerExecution:
    isolation = Isolation.CONTAINER

    def __init__(
        self,
        configuration: Configuration,
        *,
        socket: str,
        state_dir: Path,
        network: str | None = None,
        egress_image: str = "python:3.13-slim",
    ) -> None:
        self._configuration = configuration
        self._socket = socket
        self._state_dir = state_dir
        self._network = network
        self._egress_image = egress_image

    @asynccontextmanager
    async def launch(self, request: JobRequest) -> AsyncIterator[ContainerJob]:
        credentials = resolve_credentials(self._configuration, request.credentials)
        suffix = secrets.token_hex(3)
        names = _Names(f"{request.job_id}-{suffix}".lower().replace("_", "-"))
        engine = Engine(self._socket)
        job: ContainerJob | None = None
        timer: asyncio.Task[None] | None = None
        try:
            job = await self._start(engine, request, names, credentials)
            wall = min(
                request.wall_seconds or request.unit.limits.wall_seconds,
                request.unit.limits.wall_seconds,
            )
            timer = asyncio.create_task(self._kill_after(job, wall), name=f"wall-{job.id}")

            async def ended() -> str | None:
                exit = await job.exit() if job is not None else None
                return None if exit is None else exit.reason

            await wait_until_healthy(
                job.endpoint, within_seconds=request.unit.start_timeout_seconds, ended=ended
            )
            yield job
        finally:
            if timer is not None:
                timer.cancel()
            await self._remove(engine, names, request, job)
            await engine.close()

    # --- start --------------------------------------------------------------------------------

    async def _start(
        self,
        engine: Engine,
        request: JobRequest,
        names: _Names,
        credentials: tuple[ResolvedCredential, ...],
    ) -> ContainerJob:
        unit = request.unit
        image = await engine.ensure_image(unit.program)
        await engine.ensure_image(self._egress_image)
        network = await engine.create_network(names.network, internal=True)

        # The egress container: on the reachable network first, with the unit's port published
        # when no shared network is named; then joined to the job's network.
        publish = self._network is None
        egress_config = {
            "Image": self._egress_image,
            "Cmd": [
                "python3",
                EGRESS_SCRIPT,
                "--listen",
                str(PROXY_PORT),
                "--forward",
                str(unit.port),
                "--to",
                f"{names.unit}:{unit.port}",
                "--allow",
                ",".join(request.allowed_hosts),
            ],
            "ExposedPorts": {f"{unit.port}/tcp": {}},
            "HostConfig": {
                "NetworkMode": self._network or "bridge",
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Memory": EGRESS_MEMORY_BYTES,
                "MemorySwap": EGRESS_MEMORY_BYTES,
                "PidsLimit": 64,
                "PortBindings": {f"{unit.port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]}
                if publish
                else {},
            },
        }
        egress = await engine.create_container(names.egress, egress_config)
        await engine.put_file(egress, EGRESS_SCRIPT, (HERE / "egress.py").read_bytes(), mode=0o644)
        await engine.start(egress)
        await engine.connect(network, egress)

        # The unit's container: the image's own command behind the launcher, a tmpfs for the
        # credentials (and one for the directory of every file credential), the state volume,
        # the job's network, limits, no capability, no socket.
        entrypoint, command = config_of(image)
        tmpfs = {CREDENTIALS_DIR: "rw,noexec,nosuid,mode=1777,size=1m"}
        for credential in credentials:
            if credential.reference.injected_as == "file" and credential.reference.path:
                directory = credential.reference.path.rpartition("/")[0] or "/"
                tmpfs.setdefault(directory, "rw,noexec,nosuid,mode=1777,size=1m")
        environment = [
            f"{UNIT_PORT_VARIABLE}={unit.port}",
            f"{UNIT_STATE_DIR_VARIABLE}={unit.state_dir}",
            f"TAKTUS_CREDENTIALS_DIR={CREDENTIALS_DIR}",
        ]
        if request.allowed_hosts:
            proxy = f"http://{names.egress}:{PROXY_PORT}"
            environment += [f"{name}={proxy}" for name in ("HTTP_PROXY", "HTTPS_PROXY")]
            environment += [f"{name}={proxy}" for name in ("http_proxy", "https_proxy")]
        unit_config = {
            "Image": unit.program,
            "Entrypoint": [LAUNCHER],
            "Cmd": [*entrypoint, *command],
            "Env": environment,
            "ExposedPorts": {f"{unit.port}/tcp": {}},
            "HostConfig": {
                "NetworkMode": names.network,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Memory": unit.limits.memory_bytes,
                "MemorySwap": unit.limits.memory_bytes,
                "NanoCpus": int(unit.limits.cpus * 1_000_000_000),
                "PidsLimit": PIDS_LIMIT,
                "Tmpfs": tmpfs,
                "Mounts": [
                    {
                        "Type": "volume",
                        "Source": names.state_volume(unit.name),
                        "Target": unit.state_dir,
                    }
                ],
            },
        }
        container = await engine.create_container(names.unit, unit_config)
        await engine.put_file(container, LAUNCHER, (HERE / "launch.sh").read_bytes(), mode=0o755)
        await engine.start(container)
        await self._inject(engine, container, credentials)

        if publish:
            inspected = await engine.inspect(egress) or {}
            bindings = ((inspected.get("NetworkSettings") or {}).get("Ports") or {}).get(
                f"{unit.port}/tcp"
            ) or []
            if not bindings:
                raise ExecutionError("the egress container published no port for the unit")
            endpoint = f"http://127.0.0.1:{bindings[0]['HostPort']}"
        else:
            endpoint = f"http://{names.egress}:{unit.port}"
        log.info(
            "job started",
            job=request.job_id,
            unit=names.unit,
            egress=names.egress,
            allowed_hosts=list(request.allowed_hosts),
            credentials=[c.reference.name for c in credentials],
        )
        return ContainerJob(
            id=request.job_id,
            endpoint=endpoint,
            unit=container,
            egress=egress,
            network=network,
            engine=engine,
        )

    @staticmethod
    async def _inject(
        engine: Engine, container: str, credentials: tuple[ResolvedCredential, ...]
    ) -> None:
        """Each value into the memory-backed directory, through a command whose environment
        carries it; then the marker the launcher waits for. The value never appears in a
        command line: the shell reads it from its own environment."""
        for credential in credentials:
            reference = credential.reference
            if reference.injected_as == "env":
                target = f"{CREDENTIALS_DIR}/env/{reference.name}"
            else:
                target = reference.path or f"{CREDENTIALS_DIR}/files/{reference.name}"
            directory = target.rpartition("/")[0]
            script = (
                f'umask 077; mkdir -p "{directory}"; printf "%s" "$TAKTUS_CREDENTIAL_VALUE" > '
                f'"{target}"'
            )
            code = await engine.exec(
                container,
                ["sh", "-c", script],
                env=[f"TAKTUS_CREDENTIAL_VALUE={credential.value.reveal()}"],
            )
            if code != 0:
                raise ExecutionError(
                    f"credential {reference.name} could not be placed into the unit (exit {code})"
                )
        code = await engine.exec(
            container, ["sh", "-c", f'touch "{CREDENTIALS_DIR}/.ready"'], env=[]
        )
        if code != 0:
            raise ExecutionError(f"the unit could not be released to start (exit {code})")

    # --- end ----------------------------------------------------------------------------------

    @staticmethod
    async def _kill_after(job: ContainerJob, wall: int) -> None:
        await asyncio.sleep(wall)
        if await job.exit() is None:
            job.killed = JobExit(
                code=137, killed="wall", reason=f"the wall-clock limit of {wall}s was exceeded"
            )
            await job.engine.kill(job.unit)

    async def _remove(
        self, engine: Engine, names: _Names, request: JobRequest, job: ContainerJob | None
    ) -> None:
        """Everything but the state volume, and the unit's log kept under the state directory
        on this side, so that a job that failed can be read about."""
        if job is not None and job.killed is None:
            exit = await job.exit()
            if exit is None:
                job.killed = JobExit(killed="stop", reason="the job is over")
        for container in (names.unit, names.egress):
            try:
                if container == names.unit:
                    await self._keep_log(engine, container, request)
                await engine.remove(container)
            except EngineError as error:
                log.warning("container not removed", container=container, error=str(error))
        try:
            await engine.remove_network(names.network)
        except EngineError as error:
            log.warning("network not removed", network=names.network, error=str(error))

    async def _keep_log(self, engine: Engine, container: str, request: JobRequest) -> None:
        directory = self._state_dir / "units" / request.unit.name
        directory.mkdir(parents=True, exist_ok=True)
        try:
            content = await engine.logs(container)
        except EngineError:
            return
        (directory / f"job-{request.job_id}.log").write_bytes(content)


@dataclass(frozen=True)
class _Names:
    tag: str

    @property
    def network(self) -> str:
        return f"taktus-job-{self.tag}"

    @property
    def unit(self) -> str:
        return f"taktus-unit-{self.tag}"

    @property
    def egress(self) -> str:
        return f"taktus-egress-{self.tag}"

    @staticmethod
    def state_volume(unit_name: str) -> str:
        return f"taktus-unit-state-{unit_name}"
