"""How the Cloud Functions API v2 is asked, and its answers read (`deployment.sites`).

Every request goes to `--target` under `/v2/projects/<project>/locations/<location>/functions/`,
with an access token the requesting identity's service account key is exchanged for
(`auth.py`); the connector has no key of its own.

**A version is a source archive.** A function has no image and no replicas. The platform builds
it from a source archive the business's own build uploaded to Cloud Storage, named by its bucket,
its object and its generation. The connector writes a version `<bucket>/<object>#<generation>`.
The generation is required, so that a version names one archive for good. The version a function
serves is the archive its last successful build was made from (`sourceProvenance`), which keeps
the generation even where the source was given without one.

**A release puts a version live.** It patches the function's `buildConfig.source` to the archive;
the platform builds and deploys it. A rollback is the same act with an earlier version, which the
caller names. The API answers a long-running operation; the connector does not wait for it, and a
reading says whether the version is live and the function `ACTIVE`: `rolled_out`.

**The mark.** The function carries the label `taktus-key`, the first 40 hexadecimal digits of the
SHA-256 of the idempotency key; a label value takes at most 63 lowercase letters, digits,
underscores and dashes. Before writing, the connector reads the function: a function whose label
is the mark is the original, and nothing is written again. The function keeps one label of that
name, so a repeat after another write under another key acts again.

A function that is still deploying is a `conflict` before anything is written: a second change
would be refused or would land on a build not yet finished.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| a function in state `DEPLOYING` or `DELETING` | `conflict`, before anything is written |
| 400: a request the API refuses | `invalid` |
| 401: the token is not admitted, or the key is refused at the token endpoint | `unauthenticated` |
| 403: the service account may not do this | `forbidden` |
| 404: no such function in the location | `not_found` |
| 409, 412: an operation on the function is already in progress | `conflict` |
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

from taktus_connectors.cloudfunctions.auth import access_token, token_endpoint
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://cloudfunctions.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
LABEL = "taktus-key"
ACTIVE = "ACTIVE"
BUSY = frozenset({"DEPLOYING", "DELETING"})
FUNCTION = re.compile(r"^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$")
VERSION = re.compile(
    r"^(?P<bucket>[a-z0-9][a-z0-9._-]{1,61}[a-z0-9])/"
    r"(?P<object>[A-Za-z0-9._-][A-Za-z0-9._/-]{0,511})#(?P<generation>[0-9]{1,20})$"
)
MASK = "buildConfig.source,labels"


@dataclass(frozen=True)
class Config:
    target: str
    """The API's address: `https://cloudfunctions.googleapis.com`, or a fake's."""
    project: str
    location: str
    timeout: float = 30.0
    token_endpoint: str = ""
    """Where the key is exchanged, where it is neither Google's nor `<target>/token`."""

    def token(self) -> str:
        return token_endpoint(self.target, TARGET, self.token_endpoint)

    def functions(self) -> str:
        return f"/v2/projects/{self.project}/locations/{self.location}/functions"


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
        raise TargetError("not_found", "none", False, "no such function in the location")
    if status in (409, 412):
        raise TargetError(
            "conflict", "none", False, "an operation on the function is already in progress"
        )
    if status == 400:
        raise invalid("the API refused the request: 400")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _function(input: Json) -> str:
    value = input.get("name")
    if not isinstance(value, str) or FUNCTION.match(value) is None:
        raise invalid("name must be a function's identifier: lower case, digits and dashes")
    return value


def _version(input: Json, *, required: bool) -> str | None:
    value = input.get("version")
    if value is None and not required:
        return None
    if not isinstance(value, str) or VERSION.match(value) is None:
        raise invalid("version must be a source archive: <bucket>/<object>#<generation>")
    return value


