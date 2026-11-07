"""How the administrators' activities are asked and their answer read.

The Admin SDK's Reports API lists activities at
`GET /admin/reports/v1/activity/users/all/applications/<application>`, with `startTime` (RFC
3339), `maxResults` (default 1000) and `pageToken`, the `nextPageToken` of the page before. The
answer is `{"kind": "reports#activities", "items": [...], "nextPageToken": ...}`; each activity
names its `id` (`time`, `uniqueQualifier`, `applicationName`, `customerId`), its `actor`
(`email`, `profileId`, `callerType`) and its `events`, each a `type`, a `name` and
`parameters`. The connector pages on while a next page token is given, up to 100 pages.

The API is reached with an access token of a service account that acts for an administrator
(domain-wide delegation). The requesting identity's credential is the service account's key
file, as the service hands it out: JSON with `client_email` and `private_key`. At every call the
connector signs an assertion with the key (RS256: `iss` the service account, `sub` the
administrator configured, `scope` `admin.reports.audit.readonly`, `aud` the token endpoint, valid
for an hour) and exchanges it at the configured token endpoint
(`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`). The key file's own `token_uri` is
never followed: a key could otherwise send a signed assertion elsewhere. Neither the key nor the
access token is kept after the call.

Each event of an activity becomes one event of the capability: its identifier (the activity's
`uniqueQualifier` and the event's position), when it happened and its hour in UTC, the event's
`name` as `action`, the actor's address or profile id, what it acted on (the parameter
`USER_EMAIL`, `ROLE_NAME` or `GROUP_EMAIL`), and `escalation`: whether it is one of the
documented events of the type `DELEGATED_ADMIN_SETTINGS` that grant rights. The IP address and
every other parameter are never copied. The actor is kept for the person who investigates; no
rule counts by it (principle 14, ADR-0015). `actions` counts per action, never per actor.

| Answer | Cause |
|---|---|
| the key file is not a service account's key, or its key does not sign | `unauthenticated` |
| the token endpoint refuses the assertion (400, 401) | `unauthenticated` |
| 400, 404: a request the API refuses, an application it does not know | `invalid` |
| 401 | `unauthenticated` |
| 403: the administrator may not read reports, or the scope is not delegated | `forbidden` |
| 429, 5xx, a refused or timed-out connection, at either endpoint | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The service's own messages stay out of `detail`.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://admin.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — an address, not a secret
SCOPE = "https://www.googleapis.com/auth/admin.reports.audit.readonly"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
APPLICATIONS = ("admin", "login", "token", "saml", "groups", "user_accounts")
"""The applications whose activities a review of privileged actions reads."""
HOURS = 24
MAX_HOURS = 4320
"""180 days: the longest period the reports answer."""
LIMIT = 1000
MAX_LIMIT = 10_000
PAGE = 1000
MAX_PAGES = 100
ESCALATION = frozenset({"ASSIGN_ROLE", "CREATE_ROLE", "ADD_PRIVILEGE", "UPDATE_ROLE"})
"""The events of the type `DELEGATED_ADMIN_SETTINGS` that grant rights (`README.md`)."""
ESCALATION_TYPE = "DELEGATED_ADMIN_SETTINGS"
TARGETS = ("USER_EMAIL", "ROLE_NAME", "GROUP_EMAIL")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the service's own, or a fake's."""
    subject: str = ""
    """The administrator the service account acts for."""
    token_url: str = TOKEN_URL
    """Where an assertion is exchanged for an access token."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _unauthenticated(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def _whole(input: Json, name: str, default: int, most: int) -> int:
    value = input.get(name, default)
    if isinstance(value, str) and value.isdigit():
        value = int(value)  # as a command line gives it
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= most:
        raise invalid(f"{name} must be a whole number from 1 to {most}")
    return value


def _client(config: Config) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
    )


def _assertion(config: Config, credential: str) -> str:
    try:
        key = json.loads(credential)
    except ValueError:
        key = None
    if (
        not isinstance(key, dict)
        or not isinstance(key.get("client_email"), str)
        or not isinstance(key.get("private_key"), str)
    ):
        raise _unauthenticated("the credential is not a service account's key file")
    now = int(time.time())
    claims = {
        "iss": key["client_email"],
        "sub": config.subject,
        "scope": SCOPE,
        "aud": config.token_url,
        "iat": now,
        "exp": now + 3600,
    }
    try:
        return jwt.encode(claims, key["private_key"], algorithm="RS256")
    except (ValueError, TypeError, jwt.PyJWTError):
        # Never the error's text: it can quote the key.
        raise _unauthenticated("the service account's key does not sign") from None


async def _access_token(config: Config, call: Call) -> str:
    assertion = _assertion(config, call.token)
    call.count()
    try:
        async with _client(config) as client:
            response = await client.post(
                config.token_url, data={"grant_type": GRANT, "assertion": assertion}
            )
    except httpx.TimeoutException as error:
        raise unavailable(
            f"the token endpoint did not answer in time: {type(error).__name__}"
        ) from error
    except httpx.HTTPError as error:
        raise unavailable(
            f"the token endpoint could not be reached: {type(error).__name__}"
        ) from error
    status = response.status_code
    if status in (400, 401, 403):
        raise _unauthenticated("the token endpoint refused the service account's assertion")
    if status == 429 or status >= 500:
        raise unavailable(f"the token endpoint answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    token = body.get("access_token") if isinstance(body, dict) and status == 200 else None
    if not isinstance(token, str) or not token:
        raise _unexpected(f"the token endpoint answered {status} without an access token")
    return token


async def _get(config: Config, call: Call, token: str, path: str, params: Json) -> Json:
    call.count()
    try:
        async with _client(config) as client:
            response = await client.get(
                config.target.rstrip("/") + path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as error:
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or body.get("kind") != "reports#activities":
            raise _unexpected("the API answered with a body that is not a list of activities")
        return body
    if status == 401:
        raise _unauthenticated("the API does not admit the access token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the administrator may not read reports")
    if status in (400, 404):
        raise invalid(f"the API refused the request: {status}")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}")


def _stamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise _unexpected("an activity has no time")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _unexpected("an activity's time is not RFC 3339") from None
    return at.astimezone(UTC) if at.tzinfo else at.replace(tzinfo=UTC)


def _target(parameters: Any) -> str | None:
    if not isinstance(parameters, list):
        return None
    given = {
        p.get("name"): p.get("value")
        for p in parameters
        if isinstance(p, dict) and isinstance(p.get("value"), str)
    }
    return next((given[name] for name in TARGETS if name in given), None)


def events_of(activity: Any) -> list[Json]:
    if not isinstance(activity, dict) or not isinstance(activity.get("id"), dict):
        raise _unexpected("an activity has no id")
    identifier = activity["id"]
    at = _stamp(identifier.get("time"))
    given = activity.get("actor")
    actor: Json = given if isinstance(given, dict) else {}
    who = actor.get("email") or actor.get("profileId")
    found = []
    for index, item in enumerate(activity.get("events") or []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise _unexpected("an event of an activity has no name")
        found.append(
            {
                "id": f"{identifier.get('uniqueQualifier')}:{index}",
                "at": at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "hour": at.hour,
                "action": item["name"],
                "actor": who if isinstance(who, str) else None,
                "target": _target(item.get("parameters")),
                "escalation": item.get("type") == ESCALATION_TYPE and item["name"] in ESCALATION,
            }
        )
    return found


def actions(events: list[Json]) -> list[Json]:
    """How many events of each action, most first: never a count per actor."""
    counted = Counter(e["action"] for e in events)
    return [
        {"action": action, "count": count}
        for action, count in sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    if not config.subject:
        raise invalid("the connector names no administrator to act for")
    hours = _whole(input, "hours", HOURS, MAX_HOURS)
    limit = _whole(input, "limit", LIMIT, MAX_LIMIT)
    application = input.get("application", "admin")
    if application not in APPLICATIONS:
        raise invalid(f"application must be one of {', '.join(APPLICATIONS)}")
    since = datetime.now(UTC) - timedelta(hours=hours)
    start = since.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    token = await _access_token(config, call)
    path = f"/admin/reports/v1/activity/users/all/applications/{application}"
    read: list[Json] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES):
        params: Json = {"startTime": start, "maxResults": min(PAGE, limit)}
        if page_token:
            params["pageToken"] = page_token
        page = await _get(config, call, token, path, params)
        items = page.get("items", [])
        if not isinstance(items, list):
            raise _unexpected("the activities are not a list")
        for activity in items:
            read.extend(events_of(activity))
        given = page.get("nextPageToken")
        page_token = given if isinstance(given, str) and given else None
        if page_token is None or len(read) >= limit:
            break
    events = read[:limit]
    output = {
        "events": events,
        "actions": actions(events),
        "complete": page_token is None and len(read) <= limit,
        "since": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"audit.events.list": list_}
