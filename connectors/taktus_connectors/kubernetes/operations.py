"""How the cluster's API is asked, and its answers read (ADR-0195).

Every request goes to `--target` under `/apis/apps/v1/namespaces/<namespace>/`, with the
requesting identity's bearer token: a service account's token with the rights its role grants,
never one of the connector's own.

**The mark.** A release and a rollback put the idempotency key on the deployment's pod template
as the annotation `taktus.eu/idempotency-key`. The cluster keeps every pod template it rolled
out as a replica set, one per revision, up to the deployment's revision history limit. Before
acting, the connector reads the deployment and its replica sets: a template that carries the
key, current or kept, is the original, and nothing is written again. A connector stopped between
the write and its answer writes nothing twice. Scaling has no template to carry a key: the
number of replicas is its own mark.

**A stale write is refused by the cluster.** A release carries the `resourceVersion` it read;
the cluster refuses a write over a deployment changed in between with 409, `conflict`.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: a request the API refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token's role may not do this | `forbidden` |
| 404: no such deployment in the namespace | `not_found` |
| 409: the deployment changed since it was read | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

KEY_ANNOTATION = "taktus.eu/idempotency-key"
REVISION = "deployment.kubernetes.io/revision"
NAME = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")
MAX_REPLICAS = 1000


@dataclass(frozen=True)
class Config:
    target: str
    """The API server's address."""
    namespace: str = "default"
    timeout: float = 30.0
    ca_file: str | None = None
    """The cluster's certificate authority; None trusts the system's."""


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    body: Any = None,
    content_type: str | None = None,
    params: Json | None = None,
) -> Any:
    writing = method != "GET"
    call.count()
    headers = {"Authorization": f"Bearer {call.token}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            verify=config.ca_file or True,
        ) as client:
            response = await client.request(
                method,
                f"/apis/apps/v1/namespaces/{config.namespace}/{path}",
                headers=headers,
                params=params,
                content=None if body is None else _json(body),
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the cluster could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the cluster did not answer the write in time"
            ) from error
        raise unavailable(f"the cluster did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the cluster could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            return response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the cluster answered the write unreadably"
                ) from error
            raise _unexpected("the cluster answered with a body that is not JSON") from error
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the cluster does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token's role may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such deployment in the namespace")
    if status == 409:
        raise TargetError("conflict", "none", False, "the deployment changed since it was read")
    if status in (400, 422):
        raise invalid(f"the cluster refused the request: {status}")
    if status == 429 or status >= 500:
        raise unavailable(f"the cluster answered {status}")
    raise _unexpected(f"the cluster answered {status}, which the connector does not foresee")


def _json(body: Any) -> bytes:
    return json.dumps(body).encode("utf-8")


def _name(input: Json, field: str = "name") -> str:
    value = input.get(field)
    if not isinstance(value, str) or NAME.match(value) is None:
        raise invalid(f"{field} must be the name of a resource: lower case, digits and dashes")
    return value


def _annotations(template: Json) -> Json:
    found = (template.get("metadata") or {}).get("annotations") or {}
    return found if isinstance(found, dict) else {}


def _revision(resource: Json) -> int | None:
    value = ((resource.get("metadata") or {}).get("annotations") or {}).get(REVISION)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _progressed(status: Json) -> str | None:
    """When the deployment's rollout last progressed: the `lastUpdateTime` of its `Progressing`
    condition, which the controller sets as the newest replica set comes up — once complete,
    the moment the last release finished rolling out (ADR-0201). None where it states none."""
    for condition in status.get("conditions") or []:
        if isinstance(condition, dict) and condition.get("type") == "Progressing":
            moment = condition.get("lastUpdateTime")
            return str(moment) if isinstance(moment, str) and moment else None
    return None


def deployment_output(made: Json) -> Json:
    """What a reading yields of a deployment, and whether its rollout is complete: the condition
    `kubectl rollout status` waits for."""
    if not isinstance(made, dict) or "spec" not in made:
        raise _unexpected(
            "the cluster answered a deployment in a shape the connector does not know"
        )
    spec, status, metadata = made["spec"], made.get("status") or {}, made.get("metadata") or {}
    template = spec.get("template") or {}
    wanted = int(spec.get("replicas", 1))
    updated = int(status.get("updatedReplicas", 0))
    available = int(status.get("availableReplicas", 0))
    observed = int(status.get("observedGeneration", 0)) >= int(metadata.get("generation", 0))
    return {
        "name": str(metadata.get("name", "")),
        "namespace": str(metadata.get("namespace", "")),
        "containers": [
            {"name": str(c.get("name", "")), "image": str(c.get("image", ""))}
            for c in (template.get("spec") or {}).get("containers", [])
        ],
        "replicas": wanted,
        "updated": updated,
        "ready": int(status.get("readyReplicas", 0)),
        "available": available,
        "revision": _revision(made),
        "key": _annotations(template).get(KEY_ANNOTATION),
        "changed_at": _progressed(status),
        "rolled_out": observed
        and updated >= wanted
        and available >= wanted
        and int(status.get("unavailableReplicas", 0)) == 0,
    }


async def _deployment(config: Config, call: Call, name: str) -> Json:
    made = await _request(config, call, "GET", f"deployments/{name}")
    deployment_output(made)  # refuses a shape it does not know
    return dict(made)


