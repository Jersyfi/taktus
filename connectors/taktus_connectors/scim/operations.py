"""How the directory's resources are asked and their answer read.

SCIM 2.0 (RFC 7644 §3.4.2) lists resources at `GET /Users` and `GET /Groups`. A list is
answered as `urn:ietf:params:scim:api:messages:2.0:ListResponse` with `totalResults`,
`itemsPerPage`, `startIndex` and `Resources`. Paging is by index (§3.4.2.4): `startIndex`
counts from 1 and `count` asks for at most that many; the connector asks for pages of 100 and
reads on while the index has not passed `totalResults`, up to 100 pages. A filter (§3.4.2.2)
narrows the groups to a display name, `displayName eq "<name>"`. `attributes` (§3.4.2.5) asks
the service for only the attributes a review needs. The requesting identity's token is sent as
a bearer token (§2).

Each account is reduced to what an access review reads (RFC 7643 §4.1): `id`, `userName`,
`userType`, `active`, the display names of its `groups`, the values of its `roles` and
`entitlements`, and `meta.lastModified`. Its name, e-mail addresses, phone numbers, addresses
and photos are never copied: no review needs them, and what is not read cannot leak. SCIM's
core schema has no last sign-in. Whether an account is in use can only be read from `active`,
and from when it last changed; the README says so.

How the service's answers map to the contract's causes (RFC 7644 §3.12):

| Answer | Cause |
|---|---|
| 400 (`invalidFilter`, `tooMany`, …), 404, 501: refused, or not served | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token may not read these resources | `forbidden` |
| 429, 5xx but 501, no connection or no answer | `unavailable`, retryable |
| any other status, a body that is not a ListResponse | `unexpected` |

The service's own `detail` stays out of the error's `detail`: only its `scimType` is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

LIST_RESPONSE = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 100
MAX_PAGES = 100
NAME = re.compile(r'^[^"\\\x00-\x1f]{1,256}$')
"""A display name the filter can quote: no quotation mark, no backslash, no control character."""
USER_ATTRIBUTES = "userName,userType,active,groups,roles,entitlements,meta"
GROUP_ATTRIBUTES = "displayName,members"


@dataclass(frozen=True)
class Config:
    target: str = ""
    """The SCIM service's base address, under which `/Users` and `/Groups` are found."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _kind(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    kind = body.get("scimType") if isinstance(body, dict) else None
    return kind if isinstance(kind, str) and re.fullmatch(r"[A-Za-z]{1,40}", kind) else ""


async def _get(config: Config, call: Call, path: str, params: Json) -> Json:
    if not config.target:
        raise invalid("the connector names no SCIM service")
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={
                "Authorization": f"Bearer {call.token}",
                "Accept": "application/scim+json",
            },
        ) as client:
            response = await client.get(path, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the service did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the service could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or LIST_RESPONSE not in (body.get("schemas") or []):
            raise _unexpected("the service answered with a body that is not a ListResponse")
        return body
    kind = _kind(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the service does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token may not read the directory")
    if status in (400, 404, 501):
        raise invalid(f"the service refused the request: {status} {kind}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the service answered {status}")
    raise _unexpected(f"the service answered {status} {kind}".rstrip())


async def _resources(
    config: Config, call: Call, path: str, params: Json, limit: int
) -> tuple[list[Json], bool]:
    """Every resource of a list, page by page, up to `limit`; and whether every one was read."""
    read: list[Json] = []
    index = 1
    total = 0
    for _ in range(MAX_PAGES):
        page = await _get(
            config,
            call,
            path,
            {**params, "startIndex": index, "count": min(PAGE, limit - len(read))},
        )
        resources = page.get("Resources", [])
        given = page.get("totalResults")
        if not isinstance(resources, list) or not isinstance(given, int) or isinstance(given, bool):
            raise _unexpected("the ListResponse has no Resources or no totalResults")
        total = given
        if not all(isinstance(r, dict) for r in resources):
            raise _unexpected("a resource is not an object")
        read.extend(resources)
        index += len(resources)
        if not resources or index > total or len(read) >= limit:
            break
    return read[:limit], len(read) >= total


def _values(items: Any, field: str) -> list[str]:
    """The texts of a multi-valued attribute (RFC 7643 §2.4): each element's `field`."""
    if not isinstance(items, list):
        return []
    found = []
    for item in items:
        value = item.get(field) if isinstance(item, dict) else None
        if isinstance(value, str):
            found.append(value)
    return found


def account(resource: Json) -> Json:
    """The fields an access review reads; never a name, an address or a number."""
    if not isinstance(resource.get("id"), str):
        raise _unexpected("an account has no identifier")
    given = resource.get("meta")
    meta: Json = given if isinstance(given, dict) else {}
    groups = resource.get("groups")
    return {
        "id": resource["id"],
        "user_name": resource.get("userName")
        if isinstance(resource.get("userName"), str)
        else None,
        "user_type": resource.get("userType")
        if isinstance(resource.get("userType"), str)
        else None,
        # RFC 7643 §4.1.1: absent `active` says nothing; only false is inactive.
        "active": resource.get("active") is not False,
        "groups": _values(groups, "display") or _values(groups, "value"),
        "roles": _values(resource.get("roles"), "value"),
        "entitlements": _values(resource.get("entitlements"), "value"),
        "last_modified": meta.get("lastModified"),
    }


def group(resource: Json) -> Json:
    if not isinstance(resource.get("id"), str):
        raise _unexpected("a group has no identifier")
    members = _values(resource.get("members"), "value")
    return {
        "id": resource["id"],
        "display_name": resource.get("displayName"),
        "members": members,
        "member_count": len(members),
    }


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _name(input: Json, field: str) -> str | None:
    value = input.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or NAME.match(value) is None:
        raise invalid(f"{field} must be a display name without quotation marks or backslashes")
    return value


async def _groups_named(config: Config, call: Call, name: str) -> tuple[list[Json], bool]:
    params = {"filter": f'displayName eq "{name}"', "attributes": GROUP_ATTRIBUTES}
    found, complete = await _resources(config, call, "/Groups", params, MAX_LIMIT)
    return [group(r) for r in found], complete


async def accounts(config: Config, call: Call, input: Json) -> Outcome:
    limit = _limit(input)
    name = _name(input, "group")
    members: set[str] | None = None
    complete = True
    if name is not None:
        groups, complete = await _groups_named(config, call, name)
        if not groups:
            raise invalid("the directory holds no group of that display name")
        members = {m for g in groups for m in g["members"]}
    resources, read_all = await _resources(
        config, call, "/Users", {"attributes": USER_ATTRIBUTES}, MAX_LIMIT if members else limit
    )
    listed = [account(r) for r in resources]
    if members is not None:
        listed = [a for a in listed if a["id"] in members]
    output = {
        "accounts": listed[:limit],
        "complete": complete and read_all and len(listed) <= limit,
    }
    return Outcome(output=output, effect={"kind": "read"})


async def groups(config: Config, call: Call, input: Json) -> Outcome:
    limit = _limit(input)
    name = _name(input, "name")
    if name is not None:
        found, complete = await _groups_named(config, call, name)
    else:
        resources, complete = await _resources(
            config, call, "/Groups", {"attributes": GROUP_ATTRIBUTES}, limit
        )
        found = [group(r) for r in resources]
    output = {"groups": found[:limit], "complete": complete and len(found) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"directory.accounts.list": accounts, "directory.groups.list": groups}
