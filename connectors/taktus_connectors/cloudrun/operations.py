"""How the Cloud Run Admin API v2 is asked, and its answers read (`deployment.workloads`).

Every request goes to `--target` under `/v2/projects/<project>/locations/<location>/services/`,
with an access token the requesting identity's service account key is exchanged for
(`auth.py`); the connector has no key of its own.

**A release is a new revision.** A service's `template` is what each new revision is made from.
Setting one container's image in it makes the service create a revision, and the traffic is set
to the latest revision, 100 percent, so that the release is what serves. The template carries
the idempotency key as the annotation `taktus.eu/idempotency-key`. The service keeps its
revisions, each with the annotations of the template it was made from. Before writing, the
connector reads the service and lists its revisions: a template that carries the key, current or
kept, is the original, and nothing is written again.

**A rollback moves the traffic.** It sends 100 percent to an earlier revision, ready, by name, or
the newest ready before the one serving. The template is left as it is, so that no revision is
created. The key is put on the service's own annotations, where a repeat finds it.

**A stale write is refused by the API.** A change carries the `etag` the service was read with;
the API refuses a write over a service changed in between, `conflict`.

A change answers a long-running operation; the connector does not wait for it. A reading says
whether the rollout is complete: `rolled_out`.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a request the API refuses | `invalid` |
| 401: the token is not admitted, or the key is refused at the token endpoint | `unauthenticated` |
| 403: the service account may not do this | `forbidden` |
| 404: no such service in the project's location | `not_found` |
| 409, 412: the service changed since it was read | `conflict` |
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

from taktus_connectors.cloudrun.auth import access_token, token_endpoint
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://run.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
KEY_ANNOTATION = "taktus.eu/idempotency-key"
LATEST = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
REVISION = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
SUCCEEDED = "CONDITION_SUCCEEDED"
SERVICE = re.compile(r"^[a-z]([-a-z0-9]{0,47}[a-z0-9])?$")
CONTAINER = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")
PAGES = 20


@dataclass(frozen=True)
class Config:
    target: str
    """The API's address: `https://run.googleapis.com`, or a fake's."""
    project: str
    location: str
    timeout: float = 30.0
    token_endpoint: str = ""
    """Where the key is exchanged, where it is neither Google's nor `<target>/token`."""

    def token(self) -> str:
        return token_endpoint(self.target, TARGET, self.token_endpoint)

    def services(self) -> str:
        return f"/v2/projects/{self.project}/locations/{self.location}/services"


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _request(
    config: Config,
    call: Call,
    token: str,
    method: str,
    path: str,
    *,
    body: Any = None,
    params: Json | None = None,
) -> Any:
    writing = method != "GET"
    call.count()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(
                method,
                path,
                headers=headers,
                params=params,
                content=None if body is None else json.dumps(body).encode("utf-8"),
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the API did not answer the write in time"
            ) from error
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            return response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the API answered the write unreadably"
                ) from error
            raise _unexpected("the API answered with a body that is not JSON") from error
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the service account may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such service in the location")
    if status in (409, 412):
        raise TargetError("conflict", "none", False, "the service changed since it was read")
    if status == 400:
        raise invalid("the API refused the request: 400")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _name(input: Json) -> str:
    value = input.get("name")
    if not isinstance(value, str) or SERVICE.match(value) is None:
        raise invalid("name must be the name of a service: lower case, digits and dashes")
    return value


def _short(name: Any) -> str | None:
    """A revision's own name, the last segment of its full name."""
    return str(name).rsplit("/", 1)[-1] if name else None


