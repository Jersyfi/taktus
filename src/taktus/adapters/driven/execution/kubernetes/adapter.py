"""The `cluster` adapter: one execution unit per job, as a Job in the execution namespace.

The third implementation of the execution port (ADR-0002), specified in
`deploy/k8s/README.md` §4 to §7. Every job gets:

- **a Job of its own** from the unit's image: `backoffLimit: 0`, because the run retries a step
  and the cluster does not retry a job behind its back; a deadline (`activeDeadlineSeconds`,
  the wall clock plus the start timeout, as the cluster's own backstop) and a time to live
  after it finished (`ttlSecondsAfterFinished`); a memory request equal to the memory limit,
  and a CPU request of a share of the CPU limit (`cpu_request_share`, README §7), because CPU is
  compressible and memory is not; and a pod that satisfies the Pod Security level
  `restricted` — not root, no privilege escalation, every capability dropped, the runtime's
  default seccomp profile, a read-only root filesystem with writable empty directories for
  `/tmp` and the workspace;
- **no service-account token**: `automountServiceAccountToken: false` on the pod, so a unit
  holds no credential for the API server that runs it;
- **credentials from a Secret created for the job**: a variable from a key of the Secret for
  `env`, a file mounted from a key at its exact path for `file`. The pod's recorded
  configuration names the Secret and its keys and never a value;
- **the variables its configuration names** (`ExecutionUnit.environment`, ADR-0090) as plain
  values in the pod's environment, beside the launch convention's: configuration, never a
  secret;
- **a Service** that selects the unit's pod; the control plane reaches the worker contract at
  its address;
- **the instance's egress gateway** when the job names hosts (ADR-0115): one Deployment of
  the chart in the execution namespace, behind the Service `gateway_service`, running the
  container adapter's `egress.py`. The job's Secret holds a token that names the job's hosts —
  for an assignment, the frame's and the worker's service hosts (ADR-0089) — signed with the
  gateway's key (`execution.gateway.key`) and valid until the job's deadline. The unit finds
  the gateway in `HTTP(S)_PROXY`, by address, since a unit resolves no names, with the token as
  the password. The gateway admits the hosts the token names and nothing else, so that the
  namespace's network policy, which cannot tell one job from another, need not. Without hosts
  there is no token and nothing to reach;
- **one owner**: the Secret and the Service are owned by the unit's Job, so that the cluster's
  garbage collector removes them with it. The adapter deletes everything itself when the job
  ends, whatever the outcome; ownership is what still removes it when the control plane died
  first — the deadline ends the Job, the time to live deletes it, and its objects go too.

It refuses before creating anything, with the port's `ExecutionRefused`: a job it cannot give
limits to; a job that names hosts where no gateway key is configured, or no gateway Service
exists; a job that names hosts on a cluster whose network policies are not enforced
(`enforce_egress=False`), because a host list nothing enforces is a line in a bundle; and, on
such a cluster, every job whose autonomy level needs isolation (ADR-0002) — without an enforced
policy the pod's network is open, and the cluster isolates the process and the filesystem only.

The only calls it makes are those of `api.PERMITTED`, the Role of Taktus's service account.
"""

from __future__ import annotations

import asyncio
import base64
import re
import secrets
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import structlog

from taktus.adapters.driven.execution._common import (
    GATEWAY_KEY,
    PROXY_VARIABLES,
    ResolvedCredential,
    gateway_key,
    job_token,
    proxy_url,
    resolve_credentials,
    wait_until_healthy,
)
from taktus.adapters.driven.execution.kubernetes.api import (
    ClusterApi,
    ClusterError,
    Connection,
    Json,
)
from taktus.ports.configuration import Configuration
from taktus.ports.execution import (
    ISOLATION_REQUIRED_FROM,
    UNIT_PORT_VARIABLE,
    UNIT_STATE_DIR_VARIABLE,
    UNIT_WALL_SECONDS_VARIABLE,
    ExecutionAtCapacity,
    ExecutionError,
    ExecutionRefused,
    Isolation,
    JobExit,
    JobRequest,
    refusal,
    unit_environment,
)

