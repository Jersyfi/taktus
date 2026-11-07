"""How the Firebase Hosting REST API v1beta1 is asked, and its answers read (`deployment.sites`).

Every request goes to `--target` under `/v1beta1/sites/<site>/`, with an access token the
requesting identity's service account key is exchanged for (`auth.py`); the connector has no key
of its own.

**A release puts a version live.** A version is a site's content and configuration, uploaded and
finalized by the site's own build. A release of a version on the site's live channel is what the
site serves. A rollback is the same act with an earlier version; the API records the release's
type itself.

**The mark.** A release carries a message. The connector writes the caller's message, if any,
followed by `taktus:` and the first 16 hexadecimal digits of the SHA-256 of the idempotency key.
Before writing, it lists the site's releases: a release whose message carries the mark is the
original, and nothing is released again.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| a version that is not finalized | `conflict`, before anything is written |
| 400: a request the API refuses | `invalid` |
| 401: the token is not admitted, or the key is refused at the token endpoint | `unauthenticated` |
| 403: the service account may not do this | `forbidden` |
| 404: no such site or version | `not_found` |
| 409, 412: the site changed under the request | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.firebase.auth import access_token
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

SCOPE = "https://www.googleapis.com/auth/firebase.hosting"
SITE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
VERSION = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MESSAGE = 400
"""The longest message a caller may give: the API keeps 512 characters, the mark takes 24."""
FINALIZED = "FINALIZED"
PAGES = 20


@dataclass(frozen=True)
class Config:
    target: str
    """The API's address: `https://firebasehosting.googleapis.com`, or a fake's."""
    timeout: float = 30.0


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
                f"/v1beta1/{path}",
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
        raise TargetError("not_found", "none", False, "no such site or version")
    if status in (409, 412):
        raise TargetError("conflict", "none", False, "the site changed under the request")
    if status == 400:
        raise invalid("the API refused the request: 400")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _site(input: Json) -> str:
    value = input.get("name")
    if not isinstance(value, str) or SITE.match(value) is None:
        raise invalid("name must be a site's identifier: lower case, digits and dashes")
    return value


def _version(input: Json, *, required: bool) -> str | None:
    value = input.get("version")
    if value is None and not required:
        return None
    if not isinstance(value, str) or VERSION.match(value) is None:
        raise invalid("version must be a version's identifier: letters, digits, - and _")
    return value


def _last(name: Any) -> str | None:
    return str(name).rsplit("/", 1)[-1] if name else None


def _mark(key: str) -> str:
    return "taktus:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


async def _live(config: Config, call: Call, token: str, site: str) -> str | None:
    """The version the live channel's current release serves; None for none or a disabled
    site."""
    channel = await _request(config, call, token, "GET", f"sites/{site}/channels/live")
    if not isinstance(channel, dict):
        raise _unexpected("the API answered a channel in a shape the connector does not know")
    release = channel.get("release") or {}
    return _last((release.get("version") or {}).get("name"))


async def _read_version(config: Config, call: Call, token: str, site: str, version: str) -> Json:
    found = await _request(config, call, token, "GET", f"sites/{site}/versions/{version}")
    if not isinstance(found, dict) or "name" not in found:
        raise _unexpected("the API answered a version in a shape the connector does not know")
    state = str(found.get("status", ""))
    return {"id": version, "state": state, "ready": state == FINALIZED}


async def _marked(config: Config, call: Call, token: str, site: str, mark: str) -> Json | None:
    """The release of the site whose message carries the mark, page by page."""
    page: str | None = None
    for _ in range(PAGES):
        params: Json = {"pageSize": 100}
        if page:
            params["pageToken"] = page
        listed = await _request(config, call, token, "GET", f"sites/{site}/releases", params=params)
        items = listed.get("releases", []) if isinstance(listed, dict) else None
        if not isinstance(items, list):
            raise _unexpected("the API's list of releases is not a list")
        for release in items:
            if isinstance(release, dict) and mark in str(release.get("message", "")):
                return release
        page = listed.get("nextPageToken") or None
        if not page:
            return None
    raise _unexpected(f"the site keeps more releases than {PAGES} pages")


async def read_site(config: Config, call: Call, input: Json) -> Outcome:
    site = _site(input)
    version = _version(input, required=False)
    token = await access_token(call, SCOPE, config.timeout)
    live = await _live(config, call, token, site)
    found = await _read_version(config, call, token, site, version) if version else None
    return Outcome(
        {
            "name": site,
            "live": live,
            "version": found,
            "rolled_out": found is not None and found["ready"] and live == version,
        },
        {"kind": "read"},
    )


async def _publish(config: Config, call: Call, input: Json, *, kind: str) -> Outcome:
    site = _site(input)
    version = _version(input, required=True) or ""
    message = input.get("message", "")
    if not isinstance(message, str) or len(message) > MESSAGE:
        raise invalid(f"message is text of at most {MESSAGE} characters")
    token = await access_token(call, SCOPE, config.timeout)
    mark = _mark(call.key)
    found = await _marked(config, call, token, site, mark)
    if found is not None:
        live = await _live(config, call, token, site)
        output = {"name": site, "live": live, "previous": None, "release": found.get("name")}
        if kind == "rollback":
            output["to_version"] = _last((found.get("version") or {}).get("name"))
        return _written(output, found, replayed=True)
    described = await _read_version(config, call, token, site, version)
    if not described["ready"]:
        raise TargetError(
            "conflict",
            "none",
            False,
            f"the version {version!r} is {described['state'] or 'not finalized'}, not finalized",
        )
    previous = await _live(config, call, token, site)
    made = await _request(
        config,
        call,
        token,
        "POST",
        f"sites/{site}/releases",
        params={"versionName": f"sites/{site}/versions/{version}"},
        body={"message": f"{message} {mark}".strip()},
    )
    if not isinstance(made, dict) or not made.get("name"):
        raise TargetError("unknown", "unknown", False, "the API answered the release unreadably")
    output = {
        "name": site,
        "live": _last((made.get("version") or {}).get("name")) or version,
        "previous": previous,
        "release": made["name"],
    }
    if kind == "rollback":
        output["to_version"] = version
    return _written(output, made, replayed=False)


def _written(output: Json, release: Json, *, replayed: bool) -> Outcome:
    records = [{"kind": "site.release", "id": str(release.get("name", ""))}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input, kind="release")


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input, kind="rollback")


OPERATIONS = {
    "deployment.sites.read": read_site,
    "deployment.sites.release": release,
    "deployment.sites.rollback": rollback,
}
