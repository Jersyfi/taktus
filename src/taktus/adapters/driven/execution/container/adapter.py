"""The `container` adapter: one execution unit per job, in a container, behind a wall.

The default in operation (ADR-0002). Every job gets:

- **a container of its own** from the unit's image, with the image's own command behind a
  launcher (`launch.sh`) that this adapter places into it; no capability, no privilege
  escalation, a process limit, a memory limit without swap (the swap limit equal to the
  memory limit), a CPU limit — the engine kills a job that exceeds the memory limit, and this
  adapter kills one that exceeds the wall clock. An engine that says it cannot limit memory
  or swap (`/info`: `MemoryLimit`, `SwapLimit`) would take the limits and silently not apply
  them, so the job is refused before anything is created (`limits_refusal`);
- **a network of its own**, internal: no route out, no route in. The only other member is the
  instance's **egress gateway** (`egress.py`, ADR-0115), which joins the job's network for the
  job's life. Inbound, it forwards `/units/<unit>/<port>/…` to the unit's worker contract, so
  that the control plane reaches it; outbound, it is an HTTP proxy that admits exactly the hosts
  the job's token names and refuses everything else. The token is minted per job, signed with
  the gateway's key, and reaches the unit as its proxy variables, in memory, as a credential
  does. A job without hosts gets no token and no proxy variable: it reaches nothing;
- **credentials in memory only**: the unit's container starts with a tmpfs, the launcher waits,
  this adapter writes each value into that tmpfs through an exec whose environment carries it,
  the launcher exports the env kind and removes the files, and the unit starts. No value is on
  a volume, in an image layer, in the container's recorded configuration, on a command line,
  or in a log;
- **the variables its configuration names** (`ExecutionUnit.environment`, ADR-0090) in the
  container's environment, beside the launch convention's: configuration, never a secret;
- **a workspace that dies with the job**: the container's own filesystem, removed with the
  container. The unit's *state* — its checkpoints — is one named volume per unit, mounted at
  the unit's state directory, and it outlives jobs so that a resumed assignment finds them;
- **no socket**: the engine's socket is never mounted into a job. The list of mounts is the
  state volume and nothing else.

**The gateway is the instance's, not the job's.** It is started with the first job and serves
every later one. Its key is the configured `execution.gateway.key`; without one, a key is drawn
for this process, its gateway is this process's alone, and `close` removes it. The gateway's
name follows from its key, so that processes configured with the same key share one gateway.
It reaches the network the control plane reaches: on a developer's machine its inbound port is
published on 127.0.0.1; from a control plane that runs in a container, it is reached by name on
the network both share (`TAKTUS_EXECUTION_NETWORK`). It listens inbound only on that network,
never on a job's, and its proxy refuses every address on a job's network, so that no unit
reaches another through it. A cluster adapter is the same shape with a pod instead of a
container and a network policy instead of an internal network; the port does not change.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from taktus.adapters.driven.execution._common import (
    PROXY_VARIABLES,
    ResolvedCredential,
    gateway_key,
    job_token,
    proxy_url,
    resolve_credentials,
    wait_until_healthy,
)
from taktus.adapters.driven.execution.container.engine import (
    Engine,
    EngineError,
    Json,
    config_of,
)
from taktus.ports.configuration import Configuration
from taktus.ports.execution import (
    UNIT_PORT_VARIABLE,
    UNIT_STATE_DIR_VARIABLE,
    UNIT_WALL_SECONDS_VARIABLE,
    ExecutionError,
    ExecutionRefused,
    Isolation,
    JobExit,
    JobRequest,
    unit_environment,
)

HERE = Path(__file__).resolve().parent
LAUNCHER = "/taktus/launch"
EGRESS_SCRIPT = "/taktus/egress.py"
CREDENTIALS_DIR = "/run/taktus/credentials"
PROXY_PORT = 3128
INBOUND_PORT = 8080
"""The gateway's port for the control plane: `/units/<unit>/<port>/…` reaches a unit."""
GATEWAY_KEY_PATH = "/run/taktus/gateway/key"
"""Where the gateway holds its key: a memory-backed directory, written after the start."""
GATEWAY_LABEL = {"taktus/role": "gateway"}
PIDS_LIMIT = 512
EGRESS_MEMORY_BYTES = 64 * 1024 * 1024
KILLED = 137
"""128 + SIGKILL: the exit status of a unit killed by the kernel, or by anyone else."""
OOM_RECORD = b"taktus-launch: oom_kill "
"""The line `launch.sh` writes when the unit died killed and the cgroup's kernel counter of
out-of-memory kills rose while it ran."""