PROXY_URL_KEY = "taktus-egress-url"
GATEWAY_SERVICE = "taktus-gateway"
"""The gateway's Service in the execution namespace, as the chart names it by default."""
UNIT_CONTAINER = "unit"
WORKSPACE = "/workspace"
MIN_MEMORY_BYTES = 6 * 1024 * 1024
"""Below this a container runtime refuses a memory limit; a smaller one cannot be given."""
LABEL_JOB = "taktus/job"
LABEL_ROLE = "taktus/role"
MANAGED_BY = {"app.kubernetes.io/managed-by": "taktus"}
NOBODY = 65534

log = structlog.get_logger("taktus.execution.cluster")


def cpu_resources(cpus: float, share: float) -> tuple[str, str]:
    """The CPU a unit requests and the CPU it is limited to, in millicores: the request is
    `share` of the limit, never below one millicore. A share of 1 requests the whole limit."""
    limit = int(cpus * 1000)
    return f"{max(1, int(limit * share))}m", f"{limit}m"


def limits_refusal(request: JobRequest) -> str | None:
    """Why the job cannot be given its limits, or None when it can. Every job carries a CPU
    and a memory limit and a deadline; the node has no swap, and one job without a limit is
    how a runaway assignment takes the node down (`deploy/k8s/README.md` §4)."""
    limits = request.unit.limits
    missing = [
        name
        for name in ("cpus", "memory_bytes", "wall_seconds")
        if limits is None or not getattr(limits, name, None) or getattr(limits, name) <= 0
    ]
    if missing:
        return f"the job has no limit for {', '.join(missing)}, and a job without one is refused"
    if int(limits.cpus * 1000) < 1:
        return f"a CPU limit of {limits.cpus} is below one thousandth of a core"
    if limits.memory_bytes < MIN_MEMORY_BYTES:
        return f"a memory limit of {limits.memory_bytes} bytes is below what a runtime enforces"
    return None


def egress_refusal(request: JobRequest, *, enforce_egress: bool) -> str | None:
    """Why the job may not run on a cluster whose network policies are not enforced, or None."""
    if enforce_egress:
        return None
    if request.allowed_hosts:
        return (
            "the job names allowed hosts — the frame's or the worker's service hosts — and this "
            "cluster does not enforce network policies "
            "(enforce_egress is off): without them the job could bypass its egress proxy, and a "
            "host list nothing enforces is refused rather than started "
            "(deploy/k8s/README.md §6)"
        )
    level = request.autonomy_level
    if level is None or level >= ISOLATION_REQUIRED_FROM:
        shown = "unknown" if level is None else str(level)
        return (
            f"autonomy level {shown} needs an isolated execution unit, and a pod on a cluster "
            "that does not enforce network policies has an open network: the cluster isolates "
            "its process and its filesystem, not its reach (ADR-0002)"
        )
    return None


@dataclass(frozen=True)
class _Names:
    tag: str

    @classmethod
    def of(cls, job_id: str, suffix: str) -> _Names:
        base = re.sub(r"[^a-z0-9-]+", "-", job_id.lower()).strip("-")[:32].strip("-") or "job"
        return cls(f"{base}-{suffix}")

    @property
    def unit(self) -> str:
        return f"taktus-unit-{self.tag}"

    @property
    def secret(self) -> str:
        return f"taktus-job-{self.tag}"

    def labels(self, role: str) -> dict[str, str]:
        return {**MANAGED_BY, LABEL_JOB: self.tag, LABEL_ROLE: role}


