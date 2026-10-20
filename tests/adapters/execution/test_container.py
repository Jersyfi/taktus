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
from contextlib import AsyncExitStack, asynccontextmanager
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
async def execution(engine_socket: str, tmp_path: Path) -> AsyncIterator[ContainerExecution]:
    """The adapter with a gateway key drawn for the test: its gateway is the test's alone, and
    closing the adapter removes it."""
    (tmp_path / "token").write_text(PLANTED + "\n", encoding="utf-8")
    (tmp_path / "key").write_text("key-77aa\n", encoding="utf-8")
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(tmp_path / "token"),
            "TAKTUS_CREDENTIAL_SIGNING_KEY_FILE": str(tmp_path / "key"),
        }
    )
    adapter = ContainerExecution(configuration, socket=engine_socket, state_dir=tmp_path / "state")
    try:
        yield adapter
    finally:
        await adapter.close()


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
            gateway = await engine.inspect(job.gateway) or {}
            assert network in gateway["NetworkSettings"]["Networks"], "the gateway joined it"
        # Torn down: the unit and the network are gone, the state volume stays, and the
        # gateway serves the next job, off this job's network.
        assert await engine.inspect(unit_name) is None
        gateway = await engine.inspect(job.gateway) or {}
        assert gateway["State"]["Running"]
        assert network not in gateway["NetworkSettings"]["Networks"]
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
    assert outputs["output-2"].startswith("/bin/sh /taktus/launch"), (
        "the launcher stays in front of the unit, to read the kernel's record of an "
        "out-of-memory kill after it (issue #29)"
    )
    assert "worker.py" in outputs["output-2"], "and runs the image's own command as its child"
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


async def test_the_variables_the_units_configuration_names_reach_its_environment(
    execution: ContainerExecution, reference_worker_image: str
) -> None:
    """ADR-0090: what the operator configured for the worker's unit, beside the convention."""
    request = JobRequest(
        job_id="asg_env",
        unit=unit(reference_worker_image, environment=(("CODING_AGENT_AUTH", "api-key"),)),
        autonomy_level=4,
    )
    async with execution.launch(request) as job:
        outputs = await run_commands(
            job, ["printenv CODING_AGENT_AUTH", "printenv TAKTUS_UNIT_PORT"]
        )
    assert outputs["output-1"].strip() == "api-key"
    assert outputs["output-2"].strip(), "the convention is still there"


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
        proxy = outputs["output-3"].strip()
        assert proxy.startswith("http://taktus:") and f"@{job.gateway}:3128" in proxy, (
            "the instance's gateway, with the job's token"
        )

        request = JobRequest(
            job_id="asg_nohost", unit=unit(reference_worker_image), autonomy_level=4
        )
        async with execution.launch(request) as job:
            outputs = await run_commands(
                job, [PROBE.format(host=allowed), "printenv HTTP_PROXY || echo no-proxy"]
            )
        assert outputs["output-1"].startswith("unreachable"), outputs["output-1"]
        assert outputs["output-2"].strip() == "no-proxy"


