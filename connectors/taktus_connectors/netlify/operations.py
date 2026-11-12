"""How the hosting service's API is asked, and its answers read.

Every request goes to `--target` under `/api/v1/`, with the requesting identity's token as a
bearer token, never one of the connector's own. A site is `GET sites/<site_id>`: its
`published_deploy` is the version it publishes. A deploy is `GET sites/<site_id>/deploys/<id>`:
its `state` is the service's own word, `ready` once it is built and can be published. A
release and a rollback are both `POST sites/<site_id>/deploys/<id>/restore`, which publishes
that deploy and answers 201 with it (the API's `restoreSiteDeploy`).

**The mark is the state.** Before acting, the connector reads the site: a site that already
publishes the deploy is the original, replayed, and nothing is written again. The restore
carries no field a key could be written into. A repeat after somebody else published the same
deploy therefore reports replayed too; that is weaker than a key, and stated so.

**What is published was built before.** A deploy whose state is not `ready` is refused as
`conflict` before anything is written: the connector publishes, it never builds.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: a request the API refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token may not do this | `forbidden` |
| 404: no such site or deploy | `not_found` |
| 409: the site changed under the write | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat finds the deploy published |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.netlify.com"
SITE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")
"""A site's identifier, or its name or domain, which the API takes in its place."""
DEPLOY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
READY = "ready"


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _request(config: Config, call: Call, method: str, path: str) -> Json:
    writing = method != "GET"
    call.count()
    headers = {"Authorization": f"Bearer {call.token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(method, f"/api/v1/{path}", headers=headers)
    except httpx.ConnectError as error:
        raise unavailable(f"the service could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the service did not answer the write in time"
            ) from error
        raise unavailable(f"the service did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the service could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            found = response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the service answered the write unreadably"
                ) from error
            raise _unexpected("the service answered with a body that is not JSON") from error
        if not isinstance(found, dict):
            raise _unexpected("the service answered in a shape the connector does not know")
        return found
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the service does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such site or deploy")
    if status == 409:
        raise TargetError("conflict", "none", False, "the site changed under the write")
    if status in (400, 422):
        raise invalid(f"the service refused the request: {status}")
    if status == 429 or status >= 500:
        raise unavailable(f"the service answered {status}")
    raise _unexpected(f"the service answered {status}, which the connector does not foresee")


def _site(input: Json) -> str:
    value = input.get("name")
    if not isinstance(value, str) or SITE.match(value) is None:
        raise invalid("name must be a site's identifier or its name")
    return value


def _deploy(input: Json) -> str:
    value = input.get("version")
    if not isinstance(value, str) or DEPLOY.match(value) is None:
        raise invalid("version must be a deploy's identifier")
    return value


def _live(site: Json) -> str | None:
    published = site.get("published_deploy")
    if published is None:
        return None
    if not isinstance(published, dict):
        raise _unexpected("the service answered a site in a shape the connector does not know")
    found = published.get("id")
    return str(found) if found else None


def _version(deploy: Json) -> Json:
    if "id" not in deploy:
        raise _unexpected("the service answered a deploy in a shape the connector does not know")
    state = str(deploy.get("state", ""))
    return {"id": str(deploy["id"]), "state": state, "ready": state == READY}


async def read_site(config: Config, call: Call, input: Json) -> Outcome:
    site = _site(input)
    wanted = None if input.get("version") is None else _deploy(input)
    live = _live(await _request(config, call, "GET", f"sites/{site}"))
    version = None
    if wanted is not None:
        version = _version(await _request(config, call, "GET", f"sites/{site}/deploys/{wanted}"))
    output = {
        "name": site,
        "live": live,
        "version": version,
        "rolled_out": version is not None and version["ready"] and live == version["id"],
    }
    return Outcome(output, {"kind": "read"})


async def _publish(config: Config, call: Call, input: Json) -> Outcome:
    site = _site(input)
    wanted = _deploy(input)
    records = [{"kind": "site.release", "id": f"{site}@{wanted}"}]
    live = _live(await _request(config, call, "GET", f"sites/{site}"))
    if live == wanted:
        output = {"name": site, "live": live, "previous": None}
        return Outcome(output, {"kind": "write", "replayed": True, "records": records})
    version = _version(await _request(config, call, "GET", f"sites/{site}/deploys/{wanted}"))
    if not version["ready"]:
        raise TargetError(
            "conflict",
            "none",
            False,
            f"the deploy is {version['state']!r}, not ready: only a built deploy is published",
        )
    published = _version(
        await _request(config, call, "POST", f"sites/{site}/deploys/{wanted}/restore")
    )
    output = {"name": site, "live": published["id"], "previous": live}
    return Outcome(output, {"kind": "write", "replayed": False, "records": records})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input)


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input)


OPERATIONS = {
    "deployment.sites.read": read_site,
    "deployment.sites.release": release,
    "deployment.sites.rollback": rollback,
}
