"""How the customer reviews are asked, their answer read, and a response written (ADR-0207).

Every request goes to `--target` (the API's own address by default) with a token the connector
signs at the moment of the call: a JSON Web Token, ES256, with the key identifier in its header
and the issuer, `iat`, `exp` and the audience `appstoreconnect-v1` in its payload, valid for
fifteen minutes, under the twenty the API admits. The requesting identity's credential is the
key itself (`README.md`); the connector holds no key of its own and keeps no token.

The paths, each as the API's documentation states it. A list asks `include=response`,
`sort=-createdDate`, `limit=200`, and `filter[rating]` where ratings are given.

| Operation | Request |
|---|---|
| list | `GET /v1/apps/{id}/customerReviews`, then each `links.next` |
| read | `GET /v1/customerReviews/{id}?include=response` |
| reply | the read, then `POST /v1/customerReviewResponses` |

A review is reduced to what a reply needs: its rating, title, text, territory, when it was
written, and the response in place. The reviewer's nickname is never copied. The API serves no
app version with a review, so `version` is always null.

**The mark of a reply.** The API keeps one response per review, and a POST replaces it. Before
writing, the connector reads the review: a response whose text is the reply's is the original,
and nothing is written again (`replayed`). The text is its own mark, weaker than a key, and
stated so: a repeat after somebody else wrote the same text reports replayed too. A response of
another text is a person's, or an earlier reply's, and is `conflict` unless the call asks to
`replace` it.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 409, 422: a request the API refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the key's role may not do this | `forbidden` |
| 404: no such app or review | `not_found` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout or an unreadable answer on a write | `unknown`, effect `unknown` |
| any other status, a body that is not the API's | `unexpected` |

The API's own message stays out of `detail`: only its error code is reported.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.appstoreconnect.apple.com"
AUDIENCE = "appstoreconnect-v1"
LIFETIME = 900
"""Seconds a signed token is valid: fifteen minutes, under the twenty the API admits."""
PAGE = 200
"""The most the API answers per page (`limit`, at most 200)."""
LIMIT = 200
MAX_LIMIT = 2000
MAX_PAGES = 20
APP = re.compile(r"^[0-9]{1,20}$")
REVIEW = re.compile(r"^[A-Za-z0-9-]{1,100}$")
MAX_TEXT = 5970
"""A bound on a reply's text, against a runaway draft; the API documents none."""
RECORD = "store.review.response"


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    timeout: float = 30.0
    blind: bool = False
    """Fault C-05 only: the response in place is not read before a reply is written."""


@dataclass(frozen=True)
class Key:
    """The requesting identity's key: `<issuer id>:<key id>:<base64 of the .p8 file>`."""

    issuer: str
    key_id: str
    pem: bytes


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def key_of(value: str) -> Key:
    parts = value.split(":")
    if len(parts) != 3 or not all(parts):
        raise TargetError(
            "unauthenticated",
            "none",
            False,
            "the credential is not <issuer id>:<key id>:<base64 of the private key file>",
        )
    issuer, key_id, encoded = parts
    try:
        pem = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise TargetError(
            "unauthenticated", "none", False, "the credential's key is not base64"
        ) from error
    return Key(issuer, key_id, pem)


def token(value: str, now: float | None = None) -> str:
    """A token signed with the requesting identity's key, valid for LIFETIME seconds."""
    key = key_of(value)
    issued = int(now if now is not None else time.time())
    claims = {"iss": key.issuer, "iat": issued, "exp": issued + LIFETIME, "aud": AUDIENCE}
    try:
        return jwt.encode(claims, key.pem, algorithm="ES256", headers={"kid": key.key_id})
    except (ValueError, TypeError, jwt.PyJWTError) as error:
        # The type alone: an error's text can quote the key.
        raise TargetError(
            "unauthenticated",
            "none",
            False,
            f"the credential's key does not sign ES256: {type(error).__name__}",
        ) from error