def _annotations(resource: Json) -> Json:
    found = resource.get("annotations") or {}
    return found if isinstance(found, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _serving(service: Json) -> str | None:
    """The revision the traffic goes to wholly: one named, or the latest ready for `LATEST`
    and for no traffic at all. None when the traffic is split."""
    traffic = [t for t in service.get("traffic") or [] if _int(t.get("percent")) > 0]
    latest = _short(service.get("latestReadyRevision"))
    if not traffic:
        return latest
    if len(traffic) != 1 or _int(traffic[0].get("percent")) != 100:
        return None
    target = traffic[0]
    if target.get("type") == REVISION:
        return _short(target.get("revision"))
    return latest


def service_output(service: Json, config: Config) -> Json:
    """What a reading yields of a service, and whether its rollout is complete."""
    if not isinstance(service, dict) or not isinstance(service.get("template"), dict):
        raise _unexpected("the API answered a service in a shape the connector does not know")
    template = service["template"]
    ready = _short(service.get("latestReadyRevision"))
    created = _short(service.get("latestCreatedRevision"))
    condition = service.get("terminalCondition") or {}
    return {
        "name": str(service.get("name", "")).rsplit("/", 1)[-1],
        "namespace": config.location,
        "containers": [
            {"name": str(c.get("name", "")), "image": str(c.get("image", ""))}
            for c in template.get("containers") or []
        ],
        "replicas": None,
        "updated": None,
        "ready": None,
        "available": None,
        "revision": ready,
        "key": _annotations(template).get(KEY_ANNOTATION),
        "rolled_out": not service.get("reconciling", False)
        and condition.get("state") == SUCCEEDED
        and ready is not None
        and ready == created
        and _int(service.get("observedGeneration")) >= _int(service.get("generation"))
        and _serving(service) == ready,
    }


async def _service(config: Config, call: Call, token: str, name: str) -> Json:
    found = await _request(config, call, token, "GET", f"{config.services()}/{name}")
    service_output(found, config)  # refuses a shape it does not know
    return dict(found)


async def _revisions(config: Config, call: Call, token: str, name: str) -> list[Json]:
    """Every revision the service keeps, page by page."""
    found: list[Json] = []
    page: str | None = None
    for _ in range(PAGES):
        params: Json = {"pageSize": 100}
        if page:
            params["pageToken"] = page
        listed = await _request(
            config, call, token, "GET", f"{config.services()}/{name}/revisions", params=params
        )
        items = listed.get("revisions", []) if isinstance(listed, dict) else None
        if not isinstance(items, list):
            raise _unexpected("the API's list of revisions is not a list")
        found.extend(r for r in items if isinstance(r, dict))
        page = listed.get("nextPageToken") or None
        if not page:
            return found
    raise _unexpected(f"the service keeps more revisions than {PAGES} pages")


def _ready(revision: Json) -> bool:
    return any(
        c.get("type") == "Ready" and c.get("state") == SUCCEEDED
        for c in revision.get("conditions") or []
        if isinstance(c, dict)
    )


def _records(config: Config, name: str, key: str) -> list[Json]:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return [{"kind": "deployment.revision", "id": f"{config.location}/{name}@{digest}"}]


def _write(output: Json, config: Config, name: str, key: str, *, replayed: bool) -> Outcome:
    records = _records(config, name, key)
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def read_service(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    token = await access_token(call, SCOPE, config.timeout, config.token())
    found = await _service(config, call, token, name)
    return Outcome(service_output(found, config), {"kind": "read"})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    container = input.get("container")
    if not isinstance(container, str) or CONTAINER.match(container) is None:
        raise invalid("container must be the name of a container: lower case, digits and dashes")
    image = input.get("image")
    if not isinstance(image, str) or IMAGE.match(image) is None:
        raise invalid("image must be an image reference: registry, name and tag or digest")
    token = await access_token(call, SCOPE, config.timeout, config.token())
    found = await _service(config, call, token, name)
    if _annotations(found["template"]).get(KEY_ANNOTATION) == call.key or any(
        _annotations(r).get(KEY_ANNOTATION) == call.key
        for r in await _revisions(config, call, token, name)
    ):
        return _write(service_output(found, config), config, name, call.key, replayed=True)
    changed = copy.deepcopy(found)
    containers = changed["template"].get("containers") or []
    target = next((c for c in containers if c.get("name") == container), None)
    if target is None:
        raise invalid(f"the service {name!r} has no container {container!r}")
    target["image"] = image
    changed["template"].setdefault("annotations", {})[KEY_ANNOTATION] = call.key
    changed["traffic"] = [{"type": LATEST, "percent": 100}]
    await _request(config, call, token, "PATCH", f"{config.services()}/{name}", body=changed)
    written = await _service(config, call, token, name)
    return _write(service_output(written, config), config, name, call.key, replayed=False)


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input)
    wanted = input.get("revision")
    if wanted is not None and (not isinstance(wanted, str) or not wanted):
        raise invalid("revision must be a revision's name")
    token = await access_token(call, SCOPE, config.timeout, config.token())
    found = await _service(config, call, token, name)
    if _annotations(found).get(KEY_ANNOTATION) == call.key:
        output = {**service_output(found, config), "to_revision": _serving(found)}
        return _write(output, config, name, call.key, replayed=True)
    current = _serving(found)
    ready = sorted(
        (r for r in await _revisions(config, call, token, name) if _ready(r)),
        key=lambda r: str(r.get("createTime", "")),
    )
    names = [_short(r.get("name")) for r in ready]
    if wanted is not None:
        target = wanted if wanted in names and wanted != current else None
    else:
        before = names[: names.index(current)] if current in names else []
        target = before[-1] if before else None
    if target is None:
        raise TargetError(
            "not_found", "none", False, f"the service {name!r} keeps no such earlier revision"
        )
    changed = copy.deepcopy(found)
    changed.setdefault("annotations", {})[KEY_ANNOTATION] = call.key
    changed["traffic"] = [{"type": REVISION, "revision": target, "percent": 100}]
    await _request(config, call, token, "PATCH", f"{config.services()}/{name}", body=changed)
    written = await _service(config, call, token, name)
    output = {**service_output(written, config), "to_revision": target}
    return _write(output, config, name, call.key, replayed=False)


OPERATIONS = {
    "deployment.workloads.read": read_service,
    "deployment.workloads.release": release,
    "deployment.workloads.rollback": rollback,
}