@dataclass
class ClusterJob:
    id: str
    endpoint: str
    name: str
    """The unit Job's name; its Service has the same."""
    api: ClusterApi = field(repr=False)
    selector: dict[str, str] = field(default_factory=dict)
    killed: JobExit | None = None

    async def exit(self) -> JobExit | None:
        if self.killed is not None:
            return self.killed
        job = await self.api.get("jobs", self.name)
        if job is None:
            return JobExit(reason="the job no longer exists in the cluster")
        for pod in await self.api.list("pods", self.selector):
            for status in (pod.get("status") or {}).get("containerStatuses") or []:
                if status.get("name") != UNIT_CONTAINER:
                    continue
                terminated = (status.get("state") or {}).get("terminated")
                if terminated is None:
                    continue
                code = int(terminated.get("exitCode") or 0)
                if terminated.get("reason") == "OOMKilled":
                    return JobExit(
                        code=code or 137,
                        killed="memory",
                        reason="the memory limit was exceeded and the cluster killed the unit",
                    )
                return JobExit(code=code, reason=f"the unit exited with {code}")
        for condition in (job.get("status") or {}).get("conditions") or []:
            if condition.get("type") == "Failed" and condition.get("status") == "True":
                if condition.get("reason") == "DeadlineExceeded":
                    deadline = (job.get("spec") or {}).get("activeDeadlineSeconds")
                    return JobExit(
                        code=137,
                        killed="wall",
                        reason=f"the job's deadline of {deadline}s was exceeded",
                    )
                return JobExit(
                    reason=f"the job failed: {condition.get('reason') or 'no reason given'}"
                )
        return None

    async def waiting(self) -> str | None:
        """Why the unit's container has not started, as the cluster says it, or None."""
        for pod in await self.api.list("pods", self.selector):
            for status in (pod.get("status") or {}).get("containerStatuses") or []:
                waiting = (status.get("state") or {}).get("waiting")
                if waiting:
                    return f"{waiting.get('reason')}: {waiting.get('message') or ''}".strip(": ")
            for condition in (pod.get("status") or {}).get("conditions") or []:
                if condition.get("type") == "PodScheduled" and condition.get("status") != "True":
                    return f"not scheduled: {condition.get('message') or condition.get('reason')}"
        return None


def no_room(why: str) -> bool:
    """Whether the cluster's reason a pod waits is that no node has room for it: the scheduler
    names an exhausted resource as `Insufficient <resource>`. A pod that no node may take at
    all — a taint, a selector — is not waiting for room, and fails as before."""
    return why.startswith("not scheduled:") and "Insufficient" in why


