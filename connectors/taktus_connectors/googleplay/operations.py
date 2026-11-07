"""How the reviews are asked, their answer read, and a reply written (ADR-0207).

**The token.** The requesting identity's credential is a service account's key file, as the
store's console hands it out: JSON with `client_email`, `private_key_id` and `private_key`. At
the moment of a call the connector signs a JSON Web Token with it, RS256, the key's identifier
as `kid`, `iss` the account's address, `scope` the store's publishing scope, `aud` the token
endpoint and an `exp` one hour after `iat`, and exchanges it at the token endpoint
(`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`) for an access token. The access
token is kept in memory, by the digest of the key, until a minute before it expires; nothing is
written down. The token endpoint is the configured one, never the `token_uri` the file names:
the key goes to the configured address and nowhere else.

The paths, each as the API's documentation states it, under
`/androidpublisher/v3/applications/{packageName}`:

| Operation | Request |
|---|---|
| list | `GET …/reviews?maxResults=100`, then each `tokenPagination.nextPageToken` as `token` |
| read | `GET …/reviews/{reviewId}` |
| reply | the read, then `POST …/reviews/{reviewId}:reply` with `replyText` |

The API answers only reviews that carry a text and were written or changed in the last week,
and filters by no rating: the connector keeps the `ratings` asked for itself. A review is
reduced to what a reply needs: its rating, text, language, when it was last changed, the app
version, and the reply in place. The author's name, the device and its metadata are never
copied. The API gives no title and no territory.

**The mark of a reply.** The API keeps one reply per review and replaces it on a second call.
Before writing, the connector reads the review: a reply whose text is the new one is the
original, and nothing is written again (`replayed`). The text is its own mark, weaker than a
key, and stated so: a repeat after somebody else wrote the same text reports replayed too. A
reply of another text is a person's, or an earlier reply's, and is `conflict` unless the call
asks to `replace` it. A reply is at most 350 characters, as the API admits.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a request the API refuses, a reply too long | `invalid` |
| 401, a token endpoint that refuses the key: the key is not admitted | `unauthenticated` |
| 403: the account may not do this for the app | `forbidden` |
| 404: no such app or review | `not_found` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout or an unreadable answer on a write | `unknown`, effect `unknown` |
| any other status, a body that is not the API's | `unexpected` |

The API's own message stays out of `detail`: only its status token is reported.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://androidpublisher.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — an address, not a secret
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
LIFETIME = 3600
"""Seconds the signed statement is valid: the hour the token endpoint admits at most."""
PAGE = 100
LIMIT = 200
MAX_LIMIT = 2000
MAX_PAGES = 50
MAX_REPLY = 350
"""The longest reply the API accepts."""
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
REVIEW = re.compile(r"^[A-Za-z0-9:_.\-]{1,200}$")
STATUS = re.compile(r"^[A-Z_]{1,40}$")
RECORD = "store.review.response"


@dataclass
class Tokens:
    """Access tokens by the digest of the key they were exchanged for, until they expire."""

    held: dict[str, tuple[str, float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the store's own, or a fake's."""
    token_url: str = TOKEN_URL
    """The token endpoint. A path, `/token`, is taken on `target`: a fake serves both."""
    timeout: float = 30.0
    blind: bool = False
    """Fault C-05 only: the reply in place is not read before a reply is written."""
    tokens: Tokens = field(default_factory=Tokens, compare=False)

    @property
    def token_endpoint(self) -> str:
        if self.token_url.startswith("/"):
            return self.target.rstrip("/") + self.token_url
        return self.token_url


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _refused(detail: str) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail)


