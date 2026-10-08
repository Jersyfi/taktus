"""A fake of the cluster's API server, as an `httpx` transport: what the cluster adapter's unit
tests run against.

It keeps the objects the adapter creates, gives them what the real server gives — a uid, a
cluster address for a Service — and, for every Job, a pod that runs and is ready at once. It
answers exactly the paths of `api.PATHS`, and it records every call by (resource, verb), so
that a test can hold the adapter to the Role of `deploy/k8s/README.md` §1: a call outside it is
answered 403 and listed in `forbidden`. Deleting an object deletes what it owns, as the
garbage collector does.
"""

from __future__ import annotations

import base64
import itertools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from taktus.adapters.driven.execution.kubernetes.api import PERMITTED

type Json = dict[str, Any]

PATH = re.compile(
    r"^/(?:api/v1|apis/batch/v1)/namespaces/(?P<namespace>[^/]+)/(?P<resource>[a-z]+)"
    r"(?:/(?P<name>[^/]+))?(?:/(?P<sub>[a-z]+))?$"
)


@dataclass
class FakeCluster:
    namespace: str
    unit_address: str = "127.0.0.1"
    """The cluster address every unit Service gets: where the test's stand-in unit listens."""
    objects: dict[str, dict[str, Json]] = field(default_factory=dict)
    calls: list[tuple[str, str, str]] = field(default_factory=list)
    """(resource, verb, name) of every call, in order."""
    forbidden: list[tuple[str, str]] = field(default_factory=list)
    deletions: list[tuple[str, str, str | None]] = field(default_factory=list)
    """(resource, name, propagation policy) of every delete."""
    logs: dict[str, bytes] = field(default_factory=dict)
    on_pod: Callable[[Json], None] | None = None
    """Called with each pod as it is created: a test makes it fail, wait, or be killed."""
    _uids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))
    _addresses: itertools.count[int] = field(default_factory=lambda: itertools.count(10))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def of(self, resource: str) -> dict[str, Json]:
        return self.objects.setdefault(resource, {})

    def everything(self) -> list[tuple[str, str]]:
        return sorted((r, n) for r, objects in self.objects.items() for n in objects)

    # --- the server ----------------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        match = PATH.match(request.url.path)
        if match is None or match["namespace"] != self.namespace:
            self.forbidden.append((request.url.path, request.method))
            return _status(403, f"{request.url.path} is outside the execution namespace")
        resource, name, sub = match["resource"], match["name"], match["sub"]
        if sub:
            resource = f"{resource}/{sub}"
        verb = {
            ("POST", False): "create",
            ("GET", True): "get",
            ("GET", False): "list",
            ("DELETE", True): "delete",
        }.get((request.method, name is not None), request.method.lower())
        if verb == "list" and request.url.params.get("watch") == "true":
            verb = "watch"
        self.calls.append((resource, verb, name or ""))
        if (resource, verb) not in PERMITTED:
            self.forbidden.append((resource, verb))
            return _status(403, f"{verb} on {resource} is forbidden")
        if resource == "pods/log":
            assert name is not None
            return httpx.Response(200, content=self.logs.get(name, b""))
        if verb == "create":
            return self._create(resource, json.loads(request.content))
        if verb == "get":
            assert name is not None
            found = self.of(resource).get(name)
            return httpx.Response(200, json=found) if found else _status(404, "not found")
        if verb == "list":
            wanted = dict(
                pair.split("=", 1)
                for pair in request.url.params.get("labelSelector", "").split(",")
                if pair
            )
            items = [
                o
                for o in self.of(resource).values()
                if wanted.items() <= ((o.get("metadata") or {}).get("labels") or {}).items()
            ]
            return httpx.Response(200, json={"items": items})
        assert name is not None
        policy = request.url.params.get("propagationPolicy")
        if request.content:
            policy = json.loads(request.content).get("propagationPolicy", policy)
        self.deletions.append((resource, name, policy))
        if name not in self.of(resource):
            return _status(404, "not found")
        self._delete(resource, name)
        return httpx.Response(200, json={"kind": "Status", "status": "Success"})

    def _create(self, resource: str, body: Json) -> httpx.Response:
        name = body["metadata"]["name"]
        if name in self.of(resource):
            return _status(409, f"{resource} {name} already exists")
        body = json.loads(json.dumps(body))
        body["metadata"]["uid"] = f"uid-{next(self._uids)}"
        body["metadata"]["namespace"] = self.namespace
        if resource == "services":
            role = body["metadata"]["labels"].get("taktus/role")
            body["spec"]["clusterIP"] = (
                self.unit_address if role == "unit" else f"10.96.0.{next(self._addresses)}"
            )
        self.of(resource)[name] = body
        if resource == "jobs":
            self._run(body)
        return httpx.Response(201, json=body)

    def _run(self, job: Json) -> None:
        """The job controller and the kubelet in one step: a pod that runs and is ready."""
        template = job["spec"]["template"]
        name = f"{job['metadata']['name']}-pod"
        pod: Json = {
            "metadata": {
                "name": name,
                "labels": dict(template["metadata"]["labels"]),
                "ownerReferences": [
                    {"kind": "Job", "name": job["metadata"]["name"], "uid": job["metadata"]["uid"]}
                ],
            },
            "spec": template["spec"],
            "status": {
                "phase": "Running",
                "podIP": f"10.244.0.{next(self._addresses)}",
                "conditions": [
                    {"type": "PodScheduled", "status": "True"},
                    {"type": "Ready", "status": "True"},
                ],
                "containerStatuses": [
                    {"name": c["name"], "ready": True, "state": {"running": {}}}
                    for c in template["spec"]["containers"]
                ],
            },
        }
        self.of("pods")[name] = pod
        if self.on_pod is not None:
            self.on_pod(pod)

    def _delete(self, resource: str, name: str) -> None:
        """The object, and — as the garbage collector does — everything it owns."""
        gone = self.of(resource).pop(name)
        uid = gone["metadata"].get("uid")
        for other_resource, objects in list(self.objects.items()):
            for other_name, other in list(objects.items()):
                owners = (other.get("metadata") or {}).get("ownerReferences") or []
                if any(o.get("uid") == uid and o.get("name") == name for o in owners):
                    self._delete(other_resource, other_name)

    def secret_values(self) -> dict[str, str]:
        """Every value in every Secret, decoded."""
        return {
            key: base64.b64decode(value).decode()
            for secret in self.of("secrets").values()
            for key, value in (secret.get("data") or {}).items()
        }


