"""The process adapter against the reference worker: the unit comes up on the port and state
directory the launch convention names, credentials reach its environment and nothing else,
the workspace does not outlive the job, the wall clock kills a unit that runs too long, and
the memory limit is enforced on Linux and refused elsewhere unless accepted unenforced."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import ProcessExecution
from taktus.adapters.driven.execution.process import UNIT_WORKSPACE_VARIABLE
from taktus.ports.execution import (
    ExecutionError,
    ExecutionRefused,
    ExecutionUnit,
    JobRequest,
    ResourceLimits,
)
from taktus.ports.worker import CredentialReference

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "workers" / "script" / "worker.py"
LIMITS = ResourceLimits(cpus=1, memory_bytes=256 * 1024 * 1024, wall_seconds=30)
LINUX = sys.platform.startswith("linux")
# Where the adapter cannot enforce a memory limit it refuses the job; these tests accept the
# unenforced limit there, as an operator would have to, and the tests below the line hold the
# adapter to both halves.
UNENFORCED = not LINUX
# A unit that prints its environment and then serves the contract — the reference worker with
# a preface; what it prints is what the adapter injected.
DUMP = (
    "import os, json; print(json.dumps({k: v for k, v in os.environ.items() "
    "if k.startswith('TAKTUS_') or k == 'VCS_TOKEN'}), flush=True)"
)


def unit(program: str | None = None) -> ExecutionUnit:
    return ExecutionUnit(
        name="reference", program=program or f"{sys.executable} {WORKER}", limits=LIMITS
    )


async def test_the_unit_comes_up_on_the_port_and_state_dir_it_was_given(tmp_path: Path) -> None:
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    request = JobRequest(job_id="job-1", unit=unit(), autonomy_level=2)
    async with execution.launch(request) as job:
        assert job.id == "job-1" and job.endpoint.startswith("http://127.0.0.1:")
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{job.endpoint}/v1/health")
            assert health.status_code == 200
        assert await job.exit() is None
    assert (tmp_path / "state" / "units" / "reference" / "job-job-1.log").is_file()
    exit = await job.exit()
    assert exit is not None and exit.killed == "stop"


async def test_a_credential_reaches_the_unit_s_environment_and_nothing_else(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "token"
    secret_file.write_text("tok-3f9a1c\n", encoding="utf-8")
    configuration = EnvironmentConfiguration({"TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(secret_file)})
    execution = ProcessExecution(
        configuration, state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    serve = f"import runpy; runpy.run_path('{WORKER}', run_name='__main__')"
    program = f'{sys.executable} -c "{DUMP}; {serve}"'
    request = JobRequest(
        job_id="job-2",
        unit=unit(program),
        autonomy_level=1,
        credentials=(CredentialReference(name="VCS_TOKEN", injected_as="env"),),
    )
    async with execution.launch(request):
        log = tmp_path / "state" / "units" / "reference" / "job-job-2.log"
        dumped = log.read_text(encoding="utf-8").splitlines()[0]
        assert '"VCS_TOKEN": "tok-3f9a1c"' in dumped, "the value is in the unit's environment"
        assert "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE" not in dumped, "the path to it is not"
        workspace = Path(json.loads(dumped)[UNIT_WORKSPACE_VARIABLE])
        assert workspace.is_dir()  # noqa: ASYNC240 — a test looks at the filesystem
        # The unit's command line never carries the value: it went through the environment.
        listing = await asyncio.create_subprocess_exec(
            "ps", "-eo", "args", stdout=asyncio.subprocess.PIPE
        )
        out, _ = await listing.communicate()
        units = [line for line in out.decode(errors="replace").splitlines() if "worker.py" in line]
        assert units and not any("tok-3f9a1c" in line for line in units)
    assert not workspace.exists(), "the workspace does not outlive the job"  # noqa: ASYNC240
    # The log carries the dump this test asked for and the worker's own lines; the worker
    # logs presence, never a value — the dump line is the only place the value appears.
    lines = log.read_text(encoding="utf-8").splitlines()[1:]
    assert not any("tok-3f9a1c" in line for line in lines)


async def test_a_missing_credential_is_refused_before_anything_starts(tmp_path: Path) -> None:
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    request = JobRequest(
        job_id="job-3",
        unit=unit(),
        autonomy_level=1,
        credentials=(CredentialReference(name="VCS_TOKEN", injected_as="env"),),
    )
    with pytest.raises(ExecutionRefused, match="TAKTUS_CREDENTIAL_VCS_TOKEN_FILE"):
        async with execution.launch(request):
            pass


async def test_a_file_credential_is_refused_by_the_process_adapter(tmp_path: Path) -> None:
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    request = JobRequest(
        job_id="job-4",
        unit=unit(),
        autonomy_level=1,
        credentials=(CredentialReference(name="KEY", injected_as="file", path="/run/secrets/key"),),
    )
    with pytest.raises(ExecutionRefused, match="container adapter"):
        async with execution.launch(request):
            pass


async def test_a_unit_that_does_not_come_up_is_an_error_that_names_why(tmp_path: Path) -> None:
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    request = JobRequest(
        job_id="job-5", unit=unit(f"{sys.executable} -c 'raise SystemExit(7)'"), autonomy_level=1
    )
    with pytest.raises(ExecutionError, match="exit code 7"):
        async with execution.launch(request):
            pass


async def test_the_wall_clock_kills_the_unit_and_says_so(tmp_path: Path) -> None:
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", memory_unenforced=UNENFORCED
    )
    short = unit().model_copy(
        update={"limits": ResourceLimits(cpus=1, memory_bytes=256 * 1024 * 1024, wall_seconds=1)}
    )
    request = JobRequest(job_id="job-6", unit=short, autonomy_level=1)
    async with execution.launch(request) as job:
        for _ in range(50):
            if await job.exit() is not None:
                break
            await asyncio.sleep(0.1)
        exit = await job.exit()
        assert exit is not None and exit.killed == "wall" and "1s" in exit.reason


# --- the memory limit -------------------------------------------------------------------------

# A unit that prints the data limit it runs under and then serves the contract.
LIMIT_DUMP = (
    "import resource; print('limit', resource.getrlimit(resource.RLIMIT_DATA)[0], flush=True)"
)


@pytest.mark.skipif(not LINUX, reason="only Linux enforces a data limit on a child's memory")
async def test_on_linux_the_unit_runs_under_its_memory_limit(tmp_path: Path) -> None:
    execution = ProcessExecution(EnvironmentConfiguration({}), state_dir=tmp_path / "state")
    assert execution.enforces_memory
    serve = f"import runpy; runpy.run_path('{WORKER}', run_name='__main__')"
    request = JobRequest(
        job_id="job-7", unit=unit(f'{sys.executable} -c "{LIMIT_DUMP}; {serve}"'), autonomy_level=1
    )
    async with execution.launch(request):
        log = tmp_path / "state" / "units" / "reference" / "job-job-7.log"
        first = log.read_text(encoding="utf-8").splitlines()[0]
    assert first == f"limit {LIMITS.memory_bytes}", "the limit reaches the unit through exec"


@pytest.mark.skipif(not LINUX, reason="only Linux enforces a data limit on a child's memory")
async def test_on_linux_a_unit_that_outgrows_its_limit_is_refused_the_memory(
    tmp_path: Path,
) -> None:
    """Allocating past the limit fails inside the unit: it cannot take the machine's memory."""
    execution = ProcessExecution(EnvironmentConfiguration({}), state_dir=tmp_path / "state")
    hog = "b = bytearray(512 * 1024 * 1024)"
    request = JobRequest(
        job_id="job-8", unit=unit(f'{sys.executable} -c "{hog}"'), autonomy_level=1
    )
    with pytest.raises(ExecutionError, match="exited before it was ready"):
        async with execution.launch(request):
            pass
    log = (tmp_path / "state" / "units" / "reference" / "job-job-8.log").read_text()
    assert "MemoryError" in log


