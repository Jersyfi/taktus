"""The container adapter against a real engine: the wall around a job, checked from inside it.

The reference worker runs shell commands as steps, so every check below is a command the
job itself runs — what it can see, what it can reach — with the answer read back as the
step's artifact. Needs Docker; skips without it (fails in CI, where Docker is required)."""

# ruff: noqa: S607, ASYNC221, S104 — a test drives the engine's command line and binds a
# stand-in host on every interface of its own container
from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import ContainerExecution
from taktus.adapters.driven.execution.container.adapter import ContainerJob
from taktus.adapters.driven.execution.container.engine import Engine
from taktus.adapters.driven.workers.http import HttpWorker
from taktus.ports.execution import ExecutionUnit, JobRequest, ResourceLimits
from taktus.ports.worker import (
    ArtifactProduced,
    Assignment,
    AssignmentFinished,
    Callback,
    ComputeLimit,
    Context,
    CredentialReference,
    Frame,
    Limits,
    Task,
)

LIMITS = ResourceLimits(cpus=1, memory_bytes=128 * 1024 * 1024, wall_seconds=120)
# The value planted as a credential: distinctive enough to search for, and plainly not one.
PLANTED = "planted-credential-value-for-this-test"
CREDENTIALS = (
    CredentialReference(name="VCS_TOKEN", injected_as="env"),
    CredentialReference(name="SIGNING_KEY", injected_as="file", path="/run/secrets/key"),
)
# What the job says about itself, one command per question, from inside the container.
LOOK_AROUND = [
    "ls /var/run/docker.sock /run/docker.sock 2>&1 || echo no-socket",
    "cat /proc/1/cmdline | tr '\\0' ' '",
    "printenv VCS_TOKEN",
    "cat /run/secrets/key",
    "printenv | grep -q SIGNING_KEY && echo in-env || echo not-in-env",
    "ls -A /run/taktus/credentials",
    f"grep -rl {PLANTED} /run /var /tmp /app /home /etc 2>/dev/null || echo not-on-disk",
    "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)\" "
    "2>&1 | tail -1",
    "mount | grep -q docker.sock && echo socket-mount || echo no-socket-mount",
]
# A request to a host through whatever proxy the environment names: reached, refused, or no
# route at all.
PROBE = (
    'python3 -c "import urllib.request, urllib.error\n'
    "try:\n"
    "    print('reached', urllib.request.urlopen('http://{host}:8000/', timeout=5).status)\n"
    "except urllib.error.HTTPError as e:\n"
    "    print('refused', e.code, e.read().decode().strip())\n"
    "except Exception as e:\n"
    "    print('unreachable', type(e).__name__)\""
)


@pytest.fixture
def execution(engine_socket: str, tmp_path: Path) -> ContainerExecution:
    (tmp_path / "token").write_text(PLANTED + "\n", encoding="utf-8")
    (tmp_path / "key").write_text("key-77aa\n", encoding="utf-8")
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(tmp_path / "token"),
            "TAKTUS_CREDENTIAL_SIGNING_KEY_FILE": str(tmp_path / "key"),
        }
    )
    return ContainerExecution(configuration, socket=engine_socket, state_dir=tmp_path / "state")


def unit(image: str, **more: Any) -> ExecutionUnit:
    return ExecutionUnit(name="reference", program=image, limits=LIMITS, **more)


async def run_commands(
    job: ContainerJob, commands: list[str], *, hosts: tuple[str, ...] = ()
) -> dict[str, str]:
    """Post an assignment whose steps are these commands; each command's output by its
    artifact id. A failed command still yields the output it produced."""
    async with HttpWorker(job.endpoint, idle_timeout=30.0) as worker:
        assignment = Assignment(
            assignment_id="asg_inside01",
            task=Task(goal="look around", acceptance=["done"], inputs={"commands": commands}),
            context=Context(),
            frame=Frame(
                autonomy_level=4, allowed_tools=("shell.script",), allowed_hosts=hosts, max_steps=20
            ),
            limits=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
            credentials=(
                CredentialReference(name="VCS_TOKEN", injected_as="env"),
                CredentialReference(
                    name="SIGNING_KEY", injected_as="file", path="/run/secrets/key"
                ),
            ),
            callback=Callback(events="sse"),
        )
        state = await worker.assign(assignment)
        assert state.status != "finished", state.reason
        outputs: dict[str, str] = {}
        async for event in worker.events(assignment.assignment_id):
            if isinstance(event, ArtifactProduced):
                content = await worker.artifact_bytes(assignment.assignment_id, event.artifact())
                outputs[event.artifact_id] = content.decode(errors="replace")
            elif isinstance(event, AssignmentFinished):
                outputs["outcome"] = f"{event.outcome}: {event.reason or ''}"
        return outputs


