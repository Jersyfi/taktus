"""The cluster's API, as the cluster execution adapter uses it, and nothing more.

The client is `httpx`, which the control plane already carries, over the cluster's REST
interface (M1.3): the adapter needs twelve calls on four kinds of object in one namespace, and a
general client library would bring the whole API surface for them. `PERMITTED` is the list of
those calls. It is the Role of Taktus's own service account in the execution namespace
(`deploy/k8s/README.md` §1), and the client refuses any other call before it is sent, so that
the adapter cannot drift past what the Role grants without a test noticing.

Two ways to connect. **In the cluster**, the normal way: the service account's token, which the
platform mounts and rotates, re-read for every request; the cluster's certificate authority
beside it; the API server's address from the variables the platform sets in every pod. **From
a kubeconfig**, for the tests against a real cluster: a server, its certificate authority and a
bearer token, read from a file and kept as a `Secret`. Client certificates and exec plugins are
not supported; a kubeconfig that needs them is refused with the reason.

Errors carry the API server's own message, which names objects and never a secret.
"""

from __future__ import annotations

import base64
import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx
import yaml

from taktus.ports.configuration import Secret
from taktus.ports.execution import ExecutionError

type Json = dict[str, Any]

IN_CLUSTER = Path("/var/run/secrets/kubernetes.io/serviceaccount")
"""Where the platform mounts a pod's service-account token and the cluster's authority."""

PATHS: dict[str, str] = {
    "jobs": "/apis/batch/v1/namespaces/{namespace}/jobs",
    "pods": "/api/v1/namespaces/{namespace}/pods",
    "secrets": "/api/v1/namespaces/{namespace}/secrets",
    "services": "/api/v1/namespaces/{namespace}/services",
}

PERMITTED: frozenset[tuple[str, str]] = frozenset(
    {
        ("jobs", "create"),
        ("jobs", "get"),
        ("jobs", "list"),
        ("jobs", "watch"),
        ("jobs", "delete"),
        ("pods", "get"),
        ("pods", "list"),
        ("pods/log", "get"),
        ("secrets", "create"),
        ("secrets", "delete"),
        ("services", "create"),
        ("services", "delete"),
    }
)
"""Every call the adapter may make, as (resource, verb): the Role of `deploy/k8s/README.md` §1.
No `get` or `list` on secrets: Taktus writes a job's credentials into the namespace and can never
read one back. `watch` on jobs is granted and not used yet; polling suffices."""


class ClusterError(ExecutionError):
    """The API server refused or failed a call; `status` is its HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Connection:
    """Where the API server is and how to authenticate to it."""

    server: str
    token_file: Path | None = None
    token: Secret | None = None
    ca_file: Path | None = None
    ca_data: bytes | None = None

    @classmethod
    def in_cluster(cls, directory: Path = IN_CLUSTER) -> Connection:
        """The pod's own service account. Fails with the reason outside a cluster."""
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if not host or not (directory / "token").is_file():
            raise ExecutionError(
                "not running in a cluster: KUBERNETES_SERVICE_HOST is not set or no "
                f"service-account token is mounted at {directory}"
            )
        if ":" in host:
            host = f"[{host}]"
        return cls(
            server=f"https://{host}:{port}",
            token_file=directory / "token",
            ca_file=directory / "ca.crt",
        )

    @classmethod
    def from_kubeconfig(cls, path: Path) -> Connection:
        """The current context of a kubeconfig that authenticates with a bearer token."""
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        contexts = {c["name"]: c.get("context") or {} for c in config.get("contexts") or []}
        clusters = {c["name"]: c.get("cluster") or {} for c in config.get("clusters") or []}
        users = {u["name"]: u.get("user") or {} for u in config.get("users") or []}
        context = contexts.get(config.get("current-context", ""))
        if context is None:
            raise ExecutionError(f"{path}: no current context")
        cluster = clusters.get(context.get("cluster", ""))
        user = users.get(context.get("user", ""))
        if cluster is None or user is None:
            raise ExecutionError(f"{path}: the current context names no cluster or no user")
        token = user.get("token")
        token_file = user.get("tokenFile")
        if not token and not token_file:
            raise ExecutionError(
                f"{path}: the current user has no bearer token; client certificates and exec "
                "plugins are not supported"
            )
        ca_data = cluster.get("certificate-authority-data")
        ca_file = cluster.get("certificate-authority")
        return cls(
            server=str(cluster.get("server", "")).rstrip("/"),
            token=Secret(str(token)) if token else None,
            token_file=Path(token_file) if token_file else None,
            ca_data=base64.b64decode(ca_data) if ca_data else None,
            ca_file=(path.parent / ca_file) if ca_file else None,
        )

    def bearer(self) -> str:
        if self.token is not None:
            return self.token.reveal()
        if self.token_file is not None:
            return self.token_file.read_text(encoding="utf-8").strip()
        raise ExecutionError("the connection to the cluster has no token")

    def verify(self) -> ssl.SSLContext | bool:
        if self.ca_data is None and self.ca_file is None:
            return True
        context = ssl.create_default_context(
            cafile=str(self.ca_file) if self.ca_file is not None else None,
            cadata=self.ca_data.decode() if self.ca_data is not None else None,
        )
        return context