def statement(value: str, audience: str, now: float | None = None) -> str:
    """The signed statement the token endpoint exchanges, from a service account's key file."""
    try:
        key = json.loads(value)
    except ValueError as error:
        raise _refused("the credential is not a service account's key file") from error
    if not isinstance(key, dict) or not all(
        isinstance(key.get(k), str) and key.get(k)
        for k in ("client_email", "private_key", "private_key_id")
    ):
        raise _refused("the credential is not a service account's key file")
    issued = int(now if now is not None else time.time())
    claims = {
        "iss": key["client_email"],
        "scope": SCOPE,
        "aud": audience,
        "iat": issued,
        "exp": issued + LIFETIME,
    }
    try:
        return jwt.encode(
            claims, key["private_key"], algorithm="RS256", headers={"kid": key["private_key_id"]}
        )
    except (ValueError, TypeError, jwt.PyJWTError) as error:
        # The type alone: an error's text can quote the key.
        raise _refused(
            f"the credential's key does not sign RS256: {type(error).__name__}"
        ) from error


async def access_token(config: Config, call: Call) -> str:
    digest = hashlib.sha256(call.token.encode("utf-8")).hexdigest()
    with config.tokens.lock:
        held = config.tokens.held.get(digest)
    if held is not None and held[1] > time.time() + 60:
        return held[0]
    signed = statement(call.token, config.token_endpoint)
    call.count()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
        ) as client:
            response = await client.post(
                config.token_endpoint, data={"grant_type": GRANT, "assertion": signed}
            )
    except httpx.HTTPError as error:
        raise unavailable(
            f"the token endpoint could not be reached: {type(error).__name__}"
        ) from error
    if response.status_code in (400, 401, 403):
        raise _refused("the token endpoint does not admit the key")
    if response.status_code == 429 or response.status_code >= 500:
        raise unavailable(f"the token endpoint answered {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if (
        response.status_code != 200
        or not isinstance(body, dict)
        or not isinstance(body.get("access_token"), str)
    ):
        raise _unexpected("the token endpoint answered with a body it does not use")
    expires = body.get("expires_in")
    lifetime = float(expires) if isinstance(expires, int | float) else 0.0
    with config.tokens.lock:
        config.tokens.held[digest] = (body["access_token"], time.time() + lifetime)
    return str(body["access_token"])


