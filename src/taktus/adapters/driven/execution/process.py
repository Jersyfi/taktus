"""The `process` adapter: an execution unit as a child process of this one. No isolation.

For local development and a single user (ADR-0002). What it does: starts the unit's command
line with a free port and the unit's state directory in its environment, injects the
credentials the job names as environment variables, gives the job a workspace that is removed
when the job ends, waits until the unit answers health, and kills the unit when the wall clock
runs out or the job is over. What it does not do, and cannot: limit memory or CPU, keep the
unit off the network — the unit shares this machine's filesystem and network, and the reach
that `allowed_hosts` names is the worker's own honesty (W-13), not a wall. That is why the port
refuses this adapter from autonomy level 3 upwards, and why a credential injected as a file is
refused here: without a filesystem of its own, a job has no place for one that outlives
nothing.

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
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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

    def __init__(self, configuration: Configuration, *, state_dir: Path) -> None:
        self._configuration = configuration
        self._state_dir = state_dir

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
                    *shlex.split(request.unit.program),
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
    """The unit and everything it started: the unit runs in its own session."""
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
