"""The cluster adapter against a real cluster: the container adapter's tests, held to a pod.

The same checks as `test_container.py`, from inside the job — what it can see, what it can
reach — with the answer read back as the step's artifact; and from outside, through the
cluster's API, that the job, its Secret, its Services and its proxy are gone afterwards.

**They need a cluster, and skip with the reason where none is configured.** CI configures none
(NEED-0015), so there they skip, and the skip's reason is printed in the test summary. What
they need, all of it set up as `deploy/k8s/README.md` §1, §4 and §5 describe:

- `TAKTUS_CREDENTIAL_CLUSTER_TEST_KUBECONFIG_FILE`: the path of a kubeconfig whose account
  holds exactly the Role of §1 in the namespace below, authenticating with a bearer token
  (CREDENTIALS.md);
- `TAKTUS_TEST_CLUSTER_NAMESPACE`: that namespace, labelled `restricted`, with the default-deny
  policies of §5 and the exceptions for the labels the adapter sets;
- `TAKTUS_TEST_CLUSTER_WORKER_IMAGE`: the reference worker's image, pullable by the cluster;
- optionally `TAKTUS_TEST_CLUSTER_HOG_IMAGE` (`tests/adapters/execution/hog/`) for the memory
  kill, and `TAKTUS_TEST_CLUSTER_HOSTS`, two hosts the cluster can reach over HTTPS, the first
  allowed and the second not (default `example.com,example.org`);
- and the tests must run where the cluster's service addresses are reachable — in a pod of the
  control plane's namespace, as the control plane does.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import KubernetesExecution
from taktus.adapters.driven.execution.kubernetes.adapter import ClusterJob
from taktus.adapters.driven.execution.kubernetes.api import ClusterApi, Connection
from taktus.ports.execution import ExecutionUnit, JobRequest, ResourceLimits

from .test_container import CREDENTIALS, PLANTED, run_commands

LIMITS = ResourceLimits(cpus=1, memory_bytes=128 * 1024 * 1024, wall_seconds=120)
LOOK_AROUND = [
    "ls /var/run/secrets/kubernetes.io/serviceaccount 2>&1 || echo no-token",
    "id -u",
    "printenv VCS_TOKEN",
    "cat /run/secrets/key",
    "printenv | grep -q SIGNING_KEY && echo in-env || echo not-in-env",
    "touch /app/written 2>&1 || echo read-only",
    f"grep -rl {PLANTED} /run /var /tmp /app /home /etc /workspace 2>/dev/null || echo not-on-disk",
    "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)\" "
    "2>&1 | tail -1",
    "grep CapEff /proc/self/status",
]
PROBE = (
    'python3 -c "import urllib.request, urllib.error\n'
    "try:\n"
    "    print('reached', urllib.request.urlopen('https://{host}/', timeout=10).status)\n"
    "except urllib.error.HTTPError as e:\n"
    "    print('reached', e.code)\n"
    "except Exception as e:\n"
    "    print('refused' if '403' in str(e) else 'unreachable', type(e).__name__, e)\""
)


def needed(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(
            f"the cluster execution tests need a cluster: {name} is not set "
            "(tests/adapters/execution/test_kubernetes_cluster.py says what they need; NEED-0015)"
        )
    return value


@pytest.fixture
def connection() -> Connection:
    return Connection.from_kubeconfig(
        Path(needed("TAKTUS_CREDENTIAL_CLUSTER_TEST_KUBECONFIG_FILE"))
    )


@pytest.fixture
def namespace() -> str:
    return needed("TAKTUS_TEST_CLUSTER_NAMESPACE")


@pytest.fixture
def worker_image() -> str:
    return needed("TAKTUS_TEST_CLUSTER_WORKER_IMAGE")


@pytest.fixture
def execution(connection: Connection, namespace: str, tmp_path: Path) -> KubernetesExecution:
    (tmp_path / "token").write_text(PLANTED + "\n", encoding="utf-8")
    (tmp_path / "key").write_text("key-77aa\n", encoding="utf-8")
    configuration = EnvironmentConfiguration(
        {
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(tmp_path / "token"),
            "TAKTUS_CREDENTIAL_SIGNING_KEY_FILE": str(tmp_path / "key"),
        }
    )
    return KubernetesExecution(
        configuration,
        namespace=namespace,
        state_dir=tmp_path / "state",
        connection=connection,
        egress_image=os.environ.get("TAKTUS_TEST_CLUSTER_EGRESS_IMAGE", "python:3.13-slim"),
    )


def unit(image: str, **more: Any) -> ExecutionUnit:
    return ExecutionUnit(
        name="reference", program=image, limits=LIMITS, start_timeout_seconds=180, **more
    )


async def objects_of(api: ClusterApi, job: ClusterJob) -> dict[str, Any]:
    recorded = await api.get("jobs", job.name)
    assert recorded is not None
    return recorded


async def test_the_job_is_walled_in_and_torn_down(
    execution: KubernetesExecution,
    worker_image: str,
    connection: Connection,
    namespace: str,
    tmp_path: Path,
) -> None:
    request = JobRequest(
        job_id="asg_wall",
        unit=unit(worker_image),
        autonomy_level=4,
        credentials=CREDENTIALS,
    )
    async with ClusterApi(connection, namespace) as api:
        async with execution.launch(request) as job:
            recorded = await objects_of(api, job)
            pods = await api.list("pods", job.selector)
            outputs = await run_commands(job, LOOK_AROUND)  # type: ignore[arg-type]
        pod_spec = recorded["spec"]["template"]["spec"]
        secret = next(
            e["valueFrom"]["secretKeyRef"]["name"]
            for e in pod_spec["containers"][0]["env"]
            if "valueFrom" in e
        )
        # The recorded configuration of the job and its pod carries no credential value.
        assert PLANTED not in json.dumps([recorded, pods]) and "key-77aa" not in json.dumps(pods)
        assert pod_spec["automountServiceAccountToken"] is False
        # Torn down: the job and its Service are gone; the Secret too — deleting it again
        # finds nothing, since the Role grants no read of a Secret.
        for _ in range(30):
            if await api.get("jobs", job.name) is None:
                break
            await asyncio.sleep(1)
        assert await api.get("jobs", job.name) is None
        assert await api.delete("secrets", secret) is False
        assert await api.delete("services", job.name) is False
    assert "no-token" in outputs["output-1"] or "No such file" in outputs["output-1"]
    assert outputs["output-2"].strip() != "0", "not root"
    assert outputs["output-3"].strip() == PLANTED, "the env credential is in the unit's environment"
    assert outputs["output-4"] == "key-77aa", "the file credential is at its path, exactly"
    assert outputs["output-5"].strip() == "not-in-env"
    assert "read-only" in outputs["output-6"], "the root filesystem is read-only"
    assert outputs["output-7"].strip() == "not-on-disk", "the env credential is on no filesystem"
    assert "Error" in outputs["output-8"] or "timed out" in outputs["output-8"], outputs["output-8"]
    assert outputs["output-9"].strip().endswith("0000000000000000"), "no capability"
    log = tmp_path / "state" / "units" / "reference" / "job-asg_wall.log"
    assert log.is_file() and PLANTED not in log.read_text() and "key-77aa" not in log.read_text()


async def test_an_empty_allowlist_reaches_nothing_and_a_named_host_is_reached_through_the_proxy(
    execution: KubernetesExecution, worker_image: str
) -> None:
    allowed, other = os.environ.get("TAKTUS_TEST_CLUSTER_HOSTS", "example.com,example.org").split(
        ","
    )[:2]
    request = JobRequest(
        job_id="asg_hosts",
        unit=unit(worker_image),
        autonomy_level=4,
        allowed_hosts=(allowed,),
    )
    async with execution.launch(request) as job:
        outputs = await run_commands(
            job,  # type: ignore[arg-type]
            [PROBE.format(host=allowed), PROBE.format(host=other), "printenv HTTPS_PROXY"],
            hosts=(allowed,),
        )
    assert outputs["output-1"].startswith("reached"), outputs["output-1"]
    assert outputs["output-2"].startswith("refused"), outputs["output-2"]
    assert outputs["output-3"].strip().startswith("http://taktus:")

    request = JobRequest(job_id="asg_nohost", unit=unit(worker_image), autonomy_level=4)
    async with execution.launch(request) as job:
        outputs = await run_commands(
            job,  # type: ignore[arg-type]
            [PROBE.format(host=allowed), "printenv HTTPS_PROXY || echo no-proxy"],
        )
    assert outputs["output-1"].startswith("unreachable"), outputs["output-1"]
    assert outputs["output-2"].strip() == "no-proxy"


async def test_a_job_that_exceeds_its_memory_limit_is_killed_and_says_so(
    execution: KubernetesExecution,
) -> None:
    import httpx

    hog = needed("TAKTUS_TEST_CLUSTER_HOG_IMAGE")
    small = ExecutionUnit(
        name="hog",
        program=hog,
        limits=ResourceLimits(cpus=1, memory_bytes=32 * 1024 * 1024, wall_seconds=60),
        start_timeout_seconds=180,
    )
    request = JobRequest(job_id="asg_hog", unit=small, autonomy_level=4)
    async with execution.launch(request) as job:
        async with httpx.AsyncClient() as client:
            try:
                await client.get(f"{job.endpoint}/v1/hog", timeout=10.0)
            except httpx.HTTPError:
                pass
        exit = None
        for _ in range(100):
            exit = await job.exit()
            if exit is not None:
                break
            await asyncio.sleep(0.2)
    assert exit is not None, "the job ended: a failure, never a hang"
    assert exit.killed == "memory" and "memory limit" in exit.reason, exit


async def test_the_wall_clock_kills_a_job(
    execution: KubernetesExecution, worker_image: str
) -> None:
    short = unit(worker_image).model_copy(
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