class KubernetesExecution:
    isolation = Isolation.CLUSTER

    def __init__(
        self,
        configuration: Configuration,
        *,
        namespace: str,
        state_dir: Path,
        connection: Connection | None = None,
        gateway_service: str = GATEWAY_SERVICE,
        enforce_egress: bool = True,
        service_account: str | None = None,
        state_claim: str | None = None,
        run_as_user: int = NOBODY,
        ttl_seconds: int = 600,
        cpu_request_share: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`namespace` is the execution namespace. `connection` defaults to the pod's own
        service account. `enforce_egress` is the operator's statement that the cluster enforces
        network policies (`execution.egress.enforce`). `gateway_service` is the Service of
        the instance's egress gateway in the namespace (`execution.gateway.service`).
        `state_claim` names an existing volume
        claim for the unit's state, which outlives jobs; without one the state directory is an
        empty directory that dies with the job, and the startup log says so.
        `cpu_request_share` is the share of its CPU limit a unit requests from the cluster's
        scheduler (`execution.cpu.request.share`, more than 0 and at most 1); its memory request
        is always its memory limit. `transport` replaces the network to the API server, for the
        tests."""
        if not 0 < cpu_request_share <= 1:
            raise ValueError(f"a CPU request share of {cpu_request_share} is not in (0, 1]")
        self._configuration = configuration
        self._namespace = namespace
        self._state_dir = state_dir
        self._connection = connection
        self._gateway_service = gateway_service
        self._enforce_egress = enforce_egress
        self._service_account = service_account
        self._state_claim = state_claim
        self._run_as_user = run_as_user
        self._ttl_seconds = ttl_seconds
        self._cpu_request_share = cpu_request_share
        self._transport = transport
        if state_claim is None:
            log.warning(
                "no volume claim for the unit's state: it lives in an empty directory and dies "
                "with each job, so an assignment cannot resume from a checkpoint",
                namespace=namespace,
            )

    async def close(self) -> None:
        """Nothing is held beyond a job: the gateway is the chart's."""

    def _api(self) -> ClusterApi:
        connection = self._connection or Connection.in_cluster()
        return ClusterApi(connection, self._namespace, transport=self._transport)

    @asynccontextmanager
    async def launch(self, request: JobRequest) -> AsyncIterator[ClusterJob]:
        for why in (
            refusal(self.isolation, request.autonomy_level),
            limits_refusal(request),
            egress_refusal(request, enforce_egress=self._enforce_egress),
        ):
            if why is not None:
                raise ExecutionRefused(why)
        unit_environment(request)
        credentials = resolve_credentials(self._configuration, request.credentials)
        key = self._gateway_key(request)
        names = _Names.of(request.job_id, secrets.token_hex(3))
        api = self._api()
        job: ClusterJob | None = None
        timer: asyncio.Task[None] | None = None
        created: list[tuple[str, str]] = []
        try:
            gateway = await self._gateway(api) if key is not None else None
            job = await self._start(api, request, names, credentials, created, key, gateway)
            wall = min(
                request.wall_seconds or request.unit.limits.wall_seconds,
                request.unit.limits.wall_seconds,
            )
            timer = asyncio.create_task(self._kill_after(job, wall), name=f"wall-{job.id}")

            async def ended() -> str | None:
                exit = await job.exit() if job is not None else None
                return None if exit is None else exit.reason

            try:
                await wait_until_healthy(
                    job.endpoint, within_seconds=request.unit.start_timeout_seconds, ended=ended
                )
            except ExecutionError as error:
                why = await job.waiting()
                said = f"{error}; the cluster says: {why}" if why else str(error)
                if why is not None and no_room(why):
                    raise ExecutionAtCapacity(said) from None
                raise ExecutionError(said) from None
            yield job
        finally:
            if timer is not None:
                timer.cancel()
            await self._remove(api, names, request, job, created)
            await api.close()

    # --- start --------------------------------------------------------------------------------

    def _gateway_key(self, request: JobRequest) -> bytes | None:
        """The gateway's key for a job that names hosts, None for one that names none; a job
        that names hosts where no key is configured is refused."""
        if not request.allowed_hosts:
            return None
        key = gateway_key(self._configuration)
        if key is None:
            raise ExecutionRefused(
                "the job names allowed hosts, and no egress gateway key is configured: set "
                f"{self._configuration.name(GATEWAY_KEY)}_FILE to the file of the key the "
                "gateway verifies each job's token with (deploy/k8s/README.md §6)"
            )
        return key.reveal().strip().encode()

    async def _gateway(self, api: ClusterApi) -> tuple[str, int]:
        """The address and port of the instance's gateway, from its Service."""
        service = await api.get("services", self._gateway_service)
        if service is None:
            raise ExecutionRefused(
                f"the egress gateway's Service {self._gateway_service} does not exist in the "
                f"namespace {self._namespace}: a job that names hosts has nothing to reach them "
                "through (deploy/k8s/README.md §6)"
            )
        ports = (service.get("spec") or {}).get("ports") or []
        if not ports:
            raise ExecutionError(
                f"the egress gateway's Service {self._gateway_service} has no port"
            )
        return _cluster_ip(service), int(ports[0]["port"])

    async def _start(
        self,
        api: ClusterApi,
        request: JobRequest,
        names: _Names,
        credentials: tuple[ResolvedCredential, ...],
        created: list[tuple[str, str]],
        key: bytes | None,
        gateway: tuple[str, int] | None,
    ) -> ClusterJob:
        hosts = key is not None and gateway is not None
        unit_job = await api.create("jobs", self._unit_job(request, names, credentials, hosts))
        created.append(("jobs", names.unit))
        owner = _owner(unit_job)
        unit_service = await api.create(
            "services",
            _service(names.unit, names, "unit", request.unit.port, owner),
        )
        created.append(("services", names.unit))
        data: dict[str, str] = {}
        if key is not None and gateway is not None:
            unit = request.unit
            token = job_token(
                key,
                job=names.tag,
                hosts=request.allowed_hosts,
                seconds=request.wall + unit.start_timeout_seconds,
            )
            data[PROXY_URL_KEY] = proxy_url(token, *gateway)
        for credential in credentials:
            data[credential.reference.name] = credential.value.reveal()
        if data:
            await api.create("secrets", _secret(names, data, owner))
            created.append(("secrets", names.secret))
        endpoint = f"http://{_cluster_ip(unit_service)}:{request.unit.port}"
        log.info(
            "job started",
            job=request.job_id,
            unit=names.unit,
            namespace=self._namespace,
            gateway=self._gateway_service if hosts else None,
            allowed_hosts=list(request.allowed_hosts),
            credentials=[c.reference.name for c in credentials],
        )
        return ClusterJob(
            id=request.job_id,
            endpoint=endpoint,
            name=names.unit,
            api=api,
            selector={LABEL_JOB: names.tag, LABEL_ROLE: "unit"},
        )

    def _pod_security(self) -> Json:
        return {
            "runAsNonRoot": True,
            "runAsUser": self._run_as_user,
            "runAsGroup": self._run_as_user,
            "fsGroup": self._run_as_user,
            "seccompProfile": {"type": "RuntimeDefault"},
        }

    @staticmethod
    def _container_security() -> Json:
        return {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        }

    def _pod(self, containers: list[Json], volumes: list[Json]) -> Json:
        spec: Json = {
            "restartPolicy": "Never",
            "automountServiceAccountToken": False,
            "enableServiceLinks": False,
            "securityContext": self._pod_security(),
            "containers": containers,
            "volumes": volumes,
        }
        if self._service_account:
            spec["serviceAccountName"] = self._service_account
        return spec

    def _job(
        self, name: str, names: _Names, role: str, deadline: int, pod: Json, owner: Json | None
    ) -> Json:
        metadata: Json = {"name": name, "labels": names.labels(role)}
        if owner is not None:
            metadata["ownerReferences"] = [owner]
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": metadata,
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": deadline,
                "ttlSecondsAfterFinished": self._ttl_seconds,
                "template": {"metadata": {"labels": names.labels(role)}, "spec": pod},
            },
        }

    def _unit_job(
        self,
        request: JobRequest,
        names: _Names,
        credentials: tuple[ResolvedCredential, ...],
        hosts: bool,
    ) -> Json:
        unit = request.unit
        # The variables the unit's configuration names, as plain values (ADR-0090): they are
        # configuration and never a secret, which comes from the job's Secret below.
        environment: list[Json] = [
            *({"name": name, "value": value} for name, value in unit.environment),
            {"name": UNIT_PORT_VARIABLE, "value": str(unit.port)},
            {"name": UNIT_STATE_DIR_VARIABLE, "value": unit.state_dir},
            {"name": UNIT_WALL_SECONDS_VARIABLE, "value": str(request.wall)},
            {"name": "HOME", "value": WORKSPACE},
            {"name": "TMPDIR", "value": "/tmp"},  # noqa: S108 — an empty directory of the job
        ]
        if hosts:
            for variable in PROXY_VARIABLES:
                environment.append(_from_secret(variable, names.secret, PROXY_URL_KEY))
        mounts: list[Json] = [
            {"name": "tmp", "mountPath": "/tmp"},  # noqa: S108
            {"name": "workspace", "mountPath": WORKSPACE},
            {"name": "state", "mountPath": unit.state_dir},
        ]
        files: list[Json] = []
        for credential in credentials:
            reference = credential.reference
            if reference.injected_as == "env":
                environment.append(_from_secret(reference.name, names.secret, reference.name))
                continue
            path = reference.path or f"/run/taktus/credentials/files/{reference.name}"
            files.append({"key": reference.name, "path": reference.name, "mode": 0o440})
            mounts.append(
                {
                    "name": "credentials",
                    "mountPath": path,
                    "subPath": reference.name,
                    "readOnly": True,
                }
            )
        state: Json = (
            {"name": "state", "persistentVolumeClaim": {"claimName": self._state_claim}}
            if self._state_claim
            else {"name": "state", "emptyDir": {}}
        )
        volumes: list[Json] = [
            {"name": "tmp", "emptyDir": {}},
            {"name": "workspace", "emptyDir": {}},
            state,
        ]
        if files:
            volumes.append(
                {"name": "credentials", "secret": {"secretName": names.secret, "items": files}}
            )
        cpu_request, cpu_limit = cpu_resources(unit.limits.cpus, self._cpu_request_share)
        memory = str(unit.limits.memory_bytes)
        unit_container: Json = {
            "name": UNIT_CONTAINER,
            "image": unit.program,
            "env": environment,
            "ports": [{"name": "contract", "containerPort": unit.port, "protocol": "TCP"}],
            "resources": {
                "requests": {"cpu": cpu_request, "memory": memory},
                "limits": {"cpu": cpu_limit, "memory": memory},
            },
            "securityContext": self._container_security(),
            "volumeMounts": mounts,
        }
        deadline = unit.limits.wall_seconds + unit.start_timeout_seconds
        return self._job(
            names.unit, names, "unit", deadline, self._pod([unit_container], volumes), None
        )

    # --- end ----------------------------------------------------------------------------------

    @staticmethod
    async def _kill_after(job: ClusterJob, wall: int) -> None:
        await asyncio.sleep(wall)
        if await job.exit() is None:
            job.killed = JobExit(
                code=137, killed="wall", reason=f"the wall-clock limit of {wall}s was exceeded"
            )
            await job.api.delete("jobs", job.name)

    async def _remove(
        self,
        api: ClusterApi,
        names: _Names,
        request: JobRequest,
        job: ClusterJob | None,
        created: list[tuple[str, str]],
    ) -> None:
        """Every object the job created, newest first, after the unit's log was kept on this
        side, so that a job that failed can be read about. A failure to delete is logged and
        does not hide the job's own outcome; ownership removes what is left."""
        if job is not None and job.killed is None:
            try:
                if await job.exit() is None:
                    job.killed = JobExit(killed="stop", reason="the job is over")
            except ClusterError as error:
                log.warning("job state not read", job=names.unit, error=str(error))
        if created:
            await self._keep_log(api, names, request)
        for resource, name in reversed(created):
            try:
                await api.delete(resource, name)
            except ClusterError as error:
                log.warning("object not deleted", kind=resource, name=name, error=str(error))

    async def _keep_log(self, api: ClusterApi, names: _Names, request: JobRequest) -> None:
        try:
            pods = await api.list("pods", {LABEL_JOB: names.tag, LABEL_ROLE: "unit"})
            content = b"".join(
                [await api.log(pod["metadata"]["name"], UNIT_CONTAINER) for pod in pods]
            )
        except ClusterError as error:
            log.warning("unit log not read", job=names.unit, error=str(error))
            return
        directory = self._state_dir / "units" / request.unit.name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"job-{request.job_id}.log").write_bytes(content)