def mark(key: str) -> str:
    """The label's value: a digest of the key, never the key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]


def _written_version(source: Any) -> str | None:
    """A storage source as a version, or None where it is not one with a generation."""
    if not isinstance(source, dict):
        return None
    bucket, name, generation = source.get("bucket"), source.get("object"), source.get("generation")
    if not (bucket and name and generation):
        return None
    return f"{bucket}/{name}#{generation}"


def _live(function: Json) -> str | None:
    """The archive the function's last successful build was made from."""
    build = function.get("buildConfig") or {}
    provenance = build.get("sourceProvenance") or {}
    resolved = _written_version(provenance.get("resolvedStorageSource"))
    if resolved is not None:
        return resolved
    return _written_version((build.get("source") or {}).get("storageSource"))


def _labels(function: Json) -> Json:
    found = function.get("labels") or {}
    return dict(found) if isinstance(found, dict) else {}


async def _read(config: Config, call: Call, token: str, name: str) -> Json:
    found = await _request(config, call, token, "GET", f"{config.functions()}/{name}")
    if not isinstance(found, dict) or not isinstance(found.get("buildConfig"), dict):
        raise _unexpected("the API answered a function in a shape the connector does not know")
    return found


async def read_site(config: Config, call: Call, input: Json) -> Outcome:
    name = _function(input)
    version = _version(input, required=False)
    token = await access_token(call, SCOPE, config.timeout, config.token())
    found = await _read(config, call, token, name)
    live = _live(found)
    state = str(found.get("state", ""))
    described = (
        {"id": version, "state": state, "ready": state == ACTIVE and live == version}
        if version
        else None
    )
    return Outcome(
        {
            "name": name,
            "live": live,
            "version": described,
            "rolled_out": described is not None and described["ready"],
        },
        {"kind": "read"},
    )


def _records(config: Config, name: str, key: str) -> list[Json]:
    return [{"kind": "site.release", "id": f"{config.location}/{name}@{mark(key)[:16]}"}]


async def _publish(config: Config, call: Call, input: Json, *, kind: str) -> Outcome:
    name = _function(input)
    version = _version(input, required=True) or ""
    parts = VERSION.match(version)
    if parts is None:
        raise invalid("version must be a source archive: <bucket>/<object>#<generation>")
    token = await access_token(call, SCOPE, config.timeout, config.token())
    found = await _read(config, call, token, name)
    records = _records(config, name, call.key)
    if _labels(found).get(LABEL) == mark(call.key):
        output: Json = {"name": name, "live": _live(found), "previous": None, "release": None}
        if kind == "rollback":
            output["to_version"] = version
        return Outcome(output, {"kind": "write", "replayed": True, "records": records})
    state = str(found.get("state", ""))
    if state in BUSY:
        raise TargetError(
            "conflict", "none", False, f"the function {name!r} is {state}, not ready for a change"
        )
    previous = _live(found)
    labels = {**_labels(found), LABEL: mark(call.key)}
    body = {
        "name": str(found.get("name") or f"{config.functions()[4:]}/{name}"),
        "buildConfig": {
            "source": {
                "storageSource": {
                    "bucket": parts["bucket"],
                    "object": parts["object"],
                    "generation": parts["generation"],
                }
            }
        },
        "labels": labels,
    }
    made = await _request(
        config,
        call,
        token,
        "PATCH",
        f"{config.functions()}/{name}",
        params={"updateMask": MASK},
        body=body,
    )
    if not isinstance(made, dict) or not made.get("name"):
        raise TargetError("unknown", "unknown", False, "the API answered the change unreadably")
    output = {"name": name, "live": version, "previous": previous, "release": str(made["name"])}
    if kind == "rollback":
        output["to_version"] = version
    return Outcome(output, {"kind": "write", "replayed": False, "records": records})


async def release(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input, kind="release")


async def rollback(config: Config, call: Call, input: Json) -> Outcome:
    return await _publish(config, call, input, kind="rollback")


OPERATIONS = {
    "deployment.sites.read": read_site,
    "deployment.sites.release": release,
    "deployment.sites.rollback": rollback,
}