def _code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list) or not errors or not isinstance(errors[0], dict):
        return ""
    code = errors[0].get("code")
    return code if isinstance(code, str) and re.fullmatch(r"[A-Z_.]{1,80}", code) else ""


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    params: Json | None = None,
    body: Json | None = None,
) -> Json:
    writing = method != "GET"
    signed = token(call.token)
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {signed}", "Accept": "application/json"},
        ) as client:
            response = await client.request(method, path, params=params, json=body)
    except httpx.ConnectError as error:
        raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the store did not answer the reply in time"
            ) from error
        raise unavailable(f"the store did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            if writing:
                raise TargetError("unknown", "unknown", False, "the store answered unreadably")
            raise _unexpected("the store answered with a body it does not use")
        return answer
    code = _code(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the store does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key's role may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "the store knows no such app or review")
    if status == 429 or status >= 500:
        raise unavailable(f"the store answered {status} {code}".rstrip())
    if status in (400, 409, 422):
        raise invalid(f"the store refused the request: {status} {code}".rstrip())
    raise _unexpected(f"the store answered {status} {code}".rstrip())


def _responses(document: Json) -> dict[str, str | None]:
    """The response texts the document includes, by the response's identifier."""
    found: dict[str, str | None] = {}
    for entry in document.get("included") or []:
        if isinstance(entry, dict) and entry.get("type") == "customerReviewResponses":
            attributes = entry.get("attributes") or {}
            text = attributes.get("responseBody")
            found[str(entry.get("id"))] = text if isinstance(text, str) else None
    return found


def _review(record: Any, responses: dict[str, str | None]) -> Json:
    if not isinstance(record, dict) or record.get("type") != "customerReviews":
        raise _unexpected("a record is not a customer review")
    if not isinstance(record.get("id"), str):
        raise _unexpected("a review has no identifier")
    attributes = record.get("attributes") or {}
    rating = attributes.get("rating")
    relation = ((record.get("relationships") or {}).get("response") or {}).get("data")
    related = relation.get("id") if isinstance(relation, dict) else None
    responded = isinstance(related, str)
    return {
        "id": record["id"],
        "rating": rating if isinstance(rating, int) and not isinstance(rating, bool) else None,
        "title": attributes.get("title") if isinstance(attributes.get("title"), str) else None,
        "text": attributes.get("body") if isinstance(attributes.get("body"), str) else None,
        "territory": attributes.get("territory"),
        "language": None,
        "at": attributes.get("createdDate"),
        "version": None,
        "responded": responded,
        "response": responses.get(related) if isinstance(related, str) else None,
    }


def _app(input: Json) -> str:
    app = input.get("app")
    if not isinstance(app, str) or APP.match(app) is None:
        raise invalid("app must be the app's identifier at the store, its digits")
    return app


def _review_id(input: Json) -> str:
    review = input.get("review")
    if not isinstance(review, str) or REVIEW.match(review) is None:
        raise invalid("review must be a review's identifier at the store")
    return review


def _ratings(input: Json) -> list[int] | None:
    ratings = input.get("ratings")
    if ratings is None:
        return None
    if (
        not isinstance(ratings, list)
        or not ratings
        or not all(isinstance(r, int) and not isinstance(r, bool) and 1 <= r <= 5 for r in ratings)
    ):
        raise invalid("ratings must be a list of whole numbers from 1 to 5")
    return sorted(set(ratings))


def _next(page: Json) -> str | None:
    """The path and query of the next page, on the configured address, or None."""
    link = (page.get("links") or {}).get("next")
    if not isinstance(link, str) or not link:
        return None
    parts = urlsplit(link)
    return parts.path + (f"?{parts.query}" if parts.query else "")


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    app = _app(input)
    ratings = _ratings(input)
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    params: Json | None = {
        "include": "response",
        "sort": "-createdDate",
        "limit": min(PAGE, limit),
    }
    if ratings is not None and params is not None:
        params["filter[rating]"] = ",".join(str(r) for r in ratings)
    path: str | None = f"/v1/apps/{app}/customerReviews"
    read: list[Json] = []
    more = False
    for _ in range(MAX_PAGES):
        if path is None:
            break
        page = await _request(config, call, "GET", path, params=params)
        data = page.get("data")
        if not isinstance(data, list):
            raise _unexpected("the answer is not a list of reviews")
        responses = _responses(page)
        read.extend(_review(record, responses) for record in data)
        path, params = _next(page), None
        more = path is not None
        if not more or len(read) >= limit:
            break
    output = {"app": app, "reviews": read[:limit], "complete": not more and len(read) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


async def _read(config: Config, call: Call, review: str) -> Json:
    document = await _request(
        config, call, "GET", f"/v1/customerReviews/{review}", params={"include": "response"}
    )
    return _review(document.get("data"), _responses(document))


async def read(config: Config, call: Call, input: Json) -> Outcome:
    _app(input)
    found = await _read(config, call, _review_id(input))
    return Outcome(output=found, effect={"kind": "read"})


def _record(review: str, text: str) -> list[Json]:
    """The response a reply names: the review, and the text's digest, so that a repeat names
    what the first call wrote and another text another record."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return [{"kind": RECORD, "id": f"{review}@{digest}"}]


async def reply(config: Config, call: Call, input: Json) -> Outcome:
    _app(input)
    review = _review_id(input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise invalid(f"text must be the reply's text, 1 to {MAX_TEXT} characters")
    replace = input.get("replace", False)
    if not isinstance(replace, bool):
        raise invalid("replace must be true or false")
    if not config.blind:
        found = await _read(config, call, review)
        if found["responded"] and found["response"] == text:
            output = {"review": review, "text": text, "state": None}
            return Outcome(
                output, {"kind": "write", "replayed": True, "records": _record(review, text)}
            )
        if found["responded"] and not replace:
            raise TargetError(
                "conflict",
                "none",
                False,
                "the review has a response of another text; it is replaced only when asked",
            )
    body = {
        "data": {
            "type": "customerReviewResponses",
            "attributes": {"responseBody": text},
            "relationships": {"review": {"data": {"type": "customerReviews", "id": review}}},
        }
    }
    written = await _request(config, call, "POST", "/v1/customerReviewResponses", body=body)
    data = written.get("data")
    attributes = data.get("attributes") if isinstance(data, dict) else None
    state = attributes.get("state") if isinstance(attributes, dict) else None
    output = {"review": review, "text": text, "state": state if isinstance(state, str) else None}
    return Outcome(output, {"kind": "write", "replayed": False, "records": _record(review, text)})


OPERATIONS = {
    "stores.reviews.list": list_,
    "stores.reviews.read": read,
    "stores.reviews.reply": reply,
}