def _owner(job: Json) -> Json:
    metadata = job.get("metadata") or {}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "name": metadata.get("name"),
        "uid": metadata.get("uid"),
    }


def _cluster_ip(service: Json) -> str:
    address = (service.get("spec") or {}).get("clusterIP")
    if not address or address == "None":
        raise ExecutionError(
            f"the service {(service.get('metadata') or {}).get('name')} has no cluster address"
        )
    return f"[{address}]" if ":" in str(address) else str(address)


def _service(name: str, names: _Names, role: str, port: int, owner: Json) -> Json:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "labels": names.labels(role), "ownerReferences": [owner]},
        "spec": {
            "type": "ClusterIP",
            "selector": {LABEL_JOB: names.tag, LABEL_ROLE: role},
            "ports": [{"port": port, "targetPort": port, "protocol": "TCP"}],
        },
    }


def _secret(names: _Names, data: Mapping[str, str], owner: Json) -> Json:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "immutable": True,
        "metadata": {
            "name": names.secret,
            "labels": names.labels("credentials"),
            "ownerReferences": [owner],
        },
        "data": {key: base64.b64encode(value.encode()).decode() for key, value in data.items()},
    }


def _from_secret(variable: str, secret: str, key: str) -> Json:
    return {"name": variable, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}}
