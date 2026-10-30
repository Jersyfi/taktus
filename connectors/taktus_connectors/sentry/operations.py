"""How the issues are asked and their answer read.

The API lists an organisation's issues at `GET /api/0/organizations/<org>/issues/`, with the
query, the period (`statsPeriod`), the order (`sort`), a page size (`limit`, at most 100) and a
`cursor`. The next page is named by the `Link` header: the part with `rel="next"` and
`results="true"` carries its `cursor`. One issue is
`GET /api/0/organizations/<org>/issues/<id>/`. The requesting identity's token is sent as a
bearer token.

Each issue is normalised to the fields a process judges by. A field that names a person — the
assignee, who resolved it, who saw it — is never copied: no figure here may assess a named
person (principle 14). The event count, which the API gives as text, becomes a whole number.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: the query or a parameter is refused | `invalid` |
| 404: the organisation or the issue is unknown | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own `detail` stays out of the error's `detail`: it can quote the query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus.adapters.driven.connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://sentry.io"
LIMIT = 100
"""How many issues a list reports when the call names no `limit`."""
MAX_LIMIT = 1000
PAGE = 100
"""The most issues the API answers in one page."""
MAX_PAGES = 10
SORTS = ("freq", "new", "date", "user")
PERIOD = re.compile(r"^\d{1,3}[mhdw]$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
ID = re.compile(r"^\d{1,20}$")
NEXT = re.compile(r'rel="next";\s*results="true";\s*cursor="([^"]+)"')


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    organization: str = ""
    """The slug of the organisation whose issues are read."""
    timeout: float = 30.0


def _text(input: Json, name: str, default: str, limit: int = 1000) -> str:
    value = input.get(name, default)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise invalid(f"{name} must be a text of at most {limit} characters")
    return value


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _whole(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def issue(item: Any) -> Json:
    """The fields a process judges an issue by; never a person."""
    if not isinstance(item, dict) or not isinstance(item.get("id"), str | int):
        raise TargetError("unexpected", "none", False, "an issue has no identifier")
    project = item.get("project")
    return {
        "id": str(item["id"]),
        "short_id": item.get("shortId"),
        "title": item.get("title"),
        "culprit": item.get("culprit"),
        "level": item.get("level"),
        "status": item.get("status"),
        "project": project.get("slug") if isinstance(project, dict) else None,
        "count": _whole(item.get("count")),
        "users": _whole(item.get("userCount")),
        "first_seen": item.get("firstSeen"),
        "last_seen": item.get("lastSeen"),
        "permalink": item.get("permalink"),
    }


async def _get(config: Config, call: Call, path: str, params: Json) -> httpx.Response:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.get(path, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        return response
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read these issues")
    if status == 404:
        raise invalid("the provider knows no such organisation or issue")
    if status == 400:
        raise invalid("the provider refused the query")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status}")
    raise TargetError("unexpected", "none", False, f"the provider answered {status}")


def _organization(config: Config) -> str:
    if SLUG.match(config.organization) is None:
        raise invalid("the connector names no organisation, or not one slug")
    return config.organization


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    query = _text(input, "query", "is:unresolved")
    period = _text(input, "period", "24h")
    if PERIOD.match(period) is None:
        raise invalid("period must be a number and one of m, h, d, w: `24h`, `14d`")
    sort = input.get("sort", "freq")
    if sort not in SORTS:
        raise invalid(f"sort must be one of {', '.join(SORTS)}")
    project = input.get("project")
    if project is not None:
        if not isinstance(project, str) or SLUG.match(project) is None:
            raise invalid("project must be a project's slug")
        query = f"{query} project:{project}"
    limit = _limit(input)
    path = f"/api/0/organizations/{_organization(config)}/issues/"
    issues: list[Json] = []
    cursor: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {
            "query": query,
            "statsPeriod": period,
            "sort": sort,
            "limit": min(PAGE, limit - len(issues)),
        }
        if cursor:
            params["cursor"] = cursor
        response = await _get(config, call, path, params)
        try:
            page = response.json()
        except ValueError:
            page = None
        if not isinstance(page, list):
            raise TargetError("unexpected", "none", False, "the answer is not a list of issues")
        issues.extend(issue(item) for item in page)
        found = NEXT.search(response.headers.get("link", ""))
        cursor = found.group(1) if found else None
        more = cursor is not None
        if not more or len(issues) >= limit:
            break
    output = {"issues": issues[:limit], "complete": not more and len(issues) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    id = input.get("id")
    if isinstance(id, int) and not isinstance(id, bool):
        id = str(id)
    if not isinstance(id, str) or ID.match(id) is None:
        raise invalid("id must be an issue's numeric identifier")
    path = f"/api/0/organizations/{_organization(config)}/issues/{id}/"
    response = await _get(config, call, path, {})
    try:
        body = response.json()
    except ValueError:
        body = None
    return Outcome(output=issue(body), effect={"kind": "read"})


OPERATIONS = {"errors.issues.list": list_, "errors.issues.read": read}
