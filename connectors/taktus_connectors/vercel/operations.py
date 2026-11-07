"""How the hosting platform's REST API is asked, and its answers read.

Every request goes to `--target`, with the requesting identity's token as a bearer token, never
one of the connector's own, and with `teamId` where `--team` names a team. A project is
`GET /v9/projects/<idOrName>`: `targets.production` is the deployment its production serves,
and `lastAliasRequest` the newest promotion or rollback with its `toDeploymentId` and
`jobStatus`. A deployment is `GET /v13/deployments/<id>`: its `readyState` is the platform's own
word, `READY` once it is built, and its `projectId` the project it belongs to. A release is
`POST /v10/projects/<projectId>/promote/<deploymentId>`, which points production at a deployment
without building it again; the platform answers 201, or 202 when it carries the promotion out
afterwards. A rollback is `POST /v1/projects/<projectId>/rollback/<deploymentId>`, which points
production back at an earlier production deployment and answers 201.

**The mark is the state.** Before acting, the connector reads the project: production serving
the deployment already, or a newest promotion or rollback to it that is pending, in progress or
succeeded, is the original, replayed, and nothing is written again. Neither request carries a
field a key could be written into. A repeat after somebody else promoted the same deployment
therefore reports replayed too; that is weaker than a key, and stated so.

**What is promoted was built before.** A deployment whose `readyState` is not `READY` is refused
as `conflict` before anything is written. A deployment of another project is `not_found`.

**A promotion can finish later.** The output's `live` is what the project's production serves
when the write was answered; `deployment.sites.read` with the version says when it is
`rolled_out`.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: a request the API refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 402, 403: the token or the plan may not do this | `forbidden` |
| 404, 410: no such project or deployment, or one removed | `not_found` |
| 409: the project's production changed under the write | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat finds the promotion |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.vercel.com"
PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
DEPLOYMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,63}$")
READY = "READY"
UNDER_WAY = frozenset({"pending", "in-progress", "succeeded"})
"""The `jobStatus` of a promotion or rollback that is, or will be, carried out."""


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address."""
    team: str | None = None
    """The team every request is made on behalf of (`teamId`); None for the token's account."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _request(config: Config, call: Call, method: str, path: str) -> Json:
    writing = method != "GET"
    call.count()
    headers = {"Authorization": f"Bearer {call.token}", "Accept": "application/json"}
    params = {"teamId": config.team} if config.team else None
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(method, path, headers=headers, params=params)
    except httpx.ConnectError as error:
        raise unavailable(f"the platform could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the platform did not answer the write in time"
            ) from error
        raise unavailable(f"the platform did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the platform could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201, 202):
        if writing:
            return {}  # what a write answers is not read: the project is read again
        try:
            found = response.json()
        except ValueError as error:
            raise _unexpected("the platform answered with a body that is not JSON") from error
        if not isinstance(found, dict):
            raise _unexpected("the platform answered in a shape the connector does not know")
        return found
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the platform does not admit the token")
    if status in (402, 403):
        raise TargetError("forbidden", "none", False, "the token or the plan may not do this")
    if status in (404, 410):
        raise TargetError("not_found", "none", False, "no such project or deployment")
    if status == 409:
        raise TargetError("conflict", "none", False, "the production changed under the write")
    if status in (400, 422):
        raise invalid(f"the platform refused the request: {status}")
    if status == 429 or status >= 500:
        raise unavailable(f"the platform answered {status}")
    raise _unexpected(f"the platform answered {status}, which the connector does not foresee")


def _project_name(input: Json) -> str:
    value = input.get("name")
    if not isinstance(value, str) or PROJECT.match(value) is None:
        raise invalid("name must be a project's identifier or its name")
    return value


def _deployment_id(input: Json) -> str:
    value = input.get("version")
    if not isinstance(value, str) or DEPLOYMENT.match(value) is None:
        raise invalid("version must be a deployment's identifier")
    return value


def _project(found: Json) -> tuple[str, str | None]:
    """The project's identifier, and the deployment its production serves."""
    identifier = found.get("id")
    if not isinstance(identifier, str):
        raise _unexpected("the platform answered a project in a shape the connector does not know")
    targets = found.get("targets") or {}
    production = targets.get("production") if isinstance(targets, dict) else None
    live = production.get("id") if isinstance(production, dict) else None
    return identifier, str(live) if live else None


def _under_way(found: Json, deployment: str) -> bool:
    """Whether the newest promotion or rollback points production at the deployment."""
    last = found.get("lastAliasRequest")
    return (
        isinstance(last, dict)
        and last.get("toDeploymentId") == deployment
        and last.get("jobStatus") in UNDER_WAY
    )


async def _deployment(config: Config, call: Call, project: str, deployment: str) -> Json:
    found = await _request(config, call, "GET", f"/v13/deployments/{deployment}")
    if "id" not in found:
        raise _unexpected(
            "the platform answered a deployment in a shape the connector does not know"
        )
    if found.get("projectId") not in (None, project):
        raise TargetError("not_found", "none", False, "the deployment belongs to another project")
    state = str(found.get("readyState", ""))
    return {"id": str(found["id"]), "state": state, "ready": state == READY}


async def read_project(config: Config, call: Call, input: Json) -> Outcome:
    name = _project_name(input)
    wanted = None if input.get("version") is None else _deployment_id(input)
    project, live = _project(await _request(config, call, "GET", f"/v9/projects/{name}"))
    version = None if wanted is None else await _deployment(config, call, project, wanted)
    output = {
        "name": name,
        "live": live,
        "version": version,
        "rolled_out": version is not None and version["ready"] and live == version["id"],
    }
    return Outcome(output, {"kind": "read"})


async def _point(config: Config, call: Call, input: Json, kind: str) -> Outcome:
    name = _project_name(input)
    wanted = _deployment_id(input)
    records = [{"kind": "site.release", "id": f"{name}@{wanted}"}]
    found = await _request(config, call, "GET", f"/v9/projects/{name}")
    project, live = _project(found)
    if live == wanted or _under_way(found, wanted):
        output = {"name": name, "live": live, "previous": None}
        return Outcome(output, {"kind": "write", "replayed": True, "records": records})
    version = await _deployment(config, call, project, wanted)
    if not version["ready"]:
        raise TargetError(
            "conflict",
            "none",
            False,
            f"the deployment is {version['state']!r}, not READY: only a built one is promoted",
        )
    path = (
        f"/v10/projects/{project}/promote/{wanted}"
        if kind == "promote"
        else f"/v1/projects/{project}/rollback/{wanted}"
    )
    await _request(config, call, "POST", path)
    try:
        _, now = _project(await _request(config, call, "GET", f"/v9/projects/{name}"))
    except TargetError as error:
        # The write was answered: a failed reading after it must not read as no write.
        raise TargetError("unknown", "unknown", False, "the project could not be read again") from (
            error
        )
    output = {"name": name, "live": now, "previous": live}
    return Outcome(output, {"kind": "write", "replayed": False, "records": records})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    return await _point(config, call, input, "promote")


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    return await _point(config, call, input, "rollback")


OPERATIONS = {
    "deployment.sites.read": read_project,
    "deployment.sites.release": release,
    "deployment.sites.rollback": rollback,
}