async def test_the_job_is_walled_in_and_torn_down(
    execution: ContainerExecution, reference_worker_image: str, engine_socket: str, tmp_path: Path
) -> None:
    request = JobRequest(
        job_id="asg_wall",
        unit=unit(reference_worker_image),
        autonomy_level=4,
        credentials=CREDENTIALS,
    )
    async with Engine(engine_socket) as engine:
        async with execution.launch(request) as job:
            inspected = await engine.inspect(job.unit) or {}
            host_config = inspected["HostConfig"]
            assert (
                host_config["CapDrop"] == ["ALL"]
                and "no-new-privileges" in host_config["SecurityOpt"]
            )
            assert host_config["Memory"] == LIMITS.memory_bytes == host_config["MemorySwap"]
            assert host_config["NanoCpus"] == 1_000_000_000 and host_config["PidsLimit"] == 512
            assert host_config["NetworkMode"].startswith("taktus-job-")
            mounts = inspected["Mounts"]
            assert [m["Type"] for m in mounts] == ["volume"], "the state volume and nothing else"
            assert mounts[0]["Name"] == "taktus-unit-state-reference"
            assert not any("docker.sock" in (m.get("Source") or "") for m in mounts)
            # The container's recorded configuration carries no credential value.
            assert PLANTED not in json.dumps(inspected) and "key-77aa" not in json.dumps(inspected)
            outputs = await run_commands(job, LOOK_AROUND)
            unit_name = inspected["Name"].lstrip("/")
            network = host_config["NetworkMode"]
        # Torn down: the containers and the network are gone, the state volume stays.
        assert await engine.inspect(unit_name) is None
        assert await engine.inspect(job.egress) is None
        listing = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert network not in listing.split()
        volumes = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "taktus-unit-state-reference" in volumes.split()
    assert outputs["output-1"].strip().endswith("no-socket")
    assert "launch" not in outputs["output-2"], (
        "the launcher gave way to the unit: PID 1 is the worker"
    )
    assert "worker.py" in outputs["output-2"]
    assert outputs["output-3"].strip() == PLANTED, "the env credential is in the unit's environment"
    assert outputs["output-4"] == "key-77aa", "the file credential is at its path, exactly"
    assert outputs["output-5"].strip() == "not-in-env"
    assert outputs["output-6"].strip() == "", "nothing is left in the credential directory"
    assert outputs["output-7"].strip() == "not-on-disk", "the value is on no filesystem"
    assert "not-on-disk" in outputs["output-7"] or "/run/secrets/key" not in outputs["output-7"]
    assert "Error" in outputs["output-8"] or "unreachable" in outputs["output-8"].lower(), outputs[
        "output-8"
    ]
    assert outputs["output-9"].strip() == "no-socket-mount"
    log = tmp_path / "state" / "units" / "reference" / "job-asg_wall.log"
    assert log.is_file() and PLANTED not in log.read_text() and "key-77aa" not in log.read_text()


async def test_an_empty_allowlist_reaches_nothing_and_a_named_host_is_reached_through_the_proxy(
    execution: ContainerExecution, reference_worker_image: str, engine_socket: str
) -> None:
    """Two hosts stand in for the outside: two containers on the reachable network. The frame
    names one of them; the job reaches that one through its egress proxy and is refused the
    other, and without any allowed host it has no proxy and no route at all."""
    async with Engine(engine_socket) as engine, two_hosts(engine) as (allowed, other):
        request = JobRequest(
            job_id="asg_hosts",
            unit=unit(reference_worker_image),
            autonomy_level=4,
            allowed_hosts=(allowed,),
        )
        async with execution.launch(request) as job:
            outputs = await run_commands(
                job,
                [PROBE.format(host=allowed), PROBE.format(host=other), "printenv HTTP_PROXY"],
                hosts=(allowed,),
            )
        assert outputs["output-1"].strip() == "reached 200"
        assert (
            outputs["output-2"].startswith("refused 403")
            and "not in the allowlist" in outputs["output-2"]
        )
        assert outputs["output-3"].strip().startswith("http://taktus-egress-")

        request = JobRequest(
            job_id="asg_nohost", unit=unit(reference_worker_image), autonomy_level=4
        )
        async with execution.launch(request) as job:
            outputs = await run_commands(
                job, [PROBE.format(host=allowed), "printenv HTTP_PROXY || echo no-proxy"]
            )
        assert outputs["output-1"].startswith("unreachable"), outputs["output-1"]
        assert outputs["output-2"].strip() == "no-proxy"


