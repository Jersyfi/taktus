"""How the secrets are listed and their metadata read, never their values.

The store's KV secrets engine version 2 keeps every secret under a mount. Two of its endpoints
are asked, both under `/v1/<mount>/metadata/`:

- **List** `GET /v1/<mount>/metadata/<folder>?list=true` answers `{"data": {"keys": [...]}}`:
  the names directly in the folder, a name ending in `/` being a folder below it. The API
  documents the verb `LIST` and says a `GET` with `list=true` is the same request; the `GET`
  is used because a proxy on the way may refuse a verb it does not know. A folder without
  keys is answered 404 with `{"errors": []}`, which the API documents for a list without
  results: it is an empty folder here, not an error. A 404 whose `errors` say something is an
  unknown mount or route, and is `invalid`.
- **Read metadata** `GET /v1/<mount>/metadata/<name>` answers the secret's `created_time`,
  `updated_time`, `current_version`, `versions` and more. A secret listed and gone before its
  metadata is read is skipped.

`/v1/<mount>/data/...` is never asked: it is the one endpoint of the engine that answers a value.

What is reported, as the store states it:

- `created_at` is the secret's `created_time`: its first version.
- `changed_at` is the `created_time` of the version named `current_version`: the moment the
  current value was written. The API does not define `updated_time`; its example shows it
  equal to the newest version's `created_time`, but it is not used, because a change of the
  metadata alone may move it.
- `rotation` is `{"automatic": null, ...}`: the engine stores versions a writer creates and
  has no rotation of its own, so it states nothing about one.
- `expires_at` is null. `delete_version_after` sets when a version is *deleted*, and a
  deleted version is a soft delete the API can undo (`undelete`); the secret does not expire.
- `last_accessed_at` is null: the engine records no read of a secret.

A version's `created_by` names who wrote it; it is never copied (principle 14).

The walk is bounded: folders at most `MAX_DEPTH` deep and `MAX_FOLDERS` lists, at most
`MAX_SECRETS` metadata reads. A walk cut by a bound reports `complete: false`.

How the store's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400 | `invalid` |
| 404 on a list with `errors` empty | an empty folder, no error |
| 404 otherwise on a list: an unknown mount | `invalid` |
| 401 | `unauthenticated` |
| 403: an unknown token or one without the permission; the API tells neither | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The store's own `errors` stay out of the error's `detail`: they can quote a path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

MOUNT = "secret"
LIMIT = 100
MAX_LIMIT = 500
MAX_PREFIX = 500
MAX_DEPTH = 10
MAX_FOLDERS = 100
MAX_SECRETS = 1000
SEGMENT = r"[A-Za-z0-9._@=+-]+"
MOUNT_FORM = re.compile(rf"^{SEGMENT}(/{SEGMENT})*$")
FOLDER_FORM = re.compile(rf"^({SEGMENT}/)*$")
NAMESPACE_FORM = re.compile(rf"^{SEGMENT}(/{SEGMENT})*/?$")
KEY_FORM = re.compile(rf"^{SEGMENT}/?$")


@dataclass(frozen=True)
class Config:
    target: str
    """The store's address, `https://vault.example:8200`; or a fake's."""
    mount: str = MOUNT
    """The mount of the KV version 2 engine."""
    folder: str = ""
    """The folder under the mount the walk starts in; empty for the mount's root."""
    namespace: str | None = None
    """The namespace every request names, where the store has namespaces."""
    timeout: float = 30.0


def folder_of(path: str) -> str:
    """A base path as the walk uses it: no leading slash, one trailing slash, or empty."""
    stripped = path.strip("/")
    return f"{stripped}/" if stripped else ""


def _moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC)


def _stamp(at: datetime | None) -> str | None:
    if at is None:
        return None
    return at.isoformat(timespec="seconds").replace("+00:00", "Z")