async def _revisions(config: Config, call: Call, made: Json) -> list[Json]:
    """The replica sets the deployment owns: the revisions the cluster keeps of it."""
    labels = (made["spec"].get("selector") or {}).get("matchLabels") or {}
    selector = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    listed = await _request(
        config, call, "GET", "replicasets", params={"labelSelector": selector} if selector else None
    )
    items = listed.get("items") if isinstance(listed, dict) else None
    if not isinstance(items, list):
        raise _unexpected("the cluster's list of replica sets is not a list")
    uid = (made.get("metadata") or {}).get("uid")
    return [
        rs
        for rs in items
        if isinstance(rs, dict)
        and any(o.get("uid") == uid for o in (rs.get("metadata") or {}).get("ownerReferences", []))
    ]


async def _found(config: Config, call: Call, made: Json, key: str) -> bool:
    """Whether the key is on the deployment's template or on one the cluster keeps."""
    if _annotations(made["spec"].get("template") or {}).get(KEY_ANNOTATION) == key:
        return True
    revisions = await _revisions(config, call, made)
    return any(
        _annotations((rs.get("spec") or {}).get("template") or {}).get(KEY_ANNOTATION) == key
        for rs in revisions
    )


def _records(made: Json, kind: str, key: str | None = None) -> list[Json]:
    """The record a write names: the deployment, and for a revision the template the key marks,
    by the key's digest, so that a repeat names what the first call wrote."""
    metadata = made.get("metadata") or {}
    identifier = f"{metadata.get('namespace', '')}/{metadata.get('name', '')}"
    if key is not None:
        identifier += "@" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return [{"kind": kind, "id": identifier}]


def _write(
    output: Json,
    made: Json,
    *,
    replayed: bool,
    kind: str = "deployment.revision",
    key: str | None = None,
) -> Outcome:
    records = _records(made, kind, key)
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def read_deployment(config: Config, call: Call, input: Json) -> Outcome:
    made = await _deployment(config, call, _name(input))
    return Outcome(deployment_output(made), {"kind": "read"})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    container = _name(input, "container")
    image = input.get("image")
    if not isinstance(image, str) or IMAGE.match(image) is None:
        raise invalid("image must be an image reference: registry, name and tag or digest")
    made = await _deployment(config, call, name)
    if await _found(config, call, made, call.key):
        return _write(deployment_output(made), made, replayed=True, key=call.key)
    names = [c.get("name") for c in made["spec"]["template"].get("spec", {}).get("containers", [])]
    if container not in names:
        raise invalid(f"the deployment {name!r} has no container {container!r}")
    patch = {
        "metadata": {"resourceVersion": made["metadata"].get("resourceVersion")},
        "spec": {
            "template": {
                "metadata": {"annotations": {KEY_ANNOTATION: call.key}},
                "spec": {"containers": [{"name": container, "image": image}]},
            }
        },
    }
    written = await _request(
        config,
        call,
        "PATCH",
        f"deployments/{name}",
        body=patch,
        content_type="application/strategic-merge-patch+json",
    )
    return _write(deployment_output(written), written, replayed=False, key=call.key)


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    wanted = input.get("revision")
    if wanted is not None and (isinstance(wanted, bool) or not isinstance(wanted, int)):
        raise invalid("revision must be a revision's number")
    made = await _deployment(config, call, name)
    revisions = await _revisions(config, call, made)
    keyed = _annotations(made["spec"].get("template") or {}).get(KEY_ANNOTATION) == call.key
    if keyed or any(
        _annotations((rs.get("spec") or {}).get("template") or {}).get(KEY_ANNOTATION) == call.key
        for rs in revisions
    ):
        return _write(
            {**deployment_output(made), "to_revision": None}, made, replayed=True, key=call.key
        )
    current = _revision(made) or 0
    numbered = sorted(
        ((n, rs) for rs in revisions if (n := _revision(rs)) is not None), key=lambda p: p[0]
    )
    if wanted is not None:
        target = next((rs for n, rs in numbered if n == wanted and n != current), None)
    else:
        target = next((rs for n, rs in reversed(numbered) if n < current), None)
    if target is None:
        raise TargetError(
            "not_found", "none", False, f"the deployment {name!r} keeps no such earlier revision"
        )
    template = copy.deepcopy((target.get("spec") or {}).get("template") or {})
    metadata = template.setdefault("metadata", {})
    (metadata.get("labels") or {}).pop("pod-template-hash", None)
    metadata.setdefault("annotations", {})[KEY_ANNOTATION] = call.key
    written = await _request(
        config,
        call,
        "PATCH",
        f"deployments/{name}",
        body=[{"op": "replace", "path": "/spec/template", "value": template}],
        content_type="application/json-patch+json",
    )
    output = {**deployment_output(written), "to_revision": _revision(target)}
    return _write(output, written, replayed=False, key=call.key)


async def scale(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    replicas = input.get("replicas")
    if isinstance(replicas, bool) or not isinstance(replicas, int):
        raise invalid("replicas must be a number")
    if not 0 <= replicas <= MAX_REPLICAS:
        raise invalid(f"replicas is a number from 0 to {MAX_REPLICAS}")
    current = await _request(config, call, "GET", f"deployments/{name}/scale")
    before = int(((current or {}).get("spec") or {}).get("replicas", 0))
    record = {"metadata": {"name": name, "namespace": config.namespace}}
    if before == replicas:
        return _write(
            {"name": name, "replicas": replicas, "previous": before},
            record,
            replayed=True,
            kind="deployment.scale",
        )
    await _request(
        config,
        call,
        "PATCH",
        f"deployments/{name}/scale",
        body={"spec": {"replicas": replicas}},
        content_type="application/merge-patch+json",
    )
    return _write(
        {"name": name, "replicas": replicas, "previous": before},
        record,
        replayed=False,
        kind="deployment.scale",
    )


OPERATIONS = {
    "deployment.workloads.read": read_deployment,
    "deployment.workloads.release": release,
    "deployment.workloads.rollback": rollback,
    "deployment.workloads.scale": scale,
}
