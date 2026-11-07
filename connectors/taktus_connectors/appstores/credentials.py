"""How the signing certificates and provisioning profiles are listed and their expiry read
(`expiry.credentials`, ADR-0203). App Store Connect only: the Google Play Developer
API publishes no signing credential with an expiry, so the operation takes no `platform`.

Two endpoints of App Store Connect, under `--app-store-target`, are asked:

- `GET /v1/certificates` with `fields[certificates]=certificateType,serialNumber,platform,
  expirationDate`;
- `GET /v1/profiles` with `fields[profiles]=name,platform,profileType,profileState,
  expirationDate`.

Both take `limit`, at most 200. The sparse fieldsets name every attribute the connector
reads and no other: `certificateContent` and `profileContent`, the content itself, are never
requested and so never answered. Each answer's `links.next`, where present, is the next page;
it is followed only while it names the configured address, so the token goes nowhere else,
and at most `MAX_PAGES` times for each kind.

A certificate's `name` and `displayName` are not requested: a development certificate's name
is the name of the person it was issued to (principle 14). Its `name` here is its serial
number, which the API's certificate list shows beside it. A profile's `name` is the name its
team gave it, and is kept.

| Field | From |
|---|---|
| `type` | `certificateType` or `profileType` |
| `platform` | `platform`: `IOS`, `MAC_OS` or `UNIVERSAL` |
| `state` | a profile's `profileState`, `ACTIVE` or `INVALID`; null for a certificate |
| `expires_at` | `expirationDate`, in RFC 3339 UTC |
| `days_left` | whole days from `read_at` to `expires_at`, rounded down; negative once expired |

An entry without an `expirationDate` is not reported, and the answer is then not complete.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404 | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the key's role may not list these | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The API's own `errors` stay out of the error's `detail`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from taktus_connectors.appstores import auth
from taktus_connectors.appstores.config import Config
from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

LIMIT = 200
MAX_LIMIT = 1000
PAGE = 200
"""The most entries the API answers in one page."""
MAX_PAGES = 10


@dataclass(frozen=True)
class Kind:
    path: str
    fieldset: str
    fields: str
    type_attribute: str


KINDS: dict[str, Kind] = {
    "certificate": Kind(
        "/v1/certificates",
        "fields[certificates]",
        "certificateType,serialNumber,platform,expirationDate",
        "certificateType",
    ),
    "profile": Kind(
        "/v1/profiles",
        "fields[profiles]",
        "name,platform,profileType,profileState,expirationDate",
        "profileType",
    ),
}


def _moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(UTC)


def _stamp(at: datetime) -> str:
    return at.isoformat(timespec="seconds").replace("+00:00", "Z")


def entry(kind: str, item: Any, now: datetime) -> Json | None:
    """One certificate or profile in the contract's shape, or None without an expiry."""
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise TargetError("unexpected", "none", False, f"a {kind} has no identifier")
    attributes = item.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    expires = _moment(attributes.get("expirationDate"))
    if expires is None:
        return None
    at = _stamp(expires)
    if kind == "certificate":
        name = attributes.get("serialNumber")
        state = None
    else:
        name = attributes.get("name")
        state = attributes.get("profileState")
    return {
        "kind": kind,
        "id": item["id"],
        "name": name if isinstance(name, str) else item["id"],
        "type": str(attributes.get(KINDS[kind].type_attribute) or ""),
        "platform": attributes.get("platform"),
        "state": state,
        "expires_at": at,
        "days_left": int((expires - now).total_seconds() // 86400),
        "key": f"credential:{kind}:{item['id']}:{at}",
    }


async def _get(
    client: httpx.AsyncClient, call: Call, url: str, params: Json | None
) -> httpx.Response:
    call.count()
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        return response
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not list these")
    if status in (400, 404):
        raise invalid("the provider refused the request")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status}")
    raise TargetError("unexpected", "none", False, f"the provider answered {status}")


def _kinds(input: Json) -> list[str]:
    kinds = input.get("kinds", list(KINDS))
    if (
        not isinstance(kinds, list)
        or not kinds
        or any(not isinstance(k, str) or k not in KINDS for k in kinds)
    ):
        raise invalid("kinds must be a list of `certificate` and `profile`")
    return [k for k in KINDS if k in kinds]


async def list_credentials(config: Config, call: Call, input: Json) -> Outcome:
    kinds = _kinds(input)
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    signed = auth.app_store_token(call)
    base = config.app_store_target.rstrip("/")
    found: list[Json] = []
    complete = True
    now = datetime.now(UTC)
    async with httpx.AsyncClient(
        base_url=base,
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        headers={"Authorization": f"Bearer {signed}"},
    ) as client:
        for kind in kinds:
            spec = KINDS[kind]
            url: str | None = spec.path
            params: Json | None = {spec.fieldset: spec.fields, "limit": PAGE}
            pages = 0
            while url is not None:
                if pages >= MAX_PAGES:
                    complete = False
                    break
                pages += 1
                response = await _get(client, call, url, params)
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                    raise TargetError("unexpected", "none", False, "the answer is not a page")
                for item in body["data"]:
                    one = entry(kind, item, now)
                    if one is None:
                        complete = False
                    else:
                        found.append(one)
                links = body.get("links")
                following = links.get("next") if isinstance(links, dict) else None
                if not following:
                    url = None
                elif not isinstance(following, str) or not following.startswith(base + "/"):
                    raise TargetError(
                        "unexpected",
                        "none",
                        False,
                        "the next page is not at the configured address",
                    )
                else:
                    # The next link carries the cursor and the parameters of the first request.
                    url, params = following, None
    found.sort(key=lambda c: (c["days_left"], c["expires_at"], c["kind"], c["id"]))
    output = {
        "credentials": found[:limit],
        "complete": complete and len(found) <= limit,
        "read_at": _stamp(now),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"expiry.credentials.list": list_credentials}