async def test_units_share_one_gateway_and_reach_nothing_of_each_other(
    execution: ContainerExecution, reference_worker_image: str, engine_socket: str
) -> None:
    """ADR-0115: two jobs at once are served by one gateway, and each reaches what its own
    token names and nothing else. A job whose hosts name the other job's unit is refused at the
    gateway; it has no route to the other unit, and none to the gateway's inbound port, through
    which the control plane reaches every unit. Without a token, or with a token the gateway's
    key did not sign, the gateway answers 407."""
    async with Engine(engine_socket) as engine, two_hosts(engine) as (allowed, other):
        async with AsyncExitStack() as stack:
            first = await stack.enter_async_context(
                execution.launch(
                    JobRequest(
                        job_id="asg_first",
                        unit=unit(reference_worker_image),
                        autonomy_level=4,
                        allowed_hosts=(allowed,),
                    )
                )
            )
            first_name = await unit_name_of(engine, first)
            second = await stack.enter_async_context(
                execution.launch(
                    JobRequest(
                        job_id="asg_second",
                        unit=unit(reference_worker_image),
                        autonomy_level=4,
                        allowed_hosts=(other, first_name),
                    )
                )
            )
            assert first.gateway == second.gateway, "one gateway for both jobs"
            second_name = await unit_name_of(engine, second)
            gateway = await engine.inspect(first.gateway) or {}
            networks = gateway["NetworkSettings"]["Networks"]
            inbound = next(
                n["IPAddress"] for name, n in networks.items() if not name.startswith("taktus-job-")
            )
            port = unit(reference_worker_image).port
            mine = await run_commands(
                first,
                [
                    REACH.format(host=second_name, port=port),
                    REACH.format(host=inbound, port=8080),
                    ASK.format(header=""),
                    ASK.format(header=FORGED),
                ],
                hosts=(allowed,),
            )
            theirs = await run_commands(
                second,
                [
                    PROBE.format(host=allowed),
                    PROBE.format(host=other),
                    PROBE.format(host=first_name),
                ],
                hosts=(other, first_name),
            )
    assert theirs["output-1"].startswith("refused 403"), "the first job's host is not the second's"
    assert theirs["output-2"].strip() == "reached 200", "its own host is"
    assert mine["output-1"].startswith("unreachable"), "no route to another unit"
    assert mine["output-2"].startswith("unreachable"), "no route to the gateway's inbound port"
    assert mine["output-3"].startswith("refused 407"), "no token, no proxy"
    assert mine["output-4"].startswith("refused 407"), "a token the gateway did not sign"
    assert theirs["output-3"].startswith("refused 502"), theirs["output-3"]
    assert "job's network" in theirs["output-3"], "a token that names a unit does not reach it"


async def test_a_job_that_exceeds_its_memory_limit_is_killed_and_says_so(
    execution: ContainerExecution, hog_image: str
) -> None:
    """A unit that answers health and then takes more memory than the limit: the job ends — a
    failure, never a hang — and says it was the memory limit.

    The adapter does not rely on the engine alone for that. The engine's `OOMKilled` flag is set
    by an event separate from the exit, which may arrive after the exit is visible, or not at
    all (issue #29). The launcher in front of the unit reads the kernel's own counter of
    out-of-memory kills in the unit's cgroup after the unit died, and says so in the log; the
    adapter classifies the kill from either record. So the test asserts the memory kill
    without a weaker branch.
    """
    small = ExecutionUnit(
        name="hog",
        program=hog_image,
        limits=ResourceLimits(cpus=1, memory_bytes=32 * 1024 * 1024, wall_seconds=60),
    )
    request = JobRequest(job_id="asg_hog", unit=small, autonomy_level=4)
    async with execution.launch(request) as job:
        async with httpx.AsyncClient() as client:
            await client.get(f"{job.endpoint}/v1/hog", timeout=10.0)
        exit = None
        for _ in range(100):
            exit = await job.exit()
            if exit is not None:
                break
            await asyncio.sleep(0.2)
    assert exit is not None, "the job ended: a failure, never a hang"
    assert exit.code == 137 and exit.killed == "memory", exit
    assert "memory limit" in exit.reason, exit


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

# A plain connection, past any proxy: what the job's network itself lets through.
REACH = (
    'python3 -c "import socket\n'
    "try:\n"
    "    socket.create_connection(('{host}', {port}), timeout=3)\n"
    "    print('reached')\n"
    "except Exception as e:\n"
    "    print('unreachable', type(e).__name__)\""
)
# A request through the proxy the environment names, with the authorisation the command gives
# in place of the job's own token.
ASK = (
    'python3 -c "import os, socket, urllib.parse\n'
    "proxy = urllib.parse.urlsplit(os.environ['HTTP_PROXY'])\n"
    "s = socket.create_connection((proxy.hostname, proxy.port), timeout=5)\n"
    "s.sendall(b'CONNECT example.org:443 HTTP/1.1\\r\\n{header}\\r\\n')\n"
    "line = s.recv(200).split(b'\\r\\n')[0].decode()\n"
    "print('refused' if ' 200 ' not in line else 'reached', line.split(' ')[1])\""
)
# A token in the gateway's shape whose signature no key of the instance made.
FORGED = "Proxy-Authorization: Basic dGFrdHVzOmV5SjJJam94ZlEuQUFBQQ==\\r\\n"


async def unit_name_of(engine: Engine, job: ContainerJob) -> str:
    return ((await engine.inspect(job.unit)) or {})["Name"].lstrip("/")


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
