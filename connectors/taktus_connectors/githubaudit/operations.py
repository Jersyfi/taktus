"""How the organisation's audit log is asked and its answer read.

The REST API lists an organisation's audit log at `GET /orgs/<org>/audit-log`, newest first,
with `phrase` (the audit log's search), `include` (`web`, `git` or `all`; `web` by default),
`order` and `per_page` (at most 100). The next page is named by the `Link` header: the URL with
`rel="next"` carries the cursor `after`. The connector asks for the events since a moment with
the search qualifier `created:>=<time>`, pages on while a next link is given, up to 100 pages,
and sends the requesting identity's token as a bearer token with the API version pinned.

Each event is reduced to what a rule over privileged actions reads: its identifier
(`_document_id`), when it happened (`@timestamp`, milliseconds since the epoch), its hour in
UTC, its `action`, the account that acted (`actor`), what it acted on, and `escalation`: whether
the action is one of those that grant rights, as the audit log's documentation names them. The
actor's location, the IP address and every other field are never copied. The actor is kept for
the person who investigates; no rule counts by it (principle 14, ADR-0015). `actions` counts the
events per action, never per actor.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: a refused search; an organisation unknown, or without an audit log | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403 with no rate limit left, 429, 5xx, no connection or no answer | `unavailable`, retryable |
| 403 otherwise: not an organisation owner, or no `read:audit_log` | `forbidden` |
| any other status, a body that is not a list of events | `unexpected` |

The API's own message stays out of `detail`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.github.com"
API_VERSION = "2022-11-28"
HOURS = 24
MAX_HOURS = 2160
"""Ninety days: the audit log answers the past three months by default."""
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 100
MAX_PAGES = 100
SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
ESCALATION = frozenset(
    {
        "org.add_member",
        "org.invite_member",
        "org.add_outside_collaborator",
        "org.restore_member",
        "org.add_billing_manager",
        "org.integration_manager_added",
        "integration.manager_added",
        "integration_installation.create",
        "integration_installation.repositories_added",
        "org.oauth_app_access_approved",
        "org.disable_two_factor_requirement",
        "auto_approve_personal_access_token_requests.enable",
    }
)
"""The actions that grant rights or lower a guard, by the names of the organisation audit log's
documentation (`README.md`)."""


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the service's own, or a fake's."""
    organization: str = ""
    """The organisation whose audit log is read."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _whole(input: Json, name: str, default: int, most: int) -> int:
    value = input.get(name, default)
    if isinstance(value, str) and value.isdigit():
        value = int(value)  # as a command line gives it
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= most:
        raise invalid(f"{name} must be a whole number from 1 to {most}")
    return value


async def _get(config: Config, call: Call, path: str, params: Json) -> httpx.Response:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={
                "Authorization": f"Bearer {call.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
        ) as client:
            response = await client.get(path, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        return response
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the token")
    if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise unavailable("the API's rate limit is spent")
    if status == 403:
        raise TargetError(
            "forbidden", "none", False, "the token may not read the organisation's audit log"
        )
    if status in (400, 404, 422):
        raise invalid(f"the API refused the request: {status}")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}")


def _target(item: Json) -> str | None:
    for field in ("user", "team", "repo", "target_login", "name"):
        value = item.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def event(item: Any) -> Json:
    if not isinstance(item, dict) or not isinstance(item.get("action"), str):
        raise _unexpected("an event has no action")
    stamp = item.get("@timestamp", item.get("created_at"))
    if isinstance(stamp, bool) or not isinstance(stamp, int):
        raise _unexpected("an event has no time")
    at = datetime.fromtimestamp(stamp / 1000, UTC)
    identifier = item.get("_document_id")
    return {
        "id": identifier if isinstance(identifier, str) else f"{stamp}:{item['action']}",
        "at": at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "hour": at.hour,
        "action": item["action"],
        "actor": item.get("actor") if isinstance(item.get("actor"), str) else None,
        "target": _target(item),
        "escalation": item["action"] in ESCALATION,
    }


def actions(events: list[Json]) -> list[Json]:
    """How many events of each action, most first: never a count per actor."""
    counted = Counter(e["action"] for e in events)
    return [
        {"action": action, "count": count}
        for action, count in sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    if SLUG.match(config.organization) is None:
        raise invalid("the connector names no organisation, or not one login")
    hours = _whole(input, "hours", HOURS, MAX_HOURS)
    limit = _whole(input, "limit", LIMIT, MAX_LIMIT)
    since = datetime.now(UTC) - timedelta(hours=hours)
    stamp = since.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    path = f"/orgs/{config.organization}/audit-log"
    read: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {
            "phrase": f"created:>={stamp}",
            "include": "web",
            "order": "desc",
            "per_page": PAGE,
        }
        if after is not None:
            params["after"] = after
        response = await _get(config, call, path, params)
        try:
            page = response.json()
        except ValueError:
            page = None
        if not isinstance(page, list):
            raise _unexpected("the answer is not a list of events")
        read.extend(event(item) for item in page)
        found = NEXT.search(response.headers.get("link", ""))
        cursor = parse_qs(urlparse(found.group(1)).query).get("after", [""])[0] if found else ""
        after = cursor or None
        more = after is not None and bool(page)
        if not more or len(read) >= limit:
            break
    events = read[:limit]
    output = {
        "events": events,
        "actions": actions(events),
        "complete": not more and len(read) <= limit,
        "since": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"audit.events.list": list_}