class ClusterApi:
    """The calls of `PERMITTED`, in one namespace. `transport` replaces the network — the unit
    tests hand it a fake of the API server."""

    def __init__(
        self,
        connection: Connection,
        namespace: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.namespace = namespace
        self._connection = connection
        self._http = httpx.AsyncClient(
            base_url=connection.server,
            verify=connection.verify() if transport is None else True,
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def create(self, resource: str, body: Json) -> Json:
        response = await self._call("POST", resource, "create", self._path(resource), json=body)
        return dict(response.json())

    async def get(self, resource: str, name: str) -> Json | None:
        response = await self._call(
            "GET", resource, "get", f"{self._path(resource)}/{name}", ok=(200, 404)
        )
        return None if response.status_code == 404 else dict(response.json())

    async def list(self, resource: str, selector: dict[str, str]) -> list[Json]:
        label_selector = ",".join(f"{k}={v}" for k, v in sorted(selector.items()))
        response = await self._call(
            "GET",
            resource,
            "list",
            self._path(resource),
            params={"labelSelector": label_selector},
        )
        return list(response.json().get("items") or [])

    async def delete(self, resource: str, name: str) -> bool:
        """Delete an object and everything it owns, in the background; False when it was
        already gone. The propagation is named: the API's default for a job orphans its pods."""
        response = await self._call(
            "DELETE",
            resource,
            "delete",
            f"{self._path(resource)}/{name}",
            json={"propagationPolicy": "Background"},
            params={"propagationPolicy": "Background"},
            ok=(200, 202, 404),
        )
        return response.status_code != 404

    async def log(self, pod: str, container: str) -> bytes:
        response = await self._call(
            "GET",
            "pods/log",
            "get",
            f"{self._path('pods')}/{pod}/log",
            params={"container": container},
            ok=(200, 400, 404),
        )
        return response.content if response.status_code == 200 else b""

    def _path(self, resource: str) -> str:
        return PATHS[resource].format(namespace=self.namespace)

    async def _call(
        self,
        method: str,
        resource: str,
        verb: str,
        path: str,
        *,
        ok: tuple[int, ...] = (200, 201, 202),
        json: Json | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        if (resource, verb) not in PERMITTED:
            raise ClusterError(
                403,
                f"{verb} on {resource} is not in the Role of Taktus's service account "
                "(deploy/k8s/README.md §1); the adapter does not send it",
            )
        try:
            response = await self._http.request(
                method,
                path,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self._connection.bearer()}"},
            )
        except httpx.HTTPError as error:
            raise ClusterError(0, f"the cluster's API is not reachable: {error}") from None
        if response.status_code not in ok:
            try:
                message = response.json().get("message") or response.text
            except ValueError:
                message = response.text
            raise ClusterError(
                response.status_code,
                f"{verb} {resource} refused by the cluster ({response.status_code}): {message}",
            )
        return response
