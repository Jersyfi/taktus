"""The cluster adapter against a fake of the cluster's API: always runs, needs nothing.

What a frame turns into — the Job, its Secret, its Services, its egress proxy — read from the
objects the fake keeps; what is refused before anything is created; that everything is deleted
whatever the outcome; and that no call leaves the Role of Taktus's service account
(`deploy/k8s/README.md` §1). The unit itself is a stand-in that answers health on this machine,
at the address the fake gives the unit's Service. `test_kubernetes_cluster.py` holds the same
adapter to the container adapter's tests on a real cluster."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import KubernetesExecution
from taktus.adapters.driven.execution.container.egress import Allowlist, proxy
from taktus.adapters.driven.execution.kubernetes.adapter import EGRESS_SOURCE
from taktus.adapters.driven.execution.kubernetes.api import Connection
from taktus.ports.configuration import Secret
from taktus.ports.execution import (
    ExecutionError,
    ExecutionRefused,
    ExecutionUnit,
    JobRequest,
    ResourceLimits,
)
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import AutonomyLevel

from .cluster_fake import FakeCluster, restricted_violations

NAMESPACE = "execution"
LIMITS = ResourceLimits(cpus=0.5, memory_bytes=256 * 1024 * 1024, wall_seconds=120)
PLANTED = "planted-credential-value-for-this-test"
FILE_VALUE = "key-77aa"
CREDENTIALS = (
    CredentialReference(name="VCS_TOKEN", injected_as="env"),
    CredentialReference(name="SIGNING_KEY", injected_as="file", path="/run/secrets/key"),
)


@pytest.fixture
async def unit_port() -> AsyncIterator[int]:
    """A stand-in for the unit: answers every request with 200, on a free port."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    async with server:
        yield server.sockets[0].getsockname()[1]


@pytest.fixture
def cluster() -> FakeCluster:
    return FakeCluster(namespace=NAMESPACE)


@pytest.fixture
def configuration(tmp_path: Path) -> EnvironmentConfiguration:
    (tmp_path / "token").write_text(PLANTED + "\n", encoding="utf-8")
    (tmp_path / "key").write_text(FILE_VALUE + "\n", encoding="utf-8")
    return EnvironmentConfiguration(
        {
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(tmp_path / "token"),
            "TAKTUS_CREDENTIAL_SIGNING_KEY_FILE": str(tmp_path / "key"),
        }
    )


def execution_for(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, **more: Any
) -> KubernetesExecution:
    return KubernetesExecution(
        configuration,
        namespace=NAMESPACE,
        state_dir=tmp_path / "state",
        connection=Connection(server="https://cluster.test", token=Secret("fake-api-token")),
        transport=cluster.transport(),
        **more,
    )


def request_for(port: int, **more: Any) -> JobRequest:
    defaults: dict[str, Any] = {
        "job_id": "asg_Cluster01",
        "unit": ExecutionUnit(name="reference", program="worker:1", port=port, limits=LIMITS),
        "autonomy_level": 4,
    }
    return JobRequest(**(defaults | more))


@pytest.fixture(autouse=True)
def _within_the_role(cluster: FakeCluster) -> Any:
    """Every test: no call outside the Role of Taktus's service account."""
    yield
    assert cluster.forbidden == [], f"calls outside the Role: {cluster.forbidden}"


# --- what a frame produces ---------------------------------------------------------------------