async def test_a_job_that_exceeds_its_memory_limit_is_killed_and_says_so(
    execution: ContainerExecution, engine_socket: str, hog_image: str
) -> None:
    """A unit that answers health and then takes more memory than the limit. Taktus's promise
    is the job's: it ends — a failure, never a hang — with a non-zero exit and a reason. That
    the cause was memory is the engine's to say, and the adapter repeats it exactly when the
    engine said it: `killed == "memory"` if and only if the engine reported OOMKilled.

    The engine does not always say it. Under cgroup v2 the kernel's OOM killer may take a
    process inside the container's cgroup without the engine setting OOMKilled; what is left
    is exit code 137, a SIGKILL, which on its own does not say who sent it (issue #29). In that
    branch the adapter names no cause — a guess in a field named `killed` is worse than none —
    and the reason carries the exit code. Both branches are asserted; neither passes silently.
    """
    small = ExecutionUnit(
        name="hog",
        program=hog_image,
        limits=ResourceLimits(cpus=1, memory_bytes=32 * 1024 * 1024, wall_seconds=60),
    )
    request = JobRequest(job_id="asg_hog", unit=small, autonomy_level=4)
    async with Engine(engine_socket) as engine, execution.launch(request) as job:
        async with httpx.AsyncClient() as client:
            await client.get(f"{job.endpoint}/v1/hog", timeout=10.0)
        exit = None
        for _ in range(100):
            exit = await job.exit()
            if exit is not None:
                break
            await asyncio.sleep(0.2)
        engine_state = ((await engine.inspect(job.unit)) or {}).get("State", {})
    assert exit is not None, "the job ended: a failure, never a hang"
    assert exit.code not in (None, 0) and exit.reason, exit
    if engine_state.get("OOMKilled"):
        # The engine named the cause; the adapter repeats it.
        assert exit.killed == "memory" and "memory limit" in exit.reason, exit
    else:
        # The weaker branch, stated: the engine did not name the cause, so neither does the
        # adapter. What is known — a SIGKILL, exit 137 — is in the reason.
        assert exit.killed is None, f"the adapter guessed a cause the engine did not report: {exit}"
        assert exit.code == 137 and "137" in exit.reason, exit


async def test_the_wall_clock_kills_a_job(
    execution: ContainerExecution, reference_worker_image: str
) -> None:
    short = unit(reference_worker_image).model_copy(
        update={"limits": ResourceLimits(cpus=1, memory_bytes=128 * 1024 * 1024, wall_seconds=2)}
    )
    request = JobRequest(job_id="asg_wall2", unit=short, autonomy_level=4)
    async with execution.launch(request) as job:
        exit = None
        for _ in range(60):
            exit = await job.exit()
            if exit is not None:
                break
            await asyncio.sleep(0.2)
        assert exit is not None and exit.killed == "wall" and "2s" in exit.reason


# --- helpers ----------------------------------------------------------------------------------


def listed(kind: str) -> list[str]:
    """The names the engine lists for `network` or `volume`."""
    completed = subprocess.run(  # noqa: S603 — fixed arguments
        ["docker", kind, "ls", "--format", "{{.Name}}"], capture_output=True, text=True, check=True
    )
    return completed.stdout.split()


@asynccontextmanager
async def two_hosts(engine: Engine) -> AsyncIterator[tuple[str, str]]:
    """Two plain HTTP servers on the default bridge, by IP address: what a job may reach and
    what it may not."""
    ids: list[str] = []
    addresses: list[str] = []
    try:
        for n in (1, 2):
            container = await engine.create_container(
                f"taktus-test-host-{n}",
                {
                    "Image": "python:3.13-slim",
                    "Cmd": ["python3", "-m", "http.server", "8000", "--bind", "0.0.0.0"],
                    "HostConfig": {"NetworkMode": "bridge"},
                },
            )
            ids.append(container)
            await engine.start(container)
            inspected = await engine.inspect(container) or {}
            networks = inspected["NetworkSettings"]["Networks"]
            addresses.append(next(iter(networks.values()))["IPAddress"])
        await asyncio.sleep(1.0)
        yield addresses[0], addresses[1]
    finally:
        for container in ids:
            await engine.remove(container)