def _status(code: int, message: str) -> httpx.Response:
    return httpx.Response(code, json={"kind": "Status", "code": code, "message": message})


def restricted_violations(pod_spec: Json) -> list[str]:
    """What in a pod's spec the Pod Security level `restricted` would refuse — the checks of
    that level that a job's spec can fail (https://kubernetes.io/docs/concepts/security/
    pod-security-standards/)."""
    found: list[str] = []
    pod = pod_spec.get("securityContext") or {}
    for key in ("hostNetwork", "hostPID", "hostIPC"):
        if pod_spec.get(key):
            found.append(f"{key} is set")
    if any("hostPath" in v for v in pod_spec.get("volumes") or []):
        found.append("a hostPath volume")
    allowed_volumes = {
        "configMap",
        "csi",
        "downwardAPI",
        "emptyDir",
        "ephemeral",
        "persistentVolumeClaim",
        "projected",
        "secret",
    }
    for volume in pod_spec.get("volumes") or []:
        kinds = set(volume) - {"name"}
        if not kinds <= allowed_volumes:
            found.append(f"volume {volume['name']} of kind {kinds - allowed_volumes}")
    for container in pod_spec.get("containers") or []:
        context = container.get("securityContext") or {}
        where = f"container {container['name']}"
        if context.get("privileged"):
            found.append(f"{where} is privileged")
        if context.get("allowPrivilegeEscalation") is not False:
            found.append(f"{where} does not forbid privilege escalation")
        if "ALL" not in ((context.get("capabilities") or {}).get("drop") or []):
            found.append(f"{where} does not drop ALL capabilities")
        added = set((context.get("capabilities") or {}).get("add") or []) - {"NET_BIND_SERVICE"}
        if added:
            found.append(f"{where} adds {added}")
        if not (context.get("runAsNonRoot") or pod.get("runAsNonRoot")):
            found.append(f"{where} may run as root")
        if context.get("runAsUser") == 0 or pod.get("runAsUser") == 0:
            found.append(f"{where} runs as user 0")
        profile = (context.get("seccompProfile") or pod.get("seccompProfile") or {}).get("type")
        if profile not in ("RuntimeDefault", "Localhost"):
            found.append(f"{where} has no seccomp profile")
        if container.get("ports") and any(p.get("hostPort") for p in container["ports"]):
            found.append(f"{where} uses a host port")
    return found
