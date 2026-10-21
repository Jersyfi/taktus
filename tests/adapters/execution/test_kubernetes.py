"""The cluster adapter against a fake of the cluster's API: always runs, needs nothing.

What a frame turns into — the Job, its Secret, its Service, and the token that names its hosts
at the instance's egress gateway (ADR-0115) — read from the objects the fake keeps; what is
refused before anything is created; that everything is deleted whatever the outcome; and that
no call leaves the Role of Taktus's service account (`deploy/k8s/README.md` §1). The unit
itself is a stand-in that answers health on this machine, at the address the fake gives the
unit's Service. `test_kubernetes_cluster.py` holds the same adapter to the container adapter's
tests on a real cluster."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import KubernetesExecution
from taktus.adapters.driven.execution.container.egress import mint, proxy, signed, verify
from taktus.adapters.driven.execution.kubernetes.api import Connection
from taktus.ports.configuration import Secret
from taktus.ports.execution import (
    ExecutionAtCapacity,
    ExecutionError,
    ExecutionRefused,
    ExecutionUnit,
    JobRequest,
    ResourceLimits,
    reach,
)
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import AutonomyLevel

from .cluster_fake import GATEWAY_ADDRESS, FakeCluster, restricted_violations

NAMESPACE = "execution"
LIMITS = ResourceLimits(cpus=0.5, memory_bytes=256 * 1024 * 1024, wall_seconds=120)
PLANTED = "planted-credential-value-for-this-test"
FILE_VALUE = "key-77aa"
GATEWAY_KEY = b"gateway-key-for-this-test"
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
    (tmp_path / "gateway").write_bytes(GATEWAY_KEY + b"\n")
    return EnvironmentConfiguration(
        {
            "TAKTUS_CREDENTIAL_VCS_TOKEN_FILE": str(tmp_path / "token"),
            "TAKTUS_CREDENTIAL_SIGNING_KEY_FILE": str(tmp_path / "key"),
            "TAKTUS_EXECUTION_GATEWAY_KEY_FILE": str(tmp_path / "gateway"),
        }
    )


def hosts_of(cluster: FakeCluster) -> list[str]:
    """The hosts the token in the job's Secret names, as the gateway reads them."""
    url = cluster.secret_values()["taktus-egress-url"]
    token = url.removeprefix("http://taktus:").split("@", 1)[0]
    allowlist = verify(GATEWAY_KEY, token, now=0)
    assert allowlist is not None, "the gateway's key signed it"
    return sorted(allowlist.entries)


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
        assert list(jobs) == [job.name], "one Job: the unit's, and no proxy of its own"
        unit = jobs[job.name]
        secret = next(iter(cluster.of("secrets").values()))
        hosts = hosts_of(cluster)
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
    assert container["resources"]["requests"] == limits, "a share of 1: the whole limit"
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
    recorded = json.dumps([unit, *services.values()])
    assert PLANTED not in recorded and FILE_VALUE not in recorded
    assert base64.b64encode(PLANTED.encode()).decode() not in recorded
    # The Secret carries the values, is immutable, and is owned by the unit's Job.
    values = {k: base64.b64decode(v).decode() for k, v in secret["data"].items()}
    assert values["VCS_TOKEN"] == PLANTED and values["SIGNING_KEY"] == FILE_VALUE
    assert secret["immutable"] is True
    uid = unit["metadata"]["uid"]
    for owned in (secret, *services.values()):
        assert owned["metadata"]["ownerReferences"][0]["uid"] == uid
    # The instance's gateway, by its Service's address, with a token that names the frame's
    # hosts, signed with the gateway's key; the token is in the Secret and nowhere else.
    url = values["taktus-egress-url"]
    assert url.startswith("http://taktus:") and url.endswith(f"@{GATEWAY_ADDRESS}:3128")
    assert hosts == ["api.example.org"]
    token = url.removeprefix("http://taktus:").split("@", 1)[0]
    assert token not in recorded and "taktus-egress-token" not in values
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


