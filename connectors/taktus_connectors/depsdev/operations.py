"""How the licences of a manifest's pinned versions are asked and their answer read.

The API v3 answers `GET /v3/systems/{system}/packages/{name}/versions/{version}` (GetVersion)
with one version: `versionKey`, `publishedAt`, `isDefault`, `licenses` — SPDX expressions, or
`non-standard`, empty where the index knows none — and more the connector does not read. The
name and the version are percent-encoded whole, `@` and `/` among them, as the API asks. One
request per version; the index takes no key.

| Answer | Cause |
|---|---|
| 404: the index holds no such version | not a failure: the package is answered with `known` false |
| 400: a name or version the index refuses | the same: `known` false |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The manifest is never sent: only each package's system, name and version leave the connector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from taktus_connectors.depsdev.manifests import FORMATS, NotTheFormat, Pinned, pinned
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.deps.dev"
LIMIT = 500
MAX_LIMIT = 2000
MAX_TEXT = 20_000_000
"""The largest manifest read, in characters: a lockfile of thousands of packages fits."""


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the index's own, or a fake's."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _version(client: httpx.AsyncClient, call: Call, package: Pinned) -> Json:
    path = (
        f"/v3/systems/{package.system}/packages/{quote(package.name, safe='')}"
        f"/versions/{quote(package.version, safe='')}"
    )
    call.count()
    try:
        response = await client.get(path)
    except httpx.TimeoutException as error:
        raise unavailable(f"the index did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        raise unavailable(f"the index could not be reached: {type(error).__name__}") from error
    entry: Json = {
        "system": package.system,
        "name": package.name,
        "version": package.version,
        "dev": package.dev,
        "licences": [],
        "known": False,
    }
    status = response.status_code
    if status in (400, 404):
        return entry
    if status == 429 or status >= 500:
        raise unavailable(f"the index answered {status}")
    if status != 200:
        raise _unexpected(f"the index answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("versionKey"), dict):
        raise _unexpected("the index answered with a body it does not use")
    licences = body.get("licenses")
    if not isinstance(licences, list) or not all(isinstance(x, str) for x in licences):
        raise _unexpected("the index answered licences that are not a list of texts")
    return {**entry, "licences": list(licences), "known": True}


async def licences(config: Config, call: Call, input: Json) -> Outcome:
    """The licences of every exact version the manifest pins (ADR-0232)."""
    format, text = input.get("format"), input.get("manifest")
    if format not in FORMATS:
        raise invalid(f"format must be one of {', '.join(FORMATS)}")
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
        raise invalid(f"manifest must be the manifest's text, at most {MAX_TEXT} characters")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    try:
        packages, unpinned = pinned(format, text)
    except NotTheFormat as error:
        raise invalid(f"the manifest is not a {format}: {error}") from error
    async with httpx.AsyncClient(
        base_url=config.target.rstrip("/"),
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
    ) as client:
        read = [await _version(client, call, package) for package in packages[:limit]]
    output = {"packages": read, "unpinned": unpinned, "complete": len(packages) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"packages.licences.list": licences}
