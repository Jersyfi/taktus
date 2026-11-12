"""How the secrets' metadata is asked and read: `secrets.metadata.list`. Never a value.

The secret API lists a project's secrets at `GET /v1/projects/<project>/secrets`, newest
created first, with `pageSize`, `pageToken` and a `filter`. For each secret the connector asks
`GET /v1/projects/<project>/secrets/<id>/versions` with `filter=state:ENABLED` and
`pageSize=1`: the versions are listed newest first, so the one answered is the version whose
value is current. The connector never calls `.../versions/<version>:access`, the one method
that answers a value, nor any method that changes a secret.

A `prefix` is sent to the API as `name:<prefix>`, which the API matches as a case-insensitive
part of the name; the connector then keeps only the secrets whose identifier starts with the
prefix exactly. A prefix is letters, digits, `_` and `-`, as a secret's identifier is, so that
nothing else reaches the filter.

What each field is read from:

| Field | From |
|---|---|
| `name` | the secret's identifier, the last part of its resource name |
| `created_at` | the secret's `createTime` |
| `changed_at` | the `createTime` of its newest enabled version; null when none is enabled |
| `rotation.automatic` | true when a rotation schedule is attached, false when none is |
| `rotation.period_days` | the schedule's `rotationPeriod` in whole days; usually null, as the |
| | API documents that field as input only |
| `rotation.next_at` | the schedule's `nextRotationTime` |
| `expires_at` | the secret's `expireTime` |
| `last_accessed_at` | always null: the API records no access time |

The list is ordered by `age_days`, largest first; a secret with no enabled version comes last.

A rotation schedule of this store only notifies at `nextRotationTime`; whatever replaces the
value is elsewhere. `automatic` says that the schedule exists, not that the store rotates.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from taktus_connectors.gcp.api import FULL, Config, bearer, instant, project, request, stamp
from taktus_connectors.gcp.api import utc_text as _utc
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

LIMIT = 100
MAX_LIMIT = 500
PAGE = 100
MAX_PAGES = 10
PREFIX = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
DURATION = re.compile(r"^(\d+)(?:\.\d+)?s$")


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _period_days(text: Any) -> int | None:
    found = DURATION.match(text) if isinstance(text, str) else None
    return int(found.group(1)) // 86400 if found else None


def _secret(item: Any, changed: Any, now: datetime) -> Json:
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        raise TargetError("unexpected", "none", False, "a secret has no name")
    rotation = item.get("rotation")
    changed_at = instant(changed)
    age = None if changed_at is None else max(0, (now - changed_at).days)
    return {
        "name": item["name"].rsplit("/", 1)[-1],
        "created_at": _utc(item.get("createTime")),
        "changed_at": stamp(changed_at) if changed_at is not None else None,
        "age_days": age,
        "rotation": {
            "automatic": isinstance(rotation, dict) and bool(rotation.get("nextRotationTime")),
            "period_days": (
                _period_days(rotation.get("rotationPeriod")) if isinstance(rotation, dict) else None
            ),
            "next_at": _utc(rotation.get("nextRotationTime"))
            if isinstance(rotation, dict)
            else None,
        },
        "expires_at": _utc(item.get("expireTime")),
        "last_accessed_at": None,
    }


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    prefix = input.get("prefix")
    if prefix is not None and (not isinstance(prefix, str) or PREFIX.match(prefix) is None):
        raise invalid("prefix must be letters, digits, `_` and `-`, as a secret's identifier is")
    limit = _limit(input)
    base = f"{config.secrets}/v1/projects/{project(config)}/secrets"
    token = await bearer(config, call, FULL)
    found: list[Json] = []
    following: Any = None
    for _ in range(MAX_PAGES):
        params: Json = {"pageSize": PAGE}
        if prefix:
            params["filter"] = f"name:{prefix}"
        if following:
            params["pageToken"] = following
        page = await request(config, call, token, "GET", base, params=params)
        items = page.get("secrets") or []
        if not isinstance(items, list):
            raise TargetError("unexpected", "none", False, "the answer's secrets are not a list")
        for item in items:
            name = item.get("name") if isinstance(item, dict) else None
            if not isinstance(name, str):
                raise TargetError("unexpected", "none", False, "a secret has no name")
            if prefix and not name.rsplit("/", 1)[-1].startswith(prefix):
                continue
            found.append(item)
        following = page.get("nextPageToken")
        if not following or len(found) >= limit:
            break
    complete = not following and len(found) <= limit
    now = datetime.now(UTC)
    secrets: list[Json] = []
    for item in found[:limit]:
        id = item["name"].rsplit("/", 1)[-1]
        if PREFIX.match(id) is None:
            raise TargetError("unexpected", "none", False, "a secret's name is not an identifier")
        versions = await request(
            config,
            call,
            token,
            "GET",
            f"{base}/{id}/versions",
            params={"filter": "state:ENABLED", "pageSize": 1},
        )
        newest = versions.get("versions") or []
        changed = newest[0].get("createTime") if newest and isinstance(newest[0], dict) else None
        secrets.append(_secret(item, changed, now))
    secrets.sort(key=lambda s: (s["age_days"] is None, -(s["age_days"] or 0), s["name"]))
    output = {
        "secrets": secrets,
        "complete": complete,
        "read_at": stamp(now.replace(microsecond=0)),
    }
    return Outcome(output=output, effect={"kind": "read"})
