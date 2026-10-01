"""The `process` adapter: an execution unit as a child process of this one. No isolation.

For local development and a single user (ADR-0002). What it does: starts the unit's command
line with a free port and the unit's state directory in its environment, injects the
credentials the job names as environment variables, gives the job a workspace that is removed
when the job ends, waits until the unit answers health, and kills the unit when the wall clock
runs out or the job is over. What it does not do, and cannot: keep the unit off the network —
the unit shares this machine's filesystem and network, and the reach that `allowed_hosts`
names is the worker's own honesty (W-13), not a wall. That is why the port refuses this
adapter from autonomy level 3 upwards, and why a credential injected as a file is refused
here: without a filesystem of its own, a job has no place for one that outlives nothing.

**Memory: what holds on which system.** Every job carries a memory limit
(`ResourceLimits.memory_bytes`), and a limit nothing enforces is worse than none, because it
reads as a guarantee. So:

- **Linux** — enforced. The unit is started through a launcher that sets `RLIMIT_DATA` to the
  limit and then becomes the unit (`exec`), so the limit holds for the unit and for everything
  it starts. `RLIMIT_DATA` rather than `RLIMIT_AS`: since Linux 4.7 it counts every private
  writable mapping — the heap and anonymous memory alike — and leaves out address space a
  runtime only reserves, which language runtimes that reserve gigabytes up front (and never
  touch) would otherwise be refused for. A unit that reaches the limit is refused the
  allocation; it fails with its own exit code, which says nothing about why, so the exit is
  not reported as a memory kill. It is a limit per process, not per job: a unit that starts
  several processes gets the limit for each. The CPU share is not limited.
- **Every other system (macOS among them)** — not enforced: the kernel does not apply a data
  limit to memory a process maps. The job is **refused** (deploy/k8s/README.md: a job it
  cannot give limits to is refused), unless the operator has accepted an unenforced limit
  explicitly — `memory_unenforced`, which the composition root sets from
  `TAKTUS_EXECUTION_MEMORY_UNENFORCED` — and then every launch logs that the limit is not
  enforced.

The unit's stdout and stderr go to a log file under the state directory, so that a unit that
fails to start can be read about; credential values never appear on a command line.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import socket
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

from taktus.adapters.driven.execution._common import resolve_credentials, wait_until_healthy
from taktus.ports.configuration import Configuration
from taktus.ports.execution import (
    UNIT_PORT_VARIABLE,
    UNIT_STATE_DIR_VARIABLE,
    ExecutionError,
    ExecutionRefused,
    Isolation,
    JobExit,
    JobRequest,
    refusal,
)

UNIT_WORKSPACE_VARIABLE = "TAKTUS_UNIT_WORKSPACE"
INHERITED = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL")
STOP_GRACE_SECONDS = 5.0
MEMORY_UNENFORCED_KEY = "execution.memory.unenforced"
# Sets the data limit on itself and becomes the unit: the limit survives exec. Run by this
# process's own interpreter, so it needs nothing installed.
LIMIT_LAUNCHER = (
    "import os, resource, sys; "
    "limit = int(sys.argv[1]); "
    "resource.setrlimit(resource.RLIMIT_DATA, (limit, limit)); "
    "os.execvp(sys.argv[2], sys.argv[2:])"
)

logger = structlog.get_logger("taktus.execution.process")


class ProcessJob:
    def __init__(
        self, job_id: str, endpoint: str, process: asyncio.subprocess.Process, log: Path
    ) -> None:
        self._id = job_id
        self._endpoint = endpoint
        self._process = process
        self.log = log
        self.killed: JobExit | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def exit(self) -> JobExit | None:
        if self.killed is not None:
            return self.killed
        code = self._process.returncode
        if code is None:
            return None
        return JobExit(code=code, reason=f"the unit exited with {code}")


class ProcessExecution:
    """`state_dir` is where every unit keeps its state across jobs, one directory per unit,
    and where each job's log is written."""

    isolation = Isolation.NONE

    def __init__(
        self,
        configuration: Configuration,
        *,
        state_dir: Path,
        memory_unenforced: bool = False,
        system: str = sys.platform,
    ) -> None:
        self._configuration = configuration
        self._state_dir = state_dir
        self._memory_unenforced = memory_unenforced
        self._system = system

    @property
    def enforces_memory(self) -> bool:
        """Whether this system lets the adapter enforce a unit's memory limit."""
        return self._system.startswith("linux")

    @asynccontextmanager
    async def launch(self, request: JobRequest) -> AsyncIterator[ProcessJob]:
        if (why := refusal(self.isolation, request.autonomy_level)) is not None:
            raise ExecutionRefused(why)
        for reference in request.credentials:
            if reference.injected_as == "file":
                raise ExecutionRefused(
                    f"credential {reference.name} is injected as a file, which the process "
                    "adapter cannot do: a file credential needs an isolated filesystem — use "
                    "the container adapter"
                )
        limit = request.unit.limits.memory_bytes
        if not self.enforces_memory:
            if not self._memory_unenforced:
                raise ExecutionRefused(
                    f"the unit's memory limit of {limit // (1024 * 1024)} MiB cannot be "
                    f"enforced by the process adapter on this system ({self._system}): only "
                    "Linux limits a child's memory. Use the container adapter, or accept an "
                    "unenforced limit explicitly with "
                    f"{self._configuration.name(MEMORY_UNENFORCED_KEY)}=true"
                )
            logger.warning(
                "memory limit not enforced",
                job=request.job_id,
                memory_bytes=limit,
                system=self._system,
            )
        credentials = resolve_credentials(self._configuration, request.credentials)
        unit_state = self._state_dir / "units" / request.unit.name
        unit_state.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=f"taktus-job-{request.job_id}-"))
        port = _free_port()
        endpoint = f"http://127.0.0.1:{port}"
        # The unit gets what a program needs to run on this machine, the launch convention and
        # the credentials — not this process's own environment, which may carry the paths to
        # the control plane's secrets.
        environment = {
            **{name: os.environ[name] for name in INHERITED if name in os.environ},
            UNIT_PORT_VARIABLE: str(port),
            UNIT_STATE_DIR_VARIABLE: str(unit_state),
            UNIT_WORKSPACE_VARIABLE: str(workspace),
            **{c.reference.name: c.value.reveal() for c in credentials},
        }
        log = unit_state / f"job-{request.job_id}.log"
        with log.open("wb") as handle:
            try:
                process = await asyncio.create_subprocess_exec(
                    *self._command(request),
                    cwd=workspace,
                    env=environment,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=handle,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as error:
                shutil.rmtree(workspace, ignore_errors=True)
                raise ExecutionError(
                    f"the unit {request.unit.program!r} could not be started: {error}"
                ) from error
        job = ProcessJob(request.job_id, endpoint, process, log)

        async def ended() -> str | None:
            return None if process.returncode is None else f"exit code {process.returncode}"

        wall = request.wall_seconds or request.unit.limits.wall_seconds
        wall = min(wall, request.unit.limits.wall_seconds)
        timer = asyncio.create_task(self._kill_after(job, process, wall), name=f"wall-{job.id}")
        try:
            await wait_until_healthy(
                endpoint, within_seconds=request.unit.start_timeout_seconds, ended=ended
            )
            yield job
        finally:
            timer.cancel()
            await self._end(process, job, JobExit(killed="stop", reason="the job is over"))
            shutil.rmtree(workspace, ignore_errors=True)

    def _command(self, request: JobRequest) -> list[str]:
        argv = shlex.split(request.unit.program)
        if not self.enforces_memory:
            return argv
        limit = str(request.unit.limits.memory_bytes)
        return [sys.executable, "-c", LIMIT_LAUNCHER, limit, *argv]

    @staticmethod
    async def _kill_after(job: ProcessJob, process: asyncio.subprocess.Process, wall: int) -> None:
        await asyncio.sleep(wall)
        if process.returncode is None:
            job.killed = JobExit(
                killed="wall", reason=f"the wall-clock limit of {wall}s was exceeded"
            )
            _signal(process, signal.SIGKILL)

    @staticmethod
    async def _end(process: asyncio.subprocess.Process, job: ProcessJob, why: JobExit) -> None:
        if process.returncode is None:
            if job.killed is None:
                job.killed = why
            _signal(process, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
            except TimeoutError:
                _signal(process, signal.SIGKILL)
                await process.wait()


def _signal(process: asyncio.subprocess.Process, signum: signal.Signals) -> None:
    """The unit and everything it started: the unit runs in its own session. A group that is
    already gone — or whose leader has exited and not yet been reaped — is nothing to signal."""
    try:
        os.killpg(process.pid, signum)
    except (ProcessLookupError, PermissionError):
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