def _status(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    status = error.get("status") if isinstance(error, dict) else None
    return status if isinstance(status, str) and STATUS.match(status) else ""


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
    bearer = await access_token(config, call)
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"},
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
    if status == 200:
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            if writing:
                raise TargetError("unknown", "unknown", False, "the store answered unreadably")
            raise _unexpected("the store answered with a body it does not use")
        return answer
    token = _status(response)
    if status == 401:
        with config.tokens.lock:
            config.tokens.held.pop(hashlib.sha256(call.token.encode()).hexdigest(), None)
        raise _refused("the store does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the account may not do this for the app")
    if status == 404:
        raise TargetError("not_found", "none", False, "the store knows no such app or review")
    if status == 429 or status >= 500:
        raise unavailable(f"the store answered {status} {token}".rstrip())
    if status == 400:
        raise invalid(f"the store refused the request: {status} {token}".rstrip())
    raise _unexpected(f"the store answered {status} {token}".rstrip())


def _moment(value: Any) -> str | None:
    seconds = value.get("seconds") if isinstance(value, dict) else None
    try:
        moment = datetime.fromtimestamp(int(str(seconds)), UTC)
    except (TypeError, ValueError, OverflowError):
        return None
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _review(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("reviewId"), str):
        raise _unexpected("a record is not a review")
    comments = record.get("comments")
    if not isinstance(comments, list):
        raise _unexpected("a review has no comments")
    user: Json = {}
    developer: Json | None = None
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        if isinstance(comment.get("userComment"), dict) and not user:
            user = comment["userComment"]
        if isinstance(comment.get("developerComment"), dict):
            developer = comment["developerComment"]
    rating = user.get("starRating")
    reply = developer.get("text") if developer is not None else None
    return {
        "id": record["reviewId"],
        "rating": rating if isinstance(rating, int) and not isinstance(rating, bool) else None,
        "title": None,
        "text": user.get("text") if isinstance(user.get("text"), str) else None,
        "territory": None,
        "language": user.get("reviewerLanguage")
        if isinstance(user.get("reviewerLanguage"), str)
        else None,
        "at": _moment(user.get("lastModified")),
        "version": user.get("appVersionName")
        if isinstance(user.get("appVersionName"), str)
        else None,
        "responded": developer is not None,
        "response": reply if isinstance(reply, str) else None,
    }


def _app(input: Json) -> str:
    app = input.get("app")
    if not isinstance(app, str) or PACKAGE.match(app) is None:
        raise invalid("app must be the app's package name, such as com.example.app")
    return app


def _review_id(input: Json) -> str:
    review = input.get("review")
    if not isinstance(review, str) or REVIEW.match(review) is None:
        raise invalid("review must be a review's identifier at the store")
    return review


def _ratings(input: Json) -> set[int] | None:
    ratings = input.get("ratings")
    if ratings is None:
        return None
    if (
        not isinstance(ratings, list)
        or not ratings
        or not all(isinstance(r, int) and not isinstance(r, bool) and 1 <= r <= 5 for r in ratings)
    ):
        raise invalid("ratings must be a list of whole numbers from 1 to 5")
    return set(ratings)


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    app = _app(input)
    ratings = _ratings(input)
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    read: list[Json] = []
    page_token: str | None = None
    more = False
    for _ in range(MAX_PAGES):
        params: Json = {"maxResults": PAGE}
        if page_token is not None:
            params["token"] = page_token
        page = await _request(
            config, call, "GET", f"/androidpublisher/v3/applications/{app}/reviews", params=params
        )
        reviews = page.get("reviews", [])
        if not isinstance(reviews, list):
            raise _unexpected("the answer is not a list of reviews")
        for record in reviews:
            found = _review(record)
            if ratings is None or found["rating"] in ratings:
                read.append(found)
        pagination = page.get("tokenPagination")
        following = pagination.get("nextPageToken") if isinstance(pagination, dict) else None
        page_token = following if isinstance(following, str) and following else None
        more = page_token is not None
        if not more or len(read) >= limit:
            break
    output = {"app": app, "reviews": read[:limit], "complete": not more and len(read) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


async def _read(config: Config, call: Call, app: str, review: str) -> Json:
    record = await _request(
        config, call, "GET", f"/androidpublisher/v3/applications/{app}/reviews/{review}"
    )
    return _review(record)


async def read(config: Config, call: Call, input: Json) -> Outcome:
    found = await _read(config, call, _app(input), _review_id(input))
    return Outcome(output=found, effect={"kind": "read"})


def _record(review: str, text: str) -> list[Json]:
    """The reply a write names: the review, and the text's digest, so that a repeat names what
    the first call wrote and another text another record."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return [{"kind": RECORD, "id": f"{review}@{digest}"}]


async def reply(config: Config, call: Call, input: Json) -> Outcome:
    app = _app(input)
    review = _review_id(input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_REPLY:
        raise invalid(f"text must be the reply's text, 1 to {MAX_REPLY} characters")
    replace = input.get("replace", False)
    if not isinstance(replace, bool):
        raise invalid("replace must be true or false")
    if not config.blind:
        found = await _read(config, call, app, review)
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
                "the review has a reply of another text; it is replaced only when asked",
            )
    written = await _request(
        config,
        call,
        "POST",
        f"/androidpublisher/v3/applications/{app}/reviews/{review}:reply",
        body={"replyText": text},
    )
    result = written.get("result")
    if not isinstance(result, dict):
        raise TargetError("unknown", "unknown", False, "the store answered the reply unreadably")
    output = {"review": review, "text": text, "state": None}
    return Outcome(output, {"kind": "write", "replayed": False, "records": _record(review, text)})


OPERATIONS = {
    "stores.reviews.list": list_,
    "stores.reviews.read": read,
    "stores.reviews.reply": reply,
}