PORT_TAKEN = "address already in use"
"""What the engine says when the host port it chose for a published port is held by a process
it does not know of."""
PUBLISH_ATTEMPTS = 5


async def start_publishing(engine: Engine, container: str) -> None:
    """Start a container that publishes a port on a host port the engine chooses. The engine
    picks the port from its own record of what it handed out, which does not see a socket
    another process holds: on a host where other programs listen on ports of the same range,
    the start fails with `address already in use`. Each further start makes the
    engine choose again, so the start is repeated a few times on exactly that answer; any other
    refusal, or the last one, is raised as it came."""
    for attempt in range(1, PUBLISH_ATTEMPTS + 1):
        try:
            await engine.start(container)
            return
        except EngineError as error:
            if PORT_TAKEN not in str(error) or attempt == PUBLISH_ATTEMPTS:
                raise
            log.warning(
                "the host port the engine chose is taken; starting again",
                container=container,
                attempt=attempt,
            )


def memory_kill_recorded(log: bytes) -> bool:
    """Whether the launcher found the kernel's record of an out-of-memory kill in the log."""
    return any(line.startswith(OOM_RECORD) for line in log.splitlines())


log = structlog.get_logger("taktus.execution.container")


@dataclass
class ContainerJob:
    id: str
    endpoint: str
    unit: str
    """The unit container's id."""
    gateway: str
    """The name of the instance's gateway, which serves this job and outlives it."""
    network: str
    engine: Engine = field(repr=False)
    killed: JobExit | None = None

    async def exit(self) -> JobExit | None:
        if self.killed is not None:
            return self.killed
        state = ((await self.engine.inspect(self.unit)) or {}).get("State") or {}
        if not state or state.get("Running"):
            return None
        code = int(state.get("ExitCode") or 0)
        if state.get("OOMKilled"):
            return JobExit(
                code=code or 137,
                killed="memory",
                reason="the memory limit was exceeded and the engine killed the unit",
            )
        if code == KILLED and memory_kill_recorded(await self.engine.logs(self.unit)):
            # The kernel's record, read by the launcher after the unit died: the engine's flag
            # comes from a separate event that may arrive late or never (issue #29).
            return JobExit(
                code=code,
                killed="memory",
                reason="the memory limit was exceeded and the kernel killed the unit "
                "(its out-of-memory record counts the kill)",
            )
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
        self._key: bytes | None = None
        self._drawn = False
        self._gateway: _Gateway | None = None
        self._gateway_lock = asyncio.Lock()

    async def close(self) -> None:
        """Remove the gateway when its key was drawn for this process and no other adapter of
        the process uses it: nobody else can. A gateway of a configured key is the instance's
        and stays."""
        gateway, self._gateway = self._gateway, None
        if gateway is None or not self._drawn:
            return
        _USERS[gateway.name] -= 1
        if _USERS[gateway.name] > 0:
            return
        del _USERS[gateway.name]
        async with Engine(self._socket) as engine:
            try:
                await engine.remove(gateway.name)
            except EngineError as error:
                log.warning("gateway not removed", gateway=gateway.name, error=str(error))

    @asynccontextmanager
    async def launch(self, request: JobRequest) -> AsyncIterator[ContainerJob]:
        unit_environment(request)  # refused before anything starts
        credentials = resolve_credentials(self._configuration, request.credentials)
        key = self._gateway_key()
        suffix = secrets.token_hex(3)
        names = _Names(f"{request.job_id}-{suffix}".lower().replace("_", "-"))
        engine = Engine(self._socket)
        try:
            why = limits_refusal(await engine.info())
        except BaseException:
            await engine.close()
            raise
        if why is not None:
            await engine.close()
            raise ExecutionRefused(why)
        job: ContainerJob | None = None
        timer: asyncio.Task[None] | None = None
        gateway: _Gateway | None = None
        try:
            gateway = await self._ensure_gateway(engine, key)
            job = await self._start(engine, request, names, credentials, gateway, key)
            timer = asyncio.create_task(self._kill_after(job, request.wall), name=f"wall-{job.id}")

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
            await self._remove(engine, names, request, job, gateway)
            await engine.close()

    # --- the gateway --------------------------------------------------------------------------

    def _gateway_key(self) -> bytes:
        """The configured key, else the one drawn for this process: every worker of the
        process shares it, and so shares one gateway."""
        if self._key is None:
            configured = gateway_key(self._configuration)
            if configured is not None:
                self._key = configured.reveal().strip().encode()
            else:
                self._key = _drawn_key()
                self._drawn = True
        return self._key

    async def _ensure_gateway(self, engine: Engine, key: bytes) -> _Gateway:
        """The running gateway of this key: this process's, one another process with the same
        key started, or a new one. One that is there but not running is replaced."""
        async with self._gateway_lock:
            name = _gateway_name(key)
            inspected = await engine.inspect(name)
            running = bool(((inspected or {}).get("State") or {}).get("Running"))
            if self._gateway is not None and running:
                return self._gateway
            if not running:
                if inspected is not None:
                    await engine.remove(name)
                try:
                    await self._create_gateway(engine, name, key)
                except EngineError:
                    # Another process with the same key may have created it a moment earlier.
                    if not await _comes_up(engine, name):
                        raise
                inspected = await engine.inspect(name)
            if self._gateway is None and self._drawn:
                _USERS[name] = _USERS.get(name, 0) + 1
            self._gateway = _Gateway(name=name, inbound=self._inbound_of(name, inspected or {}))
            return self._gateway

    async def _create_gateway(self, engine: Engine, name: str, key: bytes) -> None:
        await engine.ensure_image(self._egress_image)
        publish = self._network is None
        config = {
            "Image": self._egress_image,
            "Cmd": [
                "python3",
                EGRESS_SCRIPT,
                "--listen",
                str(PROXY_PORT),
                "--key-file",
                GATEWAY_KEY_PATH,
                "--inbound",
                str(INBOUND_PORT),
                "--refuse-job-networks",
            ],
            "Labels": dict(GATEWAY_LABEL),
            "ExposedPorts": {f"{INBOUND_PORT}/tcp": {}},
            "HostConfig": {
                "NetworkMode": self._network or "bridge",
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Memory": EGRESS_MEMORY_BYTES,
                "MemorySwap": EGRESS_MEMORY_BYTES,
                "PidsLimit": 64,
                "Tmpfs": {GATEWAY_KEY_PATH.rpartition("/")[0]: "rw,noexec,nosuid,size=64k"},
                "PortBindings": {f"{INBOUND_PORT}/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]}
                if publish
                else {},
            },
        }
        container = await engine.create_container(name, config)
        await engine.put_file(
            container, EGRESS_SCRIPT, (HERE / "egress.py").read_bytes(), mode=0o644
        )
        if publish:
            await start_publishing(engine, container)
        else:
            await engine.start(container)
        # The key into memory, through a command whose environment carries it.
        code = await engine.exec(
            container,
            ["sh", "-c", f'umask 077; printf "%s" "$TAKTUS_GATEWAY_KEY" > "{GATEWAY_KEY_PATH}"'],
            env=[f"TAKTUS_GATEWAY_KEY={key.decode()}"],
        )
        if code != 0:
            raise ExecutionError(f"the gateway's key could not be placed into it (exit {code})")
        log.info("gateway started", gateway=name, network=self._network or "bridge")

    def _inbound_of(self, name: str, inspected: Json) -> str:
        if self._network is not None:
            return f"http://{name}:{INBOUND_PORT}"
        bindings = ((inspected.get("NetworkSettings") or {}).get("Ports") or {}).get(
            f"{INBOUND_PORT}/tcp"
        ) or []
        if not bindings:
            raise ExecutionError(f"the gateway {name} published no port for the control plane")
        return f"http://127.0.0.1:{bindings[0]['HostPort']}"

    # --- start --------------------------------------------------------------------------------

    async def _start(
        self,
        engine: Engine,
        request: JobRequest,
        names: _Names,
        credentials: tuple[ResolvedCredential, ...],
        gateway: _Gateway,
        key: bytes,
    ) -> ContainerJob:
        unit = request.unit
        image = await engine.ensure_image(unit.program)
        network = await engine.create_network(names.network, internal=True)
        await engine.connect(network, gateway.name)

        # The unit's container: the image's own command behind the launcher, a tmpfs for the
        # credentials (and one for the directory of every file credential), the state volume,
        # the job's network, limits, no capability, no socket.
        entrypoint, command = config_of(image)
        tmpfs = {CREDENTIALS_DIR: "rw,noexec,nosuid,mode=1777,size=1m"}
        for credential in credentials:
            if credential.reference.injected_as == "file" and credential.reference.path:
                directory = credential.reference.path.rpartition("/")[0] or "/"
                tmpfs.setdefault(directory, "rw,noexec,nosuid,mode=1777,size=1m")
        # The variables the unit's configuration names (ADR-0090), then the launch convention.
        environment = [
            *(f"{name}={value}" for name, value in unit.environment),
            f"{UNIT_PORT_VARIABLE}={unit.port}",
            f"{UNIT_STATE_DIR_VARIABLE}={unit.state_dir}",
            f"{UNIT_WALL_SECONDS_VARIABLE}={request.wall}",
            f"TAKTUS_CREDENTIALS_DIR={CREDENTIALS_DIR}",
        ]
        # The proxy variables carry the job's token: into memory with the credentials, never
        # into the container's recorded configuration.
        proxy: tuple[tuple[str, str], ...] = ()
        if request.allowed_hosts:
            token = job_token(
                key,
                job=names.tag,
                hosts=request.allowed_hosts,
                seconds=request.wall + unit.start_timeout_seconds,
            )
            url = proxy_url(token, gateway.name, PROXY_PORT)
            proxy = tuple((variable, url) for variable in PROXY_VARIABLES)
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
        await self._inject(engine, container, credentials, proxy)

        log.info(
            "job started",
            job=request.job_id,
            unit=names.unit,
            gateway=gateway.name,
            allowed_hosts=list(request.allowed_hosts),
            credentials=[c.reference.name for c in credentials],
        )
        return ContainerJob(
            id=request.job_id,
            endpoint=f"{gateway.inbound}/units/{names.unit}/{unit.port}",
            unit=container,
            gateway=gateway.name,
            network=network,
            engine=engine,
        )

    @staticmethod
    async def _inject(
        engine: Engine,
        container: str,
        credentials: tuple[ResolvedCredential, ...],
        variables: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Each value into the memory-backed directory, through a command whose environment
        carries it; then the marker the launcher waits for. The value never appears in a
        command line: the shell reads it from its own environment. `variables` are values that
        are not credentials and are carried as one: the proxy URL with the job's token."""
        targets = [
            (
                f"{CREDENTIALS_DIR}/env/{c.reference.name}"
                if c.reference.injected_as == "env"
                else c.reference.path or f"{CREDENTIALS_DIR}/files/{c.reference.name}",
                c.reference.name,
                c.value.reveal(),
            )
            for c in credentials
        ]
        targets += [(f"{CREDENTIALS_DIR}/env/{name}", name, value) for name, value in variables]
        for target, name, value in targets:
            directory = target.rpartition("/")[0]
            script = (
                f'umask 077; mkdir -p "{directory}"; printf "%s" "$TAKTUS_CREDENTIAL_VALUE" > '
                f'"{target}"'
            )
            code = await engine.exec(
                container, ["sh", "-c", script], env=[f"TAKTUS_CREDENTIAL_VALUE={value}"]
            )
            if code != 0:
                raise ExecutionError(
                    f"credential {name} could not be placed into the unit (exit {code})"
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
        self,
        engine: Engine,
        names: _Names,
        request: JobRequest,
        job: ContainerJob | None,
        gateway: _Gateway | None,
    ) -> None:
        """The unit and the job's network, after the gateway left it; the unit's log kept under
        the state directory on this side, so that a job that failed can be read about. The
        gateway and the state volume stay."""
        if job is not None and job.killed is None:
            exit = await job.exit()
            if exit is None:
                job.killed = JobExit(killed="stop", reason="the job is over")
        try:
            await self._keep_log(engine, names.unit, request)
            await engine.remove(names.unit)
        except EngineError as error:
            log.warning("container not removed", container=names.unit, error=str(error))
        if gateway is not None:
            try:
                await engine.disconnect(names.network, gateway.name)
            except EngineError as error:
                log.warning("gateway not taken off", network=names.network, error=str(error))
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


def limits_refusal(info: Json) -> str | None:
    """Why the engine cannot be trusted with a job's limits, or None when it can. An engine
    without memory limiting accepts `Memory` and applies nothing; one without swap limiting
    accepts `MemorySwap` and lets the job swap past its limit. Either way the limit would be a
    number in a configuration and nothing on the machine: the job is refused, as a job the
    adapter cannot give limits to is refused (deploy/k8s/README.md)."""
    missing = [name for name in ("MemoryLimit", "SwapLimit") if info.get(name) is not True]
    if not missing:
        return None
    return (
        f"the container engine reports {' and '.join(f'{n}: false' for n in missing)}: it "
        "cannot enforce the job's memory limit without swap, and a limit it does not enforce "
        "is refused rather than trusted"
    )


@dataclass(frozen=True)
class _Gateway:
    name: str
    inbound: str
    """Where the control plane reaches the gateway's inbound port."""


_DRAWN: list[bytes] = []
"""The gateway key drawn for this process, once, where none is configured."""
_USERS: dict[str, int] = {}
"""How many adapters of this process use a gateway of the drawn key, by its name."""


def _drawn_key() -> bytes:
    if not _DRAWN:
        _DRAWN.append(secrets.token_urlsafe(32).encode())
    return _DRAWN[0]


async def _comes_up(engine: Engine, name: str, within: float = 10.0) -> bool:
    """Whether a gateway of that name is running, or starts running within a few seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within
    while True:
        state = ((await engine.inspect(name)) or {}).get("State") or {}
        if state.get("Running"):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.2)


def _gateway_name(key: bytes) -> str:
    """The gateway's name, the same for every process with the same key and saying nothing of
    the key itself."""
    return "taktus-gateway-" + hmac.new(key, b"gateway-name", hashlib.sha256).hexdigest()[:12]


@dataclass(frozen=True)
class _Names:
    tag: str

    @property
    def network(self) -> str:
        return f"taktus-job-{self.tag}"

    @property
    def unit(self) -> str:
        return f"taktus-unit-{self.tag}"

    @staticmethod
    def state_volume(unit_name: str) -> str:
        return f"taktus-unit-state-{unit_name}"