def secret(name: str, data: Any, now: datetime) -> Json:
    """What the metadata of one secret says, in the contract's shape; never a person."""
    if not isinstance(data, dict):
        raise TargetError("unexpected", "none", False, "a secret's metadata is not an object")
    created = _moment(data.get("created_time"))
    versions = data.get("versions")
    current = versions.get(str(data.get("current_version"))) if isinstance(versions, dict) else None
    changed = _moment(current.get("created_time")) if isinstance(current, dict) else None
    age = int((now - changed).total_seconds() // 86400) if changed else None
    return {
        "name": name,
        "created_at": _stamp(created),
        "changed_at": _stamp(changed),
        "age_days": age,
        "rotation": {"automatic": None, "period_days": None, "next_at": None},
        "expires_at": None,
        "last_accessed_at": None,
    }


class _Store:
    def __init__(self, config: Config, call: Call, client: httpx.AsyncClient) -> None:
        self.config = config
        self.call = call
        self.client = client

    async def get(self, path: str, listing: bool) -> Json | None:
        """The `data` of an answer, or None for a list without results or a vanished secret."""
        self.call.count()
        try:
            response = await self.client.get(path, params={"list": "true"} if listing else None)
        except httpx.TimeoutException as error:
            raise unavailable(
                f"the store did not answer in time: {type(error).__name__}"
            ) from error
        except httpx.HTTPError as error:
            # The type alone: an error's text can quote the request, the token among it.
            raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
        status = response.status_code
        if status == 200:
            try:
                body = response.json()
            except ValueError:
                body = None
            if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
                raise TargetError("unexpected", "none", False, "the answer is not the store's")
            data: Json = body["data"]
            return data
        if status == 404:
            if not listing:
                return None
            try:
                said = response.json().get("errors")
            except (ValueError, AttributeError):
                said = None
            if said == []:
                return None
            raise invalid("the store knows no such mount")
        if status == 401:
            raise TargetError(
                "unauthenticated", "none", False, "the store does not admit the token"
            )
        if status == 403:
            raise TargetError(
                "forbidden",
                "none",
                False,
                "the store refused: the token is not admitted or may not list this metadata",
            )
        if status == 400:
            raise invalid("the store refused the request")
        if status == 429 or status >= 500:
            raise unavailable(f"the store answered {status}")
        raise TargetError("unexpected", "none", False, f"the store answered {status}")


def _wanted(folder: str, prefix: str) -> bool:
    """Whether a folder can hold a name that starts with the prefix."""
    return folder.startswith(prefix) or prefix.startswith(folder)


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    prefix = input.get("prefix", "")
    if not isinstance(prefix, str) or len(prefix) > MAX_PREFIX:
        raise invalid(f"prefix must be a text of at most {MAX_PREFIX} characters")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    if MOUNT_FORM.match(config.mount) is None:
        raise invalid("the connector names no mount, or not one of path segments")
    base = folder_of(config.folder)
    if FOLDER_FORM.match(base) is None:
        raise invalid("the connector's folder is not a path of segments")
    headers = {"X-Vault-Token": call.token}
    if config.namespace:
        if NAMESPACE_FORM.match(config.namespace) is None:
            raise invalid("the connector's namespace is not a path of segments")
        headers["X-Vault-Namespace"] = config.namespace
    names: list[str] = []
    cut = False
    async with httpx.AsyncClient(
        base_url=f"{config.target.rstrip('/')}/v1/{config.mount}/metadata/",
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        headers=headers,
    ) as client:
        store = _Store(config, call, client)
        pending: list[tuple[str, int]] = [(base, 0)]
        lists = 0
        while pending:
            folder, depth = pending.pop(0)
            if lists >= MAX_FOLDERS:
                cut = True
                break
            lists += 1
            data = await store.get(folder, listing=True)
            keys = data.get("keys", []) if data is not None else []
            if not isinstance(keys, list):
                raise TargetError("unexpected", "none", False, "a list answer holds no keys")
            for key in keys:
                if not isinstance(key, str) or KEY_FORM.match(key) is None:
                    raise TargetError("unexpected", "none", False, "a key is not one path segment")
                path = folder + key
                if key.endswith("/"):
                    if not _wanted(path, prefix):
                        continue
                    if depth + 1 >= MAX_DEPTH:
                        cut = True
                    else:
                        pending.append((path, depth + 1))
                elif path.startswith(prefix):
                    names.append(path)
        if len(names) > MAX_SECRETS:
            names, cut = sorted(names)[:MAX_SECRETS], True
        now = datetime.now(UTC)
        secrets: list[Json] = []
        for name in sorted(names):
            data = await store.get(name, listing=False)
            if data is not None:
                secrets.append(secret(name, data, now))
    # The oldest change first; a secret whose change the store does not state last.
    secrets.sort(key=lambda s: (s["age_days"] is None, -(s["age_days"] or 0), s["name"]))
    output = {
        "secrets": secrets[:limit],
        "complete": not cut and len(secrets) <= limit,
        "read_at": _stamp(now),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"secrets.metadata.list": list_}