async def test_the_job_a_frame_produces_carries_every_field(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path, state_claim="unit-state")
    request = request_for(unit_port, credentials=CREDENTIALS, allowed_hosts=("api.example.org",))
    async with execution.launch(request) as job:
        jobs = dict(cluster.of("jobs"))
        unit = jobs[job.name]
        egress = next(j for n, j in jobs.items() if n != job.name)
        secret = next(iter(cluster.of("secrets").values()))
        services = dict(cluster.of("services"))
        assert job.endpoint == f"http://127.0.0.1:{unit_port}", "the unit's Service address"

    spec = unit["spec"]
    assert spec["backoffLimit"] == 0
    assert spec["activeDeadlineSeconds"] == LIMITS.wall_seconds + 60
    assert spec["ttlSecondsAfterFinished"] > 0
    pod = spec["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    assert pod["automountServiceAccountToken"] is False
    assert pod["enableServiceLinks"] is False
    assert restricted_violations(pod) == []
    (container,) = pod["containers"]
    assert container["image"] == "worker:1"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    limits = container["resources"]["limits"]
    assert limits == {"cpu": "500m", "memory": str(256 * 1024 * 1024)}
    assert container["resources"]["requests"] == limits
    env = {e["name"]: e for e in container["env"]}
    assert env["TAKTUS_UNIT_PORT"]["value"] == str(unit_port)
    assert env["TAKTUS_UNIT_STATE_DIR"]["value"] == "/var/lib/taktus/unit"
    secret_name = secret["metadata"]["name"]
    assert env["VCS_TOKEN"]["valueFrom"]["secretKeyRef"] == {
        "name": secret_name,
        "key": "VCS_TOKEN",
    }
    assert "SIGNING_KEY" not in env, "a file credential is not in the environment"
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert env[variable]["valueFrom"]["secretKeyRef"]["name"] == secret_name
    mounts = {m["mountPath"]: m for m in container["volumeMounts"]}
    assert mounts["/run/secrets/key"]["subPath"] == "SIGNING_KEY"
    assert mounts["/run/secrets/key"]["readOnly"] is True
    assert {"/tmp", "/workspace", "/var/lib/taktus/unit"} <= set(mounts)  # noqa: S108
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert volumes["state"]["persistentVolumeClaim"]["claimName"] == "unit-state"
    assert volumes["credentials"]["secret"]["items"] == [
        {"key": "SIGNING_KEY", "path": "SIGNING_KEY", "mode": 0o440}
    ]
    # The recorded configuration of every object but the Secret carries no value.
    recorded = json.dumps([unit, egress, *services.values()])
    assert PLANTED not in recorded and FILE_VALUE not in recorded
    assert base64.b64encode(PLANTED.encode()).decode() not in recorded
    # The Secret carries the values, is immutable, and is owned by the unit's Job.
    values = {k: base64.b64decode(v).decode() for k, v in secret["data"].items()}
    assert values["VCS_TOKEN"] == PLANTED and values["SIGNING_KEY"] == FILE_VALUE
    assert secret["immutable"] is True
    uid = unit["metadata"]["uid"]
    for owned in (secret, egress, *services.values()):
        assert owned["metadata"]["ownerReferences"][0]["uid"] == uid
    # The egress proxy: a Job of its own with the frame's hosts, restricted too, a token from
    # the Secret, and a Service whose address is in the unit's proxy URL.
    proxy_pod = egress["spec"]["template"]["spec"]
    assert restricted_violations(proxy_pod) == []
    assert proxy_pod["automountServiceAccountToken"] is False
    (proxy_container,) = proxy_pod["containers"]
    args = proxy_container["args"]
    assert args[args.index("--allow") + 1] == "api.example.org"
    assert proxy_container["command"][:2] == ["python3", "-c"]
    assert proxy_container["command"][2] == EGRESS_SOURCE.read_text(encoding="utf-8")
    assert proxy_container["resources"]["limits"] == proxy_container["resources"]["requests"]
    assert egress["spec"]["backoffLimit"] == 0
    proxy_service = next(
        s for s in services.values() if s["metadata"]["labels"]["taktus/role"] == "egress"
    )
    token = values["taktus-egress-token"]
    assert values["taktus-egress-url"] == (
        f"http://taktus:{token}@{proxy_service['spec']['clusterIP']}:3128"
    )
    assert token not in recorded
    unit_service = services[unit["metadata"]["name"]]
    assert unit_service["spec"]["selector"] == {
        "taktus/job": unit["metadata"]["labels"]["taktus/job"],
        "taktus/role": "unit",
    }


async def test_a_job_without_hosts_has_no_proxy_and_no_secret_without_credentials(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path)
    async with execution.launch(request_for(unit_port)) as job:
        assert [r for r, _ in cluster.everything()] == ["jobs", "pods", "services"]
        pod = cluster.of("jobs")[job.name]["spec"]["template"]["spec"]
        names = {e["name"] for e in pod["containers"][0]["env"]}
        assert not names & {"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"}
        assert pod["volumes"][2] == {"name": "state", "emptyDir": {}}, "no claim: dies with job"


# --- refused before anything is created ----------------------------------------------------------


async def test_a_job_without_a_limit_is_refused(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    unlimited = ExecutionUnit.model_construct(
        name="reference",
        program="worker:1",
        port=unit_port,
        state_dir="/var/lib/taktus/unit",
        limits=ResourceLimits.model_construct(cpus=1.0, memory_bytes=None, wall_seconds=60),
        start_timeout_seconds=60,
    )
    request = JobRequest.model_construct(
        job_id="asg_nolimit",
        unit=unlimited,
        autonomy_level=2,
        allowed_hosts=(),
        credentials=(),
        wall_seconds=None,
    )
    with pytest.raises(ExecutionRefused, match="no limit for memory_bytes"):
        async with execution_for(cluster, configuration, tmp_path).launch(request):
            pass
    assert cluster.calls == [], "nothing was created"


async def test_a_memory_limit_no_runtime_enforces_is_refused(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    tiny = ResourceLimits(cpus=1, memory_bytes=1024 * 1024, wall_seconds=60)
    unit = ExecutionUnit(name="reference", program="worker:1", port=unit_port, limits=tiny)
    with pytest.raises(ExecutionRefused, match="below what a runtime enforces"):
        async with execution_for(cluster, configuration, tmp_path).launch(
            request_for(unit_port, unit=unit)
        ):
            pass
    assert cluster.calls == []


async def test_hosts_on_a_cluster_that_does_not_enforce_network_policies_are_refused(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path, enforce_egress=False)
    request = request_for(unit_port, autonomy_level=1, allowed_hosts=("api.example.org",))
    with pytest.raises(ExecutionRefused, match=r"names allowed hosts.*§6"):
        async with execution.launch(request):
            pass
    assert cluster.calls == []


@pytest.mark.parametrize("level", [3, 4, None])
async def test_isolation_that_does_not_suffice_for_the_level_is_refused(
    cluster: FakeCluster,
    configuration: EnvironmentConfiguration,
    tmp_path: Path,
    unit_port: int,
    level: AutonomyLevel | None,
) -> None:
    """Without enforced network policies the pod's network is open: the cluster isolates less
    than a level from 3 upwards needs, and an unknown level is treated as one that does."""
    execution = execution_for(cluster, configuration, tmp_path, enforce_egress=False)
    with pytest.raises(ExecutionRefused, match="ADR-0002"):
        async with execution.launch(request_for(unit_port, autonomy_level=level)):
            pass
    assert cluster.calls == []


async def test_below_level_3_a_job_without_hosts_runs_where_policies_are_not_enforced(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path, enforce_egress=False)
    async with execution.launch(request_for(unit_port, autonomy_level=2)) as job:
        assert job.endpoint.endswith(f":{unit_port}")


async def test_a_credential_that_is_not_configured_is_refused(
    cluster: FakeCluster, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, EnvironmentConfiguration({}), tmp_path)
    with pytest.raises(ExecutionRefused, match="VCS_TOKEN is not configured"):
        async with execution.launch(request_for(unit_port, credentials=CREDENTIALS[:1])):
            pass
    assert cluster.calls == []


# --- deleted whatever the outcome ---------------------------------------------------------------


def assert_all_deleted(cluster: FakeCluster) -> None:
    assert cluster.everything() == [], f"left behind: {cluster.everything()}"
    kinds = {resource for resource, _, _ in cluster.deletions}
    assert kinds >= {"jobs", "services", "secrets"}
    assert all(policy == "Background" for _, _, policy in cluster.deletions), (
        "a job deleted without propagation leaves its pods"
    )


async def test_everything_is_deleted_on_success(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(unit_port, credentials=CREDENTIALS, allowed_hosts=("a.example.org",))
    async with execution.launch(request):
        assert len(cluster.of("jobs")) == 2
    assert_all_deleted(cluster)
    deleted = [(r, n) for r, n, _ in cluster.deletions]
    assert len([r for r, _ in deleted if r == "jobs"]) == 2, "both jobs, explicitly"


async def test_everything_is_deleted_on_failure(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(unit_port, credentials=CREDENTIALS, allowed_hosts=("a.example.org",))
    with pytest.raises(RuntimeError, match="the step failed"):
        async with execution.launch(request):
            raise RuntimeError("the step failed")
    assert_all_deleted(cluster)


async def test_everything_is_deleted_on_stop(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    """A stop is the task that holds the job being cancelled."""
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(unit_port, credentials=CREDENTIALS, allowed_hosts=("a.example.org",))
    entered = asyncio.Event()
    stopped: list[Any] = []

    async def hold() -> None:
        async with execution.launch(request) as job:
            stopped.append(job)
            entered.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(hold())
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_all_deleted(cluster)
    assert stopped[0].killed is not None and stopped[0].killed.killed == "stop"


async def test_everything_is_deleted_when_the_unit_never_becomes_ready(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path
) -> None:
    """No unit listens at the Service's address; the pod says why, and the error says it."""

    def waiting(pod: dict[str, Any]) -> None:
        for status in pod["status"]["containerStatuses"]:
            status["state"] = {"waiting": {"reason": "ImagePullBackOff", "message": "no such"}}

    cluster.on_pod = waiting
    unit = ExecutionUnit(
        name="reference", program="worker:1", port=1, limits=LIMITS, start_timeout_seconds=1
    )
    execution = execution_for(cluster, configuration, tmp_path)
    with pytest.raises(ExecutionError, match="ImagePullBackOff"):
        async with execution.launch(request_for(1, unit=unit, credentials=CREDENTIALS)):
            pass
    assert_all_deleted(cluster)


async def test_the_units_log_is_kept_and_carries_no_credential(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path)
    async with execution.launch(request_for(unit_port, credentials=CREDENTIALS)) as job:
        cluster.logs[f"{job.name}-pod"] = b"serving on 9000\n"
    kept = tmp_path / "state" / "units" / "reference" / "job-asg_Cluster01.log"
    assert kept.read_bytes() == b"serving on 9000\n"


# --- how a job ended -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("terminated", "condition", "killed", "code"),
    [
        ({"exitCode": 137, "reason": "OOMKilled"}, None, "memory", 137),
        ({"exitCode": 3, "reason": "Error"}, None, None, 3),
        (None, {"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}, "wall", 137),
    ],
)
async def test_how_a_job_ended_is_read_from_the_cluster(
    cluster: FakeCluster,
    configuration: EnvironmentConfiguration,
    tmp_path: Path,
    unit_port: int,
    terminated: dict[str, Any] | None,
    condition: dict[str, Any] | None,
    killed: str | None,
    code: int,
) -> None:
    execution = execution_for(cluster, configuration, tmp_path)
    async with execution.launch(request_for(unit_port)) as job:
        assert await job.exit() is None
        if terminated is not None:
            pod = cluster.of("pods")[f"{job.name}-pod"]
            pod["status"]["containerStatuses"][0]["state"] = {"terminated": terminated}
        if condition is not None:
            cluster.of("jobs")[job.name]["status"] = {"conditions": [condition]}
        exit = await job.exit()
    assert exit is not None and exit.killed == killed and exit.code == code, exit


async def test_the_wall_clock_deletes_the_job(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    short = ResourceLimits(cpus=1, memory_bytes=64 * 1024 * 1024, wall_seconds=1)
    unit = ExecutionUnit(name="reference", program="worker:1", port=unit_port, limits=short)
    execution = execution_for(cluster, configuration, tmp_path)
    async with execution.launch(request_for(unit_port, unit=unit)) as job:
        for _ in range(50):
            if (exit := await job.exit()) is not None:
                break
            await asyncio.sleep(0.1)
        assert exit is not None and exit.killed == "wall" and "1s" in exit.reason
        assert job.name not in cluster.of("jobs"), "the job was deleted, and its pod with it"


# --- the proxy admits its own unit only ------------------------------------------------------


async def test_the_proxy_answers_407_without_the_jobs_token() -> None:
    """In a cluster the namespace's policy cannot tell one job's proxy from another's; the token
    can. Without it, or with another job's, the proxy refuses before it looks at the host."""

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    target = await asyncio.start_server(upstream, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    server = await asyncio.start_server(
        proxy(Allowlist([f"127.0.0.1:{target_port}"]), "the-token"), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]

    async def connect(authorisation: str | None) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        header = f"Proxy-Authorization: {authorisation}\r\n" if authorisation else ""
        writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n{header}\r\n".encode())
        await writer.drain()
        line = await reader.readline()
        writer.close()
        return line

    good = "Basic " + base64.b64encode(b"taktus:the-token").decode()
    wrong = "Basic " + base64.b64encode(b"taktus:another-jobs-token").decode()
    async with server, target:
        assert b"407" in await connect(None)
        assert b"407" in await connect(wrong)
        assert b"200" in await connect(good)


async def test_a_client_that_sends_the_proxy_url_credentials_reaches_through_the_proxy() -> None:
    """The unit finds its proxy as `http://taktus:<token>@address:port`; a client that honours
    the variable sends the token by itself — here httpx, as the workers' Python would."""

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nreached")
        await writer.drain()
        writer.close()

    target = await asyncio.start_server(upstream, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    server = await asyncio.start_server(
        proxy(Allowlist([f"127.0.0.1:{target_port}"]), "tok-1"), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]
    async with server, target:
        async with httpx.AsyncClient(proxy=f"http://taktus:tok-1@127.0.0.1:{port}") as client:
            response = await client.get(f"http://127.0.0.1:{target_port}/")
        async with httpx.AsyncClient(proxy=f"http://taktus:other@127.0.0.1:{port}") as client:
            refused = await client.get(f"http://127.0.0.1:{target_port}/")
    assert response.text == "reached"
    assert refused.status_code == 407