async def test_the_proxy_admits_the_frames_hosts_and_the_workers_service_hosts(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    """ADR-0089: a unit whose worker names service hosts reaches them beside the frame's —
    the hosts a launched worker hands the adapter for an assignment (`reach`)."""
    unit = ExecutionUnit(
        name="coding",
        program="worker:1",
        port=unit_port,
        limits=LIMITS,
        service_hosts=("model.example.net", "api.example.org"),
    )
    hosts = reach(unit, ("api.example.org",))
    assert hosts == ("api.example.org", "model.example.net"), "the frame's first, each once"
    execution = execution_for(cluster, configuration, tmp_path)
    async with execution.launch(request_for(unit_port, unit=unit, allowed_hosts=hosts)):
        assert hosts_of(cluster) == ["api.example.org", "model.example.net"]


async def test_the_variables_the_units_configuration_names_are_plain_values_in_the_pod(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    """ADR-0090: configuration, not a secret — a value in the pod's environment, beside the
    convention's, and nothing of it in the job's Secret."""
    unit = ExecutionUnit(
        name="coding",
        program="worker:1",
        port=unit_port,
        limits=LIMITS,
        environment=(("CODING_AGENT_AUTH", "api-key"), ("CODING_AGENT_MODEL", "m-1")),
    )
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(unit_port, unit=unit, credentials=CREDENTIALS[:1])
    async with execution.launch(request) as job:
        pod = cluster.of("jobs")[job.name]["spec"]["template"]["spec"]
        secret = next(iter(cluster.of("secrets").values()))
    env = {e["name"]: e for e in pod["containers"][0]["env"]}
    assert env["CODING_AGENT_AUTH"] == {"name": "CODING_AGENT_AUTH", "value": "api-key"}
    assert env["CODING_AGENT_MODEL"] == {"name": "CODING_AGENT_MODEL", "value": "m-1"}
    assert env["TAKTUS_UNIT_PORT"]["value"] == str(unit_port)
    assert "secretKeyRef" in env["VCS_TOKEN"]["valueFrom"]
    assert "CODING_AGENT_AUTH" not in secret["data"]


async def test_a_credential_under_a_configured_variables_name_is_refused_before_anything(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    unit = ExecutionUnit(
        name="coding",
        program="worker:1",
        port=unit_port,
        limits=LIMITS,
        environment=(("SIGNING", "x"),),
    )
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(
        unit_port,
        unit=unit,
        credentials=(CredentialReference(name="SIGNING", injected_as="env"),),
    )
    with pytest.raises(ExecutionRefused, match="either configuration or a credential"):
        async with execution.launch(request):
            pass
    assert cluster.everything() == [], "nothing was created"


async def test_service_hosts_alone_get_a_token_and_a_frame_without_hosts_reaches_them(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    unit = ExecutionUnit(
        name="coding",
        program="worker:1",
        port=unit_port,
        limits=LIMITS,
        service_hosts=("model.example.net",),
    )
    execution = execution_for(cluster, configuration, tmp_path)
    request = request_for(unit_port, unit=unit, allowed_hosts=reach(unit, ()))
    async with execution.launch(request):
        assert hosts_of(cluster) == ["model.example.net"]


async def test_service_hosts_on_a_cluster_that_does_not_enforce_network_policies_are_refused(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    unit = ExecutionUnit(
        name="coding",
        program="worker:1",
        port=unit_port,
        limits=LIMITS,
        service_hosts=("model.example.net",),
    )
    execution = execution_for(cluster, configuration, tmp_path, enforce_egress=False)
    request = request_for(unit_port, unit=unit, autonomy_level=1, allowed_hosts=reach(unit, ()))
    with pytest.raises(ExecutionRefused, match="service hosts"):
        async with execution.launch(request):
            pass
    assert cluster.calls == []


@pytest.mark.parametrize(
    ("share", "cpu_request"),
    [(0.25, "125m"), (0.5, "250m"), (1.0, "500m"), (0.001, "1m")],
)
async def test_a_unit_requests_a_share_of_its_cpu_and_all_of_its_memory(
    cluster: FakeCluster,
    configuration: EnvironmentConfiguration,
    tmp_path: Path,
    unit_port: int,
    share: float,
    cpu_request: str,
) -> None:
    """Issue #244: CPU is compressible, so a unit reserves a share of its CPU limit on the node
    and may use the rest while the node has it to spare; memory is not — the node has no swap —
    so the memory request is the memory limit. A share of 1 requests the whole limit, as before;
    a request is never below one millicore."""
    execution = execution_for(cluster, configuration, tmp_path, cpu_request_share=share)
    async with execution.launch(request_for(unit_port)) as job:
        pod = cluster.of("jobs")[job.name]["spec"]["template"]["spec"]
    resources = pod["containers"][0]["resources"]
    memory = str(LIMITS.memory_bytes)
    assert resources["limits"] == {"cpu": "500m", "memory": memory}, "the limits do not move"
    assert resources["requests"] == {"cpu": cpu_request, "memory": memory}


@pytest.mark.parametrize("share", [0.0, -0.25, 1.5])
def test_a_cpu_request_share_outside_zero_to_one_is_refused(
    configuration: EnvironmentConfiguration, tmp_path: Path, share: float
) -> None:
    with pytest.raises(ValueError, match="CPU request share"):
        execution_for(
            FakeCluster(namespace=NAMESPACE), configuration, tmp_path, cpu_request_share=share
        )


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


async def test_hosts_without_a_gateway_key_are_refused(
    cluster: FakeCluster, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, EnvironmentConfiguration({}), tmp_path)
    request = request_for(unit_port, allowed_hosts=("api.example.org",))
    with pytest.raises(ExecutionRefused, match="TAKTUS_EXECUTION_GATEWAY_KEY_FILE"):
        async with execution.launch(request):
            pass
    assert cluster.calls == []


async def test_hosts_without_the_gateways_service_are_refused(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path, unit_port: int
) -> None:
    execution = execution_for(cluster, configuration, tmp_path, gateway_service="elsewhere")
    request = request_for(unit_port, allowed_hosts=("api.example.org",))
    with pytest.raises(ExecutionRefused, match="Service elsewhere does not exist"):
        async with execution.launch(request):
            pass
    assert cluster.everything() == [], "nothing was created"


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
        assert len(cluster.of("jobs")) == 1, "the unit's Job alone"
    assert_all_deleted(cluster)
    deleted = [(r, n) for r, n, _ in cluster.deletions]
    assert len([r for r, _ in deleted if r == "jobs"]) == 1, "the Job, explicitly"
    assert ("services", "taktus-gateway") not in deleted, "the chart's gateway stays"


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


async def test_a_unit_no_node_has_room_for_is_at_capacity(
    cluster: FakeCluster, configuration: EnvironmentConfiguration, tmp_path: Path
) -> None:
    """The scheduler names an exhausted resource; the job waits for room, it is not broken
    (ADR-0037 §6, #358). A pod no node may take at all is still an error."""

    def unplaced(message: str) -> Callable[[dict[str, Any]], None]:
        def mark(pod: dict[str, Any]) -> None:
            pod["status"]["conditions"] = [
                {
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                    "message": message,
                }
            ]
            pod["status"]["containerStatuses"] = []

        return mark

    unit = ExecutionUnit(
        name="reference", program="worker:1", port=1, limits=LIMITS, start_timeout_seconds=1
    )
    execution = execution_for(cluster, configuration, tmp_path)
    cluster.on_pod = unplaced("0/1 nodes are available: 1 Insufficient memory.")
    with pytest.raises(ExecutionAtCapacity, match="Insufficient memory"):
        async with execution.launch(request_for(1, unit=unit, credentials=CREDENTIALS)):
            pass
    assert_all_deleted(cluster)
    cluster.on_pod = unplaced("0/1 nodes are available: 1 node(s) had untolerated taint.")
    with pytest.raises(ExecutionError) as raised:
        async with execution.launch(request_for(1, unit=unit, credentials=CREDENTIALS)):
            pass
    assert not isinstance(raised.value, ExecutionAtCapacity)


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


# --- the gateway admits what a job's token names, and nothing else -----------------------------


def token_for(*hosts: str, expires: int | None = None, key: bytes = GATEWAY_KEY) -> str:
    when = int(time.time()) + 600 if expires is None else expires
    return mint(key, job="test", hosts=hosts, expires=when)


async def test_the_gateway_answers_407_without_a_token_its_key_signed() -> None:
    """In a cluster the namespace's policy cannot tell one job from another; the token can.
    Without one, with one another key signed, or with one whose job's time is over, the gateway
    refuses before it looks at the host. With one, it admits the hosts that token names alone."""

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    target = await asyncio.start_server(upstream, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    server = await asyncio.start_server(proxy(signed(lambda: GATEWAY_KEY)), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async def connect(token: str | None) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        header = (
            "Proxy-Authorization: Basic "
            + base64.b64encode(f"taktus:{token}".encode()).decode()
            + "\r\n"
            if token is not None
            else ""
        )
        writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\n{header}\r\n".encode())
        await writer.drain()
        line = await reader.readline()
        writer.close()
        return line

    async with server, target:
        assert b"407" in await connect(None)
        assert b"407" in await connect(token_for(f"127.0.0.1:{target_port}", key=b"another"))
        assert b"407" in await connect(token_for(f"127.0.0.1:{target_port}", expires=1))
        assert b"407" in await connect("not-a-token")
        assert b"403" in await connect(token_for("api.example.org"))
        assert b"200" in await connect(token_for(f"127.0.0.1:{target_port}"))


async def test_a_client_that_sends_the_proxy_url_credentials_reaches_through_the_gateway() -> None:
    """The unit finds the gateway as `http://taktus:<token>@address:port`; a client that honours
    the variable sends the token by itself — here httpx, as the workers' Python would."""

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nreached")
        await writer.drain()
        writer.close()

    target = await asyncio.start_server(upstream, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    server = await asyncio.start_server(proxy(signed(lambda: GATEWAY_KEY)), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    mine = token_for(f"127.0.0.1:{target_port}")
    other = token_for("api.example.org")
    async with server, target:
        async with httpx.AsyncClient(proxy=f"http://taktus:{mine}@127.0.0.1:{port}") as client:
            response = await client.get(f"http://127.0.0.1:{target_port}/")
        async with httpx.AsyncClient(proxy=f"http://taktus:{other}@127.0.0.1:{port}") as client:
            refused = await client.get(f"http://127.0.0.1:{target_port}/")
    assert response.text == "reached"
    assert refused.status_code == 403, "another job's hosts are not this one's"


async def test_a_client_that_negotiates_the_scheme_reaches_through_the_gateway(
    tmp_path: Path,
) -> None:
    """git asks without credentials first and sends the token only once the 407 names a scheme
    it can answer. Without `Proxy-Authenticate` it gave up, and no coding worker in a cluster
    could clone its workspace (issue #356)."""
    requests: list[bytes] = []

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        requests.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    target = await asyncio.start_server(upstream, "127.0.0.1", 0)
    target_port = target.sockets[0].getsockname()[1]
    server = await asyncio.start_server(proxy(signed(lambda: GATEWAY_KEY)), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    token = token_for(f"127.0.0.1:{target_port}")
    environment = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "http_proxy": f"http://taktus:{token}@127.0.0.1:{port}",
    }
    async with server, target:
        git = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            f"http://127.0.0.1:{target_port}/repository.git",
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, error = await git.communicate()
    # A word, not a substring: the target's random port may contain "407" (#450).
    assert re.search(rb"\b407\b", error) is None, error
    assert requests and b"/repository.git/info/refs" in requests[0]


async def test_the_gateway_refuses_an_address_no_token_may_reach() -> None:
    """The container gateway's guard (`--refuse-job-networks`): an address on a job's network
    is refused whatever the token names, before anything is connected."""
    server = await asyncio.start_server(
        proxy(signed(lambda: GATEWAY_KEY), forbidden=lambda address: address.is_loopback),
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]
    token = token_for("127.0.0.1:9")
    async with server:
        async with httpx.AsyncClient(proxy=f"http://taktus:{token}@127.0.0.1:{port}") as client:
            refused = await client.get("http://127.0.0.1:9/")
    assert refused.status_code == 502 and "job's network" in refused.text