@pytest.mark.parametrize("system", ["darwin", "win32", "freebsd14"])
async def test_where_the_limit_cannot_be_enforced_the_job_is_refused(
    tmp_path: Path, system: str
) -> None:
    marker = tmp_path / "started"
    execution = ProcessExecution(
        EnvironmentConfiguration({}), state_dir=tmp_path / "state", system=system
    )
    assert not execution.enforces_memory
    request = JobRequest(job_id="job-9", unit=unit(f"touch {marker}"), autonomy_level=1)
    with pytest.raises(ExecutionRefused, match="TAKTUS_EXECUTION_MEMORY_UNENFORCED=true") as raised:
        async with execution.launch(request):
            pass
    assert f"({system})" in str(raised.value) and "256 MiB" in str(raised.value)
    assert not marker.exists(), "nothing was started"
    assert not (tmp_path / "state").exists(), "nothing was prepared for a refused job"


async def test_an_unenforced_limit_is_the_operator_s_explicit_choice(tmp_path: Path) -> None:
    """Accepted explicitly, the unit starts without a limit and without the launcher."""
    execution = ProcessExecution(
        EnvironmentConfiguration({}),
        state_dir=tmp_path / "state",
        system="darwin",
        memory_unenforced=True,
    )
    request = JobRequest(job_id="job-10", unit=unit(), autonomy_level=1)
    async with execution.launch(request) as job:
        assert job.endpoint.startswith("http://127.0.0.1:")
