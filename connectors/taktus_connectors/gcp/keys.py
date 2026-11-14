"""The expiry of the project's service account keys: `expiry.credentials.list` (ADR-0337).

The identity API lists the project's service accounts,
`GET /v1/projects/<project>/serviceAccounts`, page by page, and for each its keys,
`GET /v1/projects/<project>/serviceAccounts/<account>/keys?keyTypes=USER_MANAGED`. Only keys a
person created and must rotate are asked: a system-managed key is rotated by the provider. A key
is reported in the shape the signing credentials of `expiry.credentials` have:

| Field | From |
|---|---|
| `kind` | `key` |
| `id` | the last part of the key's `name` |
| `name` | the service account's address, the part of the key's `name` before `/keys/` |
| `type` | `keyType` |
| `platform` | null |
| `state` | `DISABLED` where `disabled` is true, with `disableReason`; `ENABLED` otherwise |
| `expires_at` | `validBeforeTime`, in RFC 3339 UTC |
| `days_left` | whole days from `read_at` to `expires_at`, rounded down; negative once expired |

A key created without an expiry is answered with a `validBeforeTime` far in the future, and is
reported so: it never comes first. No key material is requested: the list answers none, and the
method that creates a key is never called. A service account's display name is not read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from taktus_connectors.gcp.api import FULL, Config, bearer, instant, project, request, stamp
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

LIMIT = 200
MAX_LIMIT = 1000
MAX_PAGES = 10
PAGE = 100


def _key(entry: Any, now: datetime) -> Json | None:
    name = entry.get("name") if isinstance(entry, dict) else None
    if not isinstance(name, str) or "/keys/" not in name:
        raise TargetError("unexpected", "none", False, "a key names no resource name")
    expires = instant(entry.get("validBeforeTime"))
    if expires is None:
        return None
    account_path, _, identifier = name.partition("/keys/")
    disabled = entry.get("disabled") is True
    reason = entry.get("disableReason")
    state = "DISABLED" if disabled else "ENABLED"
    if disabled and isinstance(reason, str) and reason:
        state = f"DISABLED:{reason}"
    at = stamp(expires)
    return {
        "kind": "key",
        "id": identifier,
        "name": account_path.rsplit("/", 1)[-1],
        "type": str(entry.get("keyType") or ""),
        "platform": None,
        "state": state,
        "expires_at": at,
        "days_left": int((expires - now).total_seconds() // 86400),
        "key": f"credential:key:{identifier}:{at}",
    }


async def list_keys(config: Config, call: Call, input: Json) -> Outcome:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    kinds = input.get("kinds")
    if kinds is not None and (not isinstance(kinds, list) or set(kinds) - {"key"}):
        raise invalid("kinds names only `key` here: a project holds service account keys")
    home = project(config)
    base = f"{config.iam}/v1/projects/{home}/serviceAccounts"
    token = await bearer(config, call, FULL)
    now = datetime.now(UTC)
    accounts: list[str] = []
    params: Json = {"pageSize": PAGE}
    complete = True
    for _ in range(MAX_PAGES):
        answer = await request(config, call, token, "GET", base, params=params)
        for account in answer.get("accounts") or []:
            email = account.get("email") if isinstance(account, dict) else None
            if not isinstance(email, str) or not email:
                raise TargetError("unexpected", "none", False, "an account names no address")
            accounts.append(email)
        following = answer.get("nextPageToken")
        if not following:
            break
        params = {**params, "pageToken": following}
    else:
        complete = False
    found: list[Json] = []
    for email in accounts:
        answer = await request(
            config,
            call,
            token,
            "GET",
            f"{base}/{quote(email, safe='@.')}/keys",
            params={"keyTypes": "USER_MANAGED"},
        )
        for entry in answer.get("keys") or []:
            key = _key(entry, now)
            if key is None:
                complete = False
            else:
                found.append(key)
    found.sort(key=lambda c: (c["days_left"], c["expires_at"], c["id"]))
    output = {
        "credentials": found[:limit],
        "complete": complete and len(found) <= limit,
        "read_at": stamp(now),
    }
    return Outcome(output=output, effect={"kind": "read"})
