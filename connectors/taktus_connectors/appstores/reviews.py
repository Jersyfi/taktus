"""How an app's customer reviews are asked, their answer read, and a reply written, on either
store (`stores.reviews`, ADR-0207).

Every call names its `platform`. `ios` is answered by the App Store Connect API under
`--app-store-target`, with a token signed for the call (`auth.app_store_token`); `android` by
the Google Play Developer API under `--play-target`, with an access token exchanged for the
call (`auth.play_token`). The requesting identity's credential is `STORES_KEY`, the key of
each store as a member of one document (`README.md`); the connector holds no key of its own
and keeps no token.

The paths, each as the store's documentation states it. App Store Connect:

| Operation | Request |
|---|---|
| list | `GET /v1/apps/{id}/customerReviews`, then each `links.next` |
| read | `GET /v1/customerReviews/{id}?include=response` |
| reply | the read, then `POST /v1/customerReviewResponses` |

A list there asks `include=response`, `sort=-createdDate`, `limit=200`, and `filter[rating]`
where ratings are given. Google Play, under `/androidpublisher/v3/applications/{package}`:

| Operation | Request |
|---|---|
| list | `GET …/reviews?maxResults=100`, then each `nextPageToken` as `token` |
| read | `GET …/reviews/{reviewId}` |
| reply | the read, then `POST …/reviews/{reviewId}:reply` with `replyText` |

A review is reduced to what a reply needs, in one shape on both stores: its rating, title,
text, territory, language, when it was written or last changed, the app version, and the
response in place. The reviewer's nickname, the author's name and the device are never
copied. App Store Connect serves no app version and no language with a review; Google Play no
title and no territory, and only reviews that carry a text and were written or changed in the
last week. Google Play filters by no rating: the connector keeps the `ratings` asked for
itself.

**The mark of a reply.** Each store keeps one response per review, and a second write replaces
it. Before writing, the connector reads the review: a response whose text is the reply's is
the original, and nothing is written again (`replayed`). The text is its own mark, weaker than
a key, and stated so: a repeat after somebody else wrote the same text reports replayed too. A
response of another text is a person's, or an earlier reply's, and is `conflict` unless the
call asks to `replace` it. A Google Play reply is at most 350 characters, as its API admits.

How the stores' answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400 (and 409, 422 on App Store Connect): a request the store refuses | `invalid` |
| 401, a token endpoint that refuses the key | `unauthenticated` |
| 403: the key's role may not do this | `forbidden` |
| 404: no such app or review | `not_found` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout or an unreadable answer on a write | `unknown`, effect `unknown` |
| any other status, a body that is not the store's | `unexpected` |

The store's own message stays out of `detail`: only its error code or status token is reported.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from taktus_connectors.appstores import auth
from taktus_connectors.appstores.config import Config
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

PLATFORMS = ("ios", "android")
LIMIT = 200
MAX_LIMIT = 2000
RECORD = "store.review.response"

APPLE_PAGE = 200
"""The most App Store Connect answers per page (`limit`, at most 200)."""
APPLE_PAGES = 20
APPLE_APP = re.compile(r"^[0-9]{1,20}$")
APPLE_REVIEW = re.compile(r"^[A-Za-z0-9-]{1,100}$")
APPLE_MAX_TEXT = 5970
"""A bound on a reply's text on App Store Connect, against a runaway draft; it documents none."""

PLAY_PAGE = 100
PLAY_PAGES = 50
PLAY_MAX_TEXT = 350
"""The longest reply Google Play accepts."""
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
PLAY_REVIEW = re.compile(r"^[A-Za-z0-9:_.\-]{1,200}$")
STATUS = re.compile(r"^[A-Z_]{1,40}$")


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


# --- the input --------------------------------------------------------------------------------


def _platform(input: Json) -> str:
    value = input.get("platform")
    if value not in PLATFORMS:
        raise invalid("platform must be ios or android")
    return str(value)


def _app(input: Json, platform: str) -> str:
    app = input.get("app")
    if platform == "ios":
        if not isinstance(app, str) or APPLE_APP.match(app) is None:
            raise invalid("app must be the app's identifier at the store, its digits")
    elif not isinstance(app, str) or PACKAGE.match(app) is None:
        raise invalid("app must be the app's package name, such as com.example.app")
    return app


def _review_id(input: Json, platform: str) -> str:
    review = input.get("review")
    pattern = APPLE_REVIEW if platform == "ios" else PLAY_REVIEW
    if not isinstance(review, str) or pattern.match(review) is None:
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


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _record(review: str, text: str) -> list[Json]:
    """The response a reply names: the review, and the text's digest, so that a repeat names
    what the first call wrote and another text another record."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return [{"kind": RECORD, "id": f"{review}@{digest}"}]


# --- one request ------------------------------------------------------------------------------


async def _send(
    config: Config,
    base: str,
    bearer: str,
    method: str,
    path: str,
    params: Json | None,
    body: Json | None,
) -> httpx.Response:
    writing = method != "GET"
    try:
        async with httpx.AsyncClient(
            base_url=base.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {bearer}", "Accept": "application/json"},
        ) as client:
            return await client.request(method, path, params=params, json=body)
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


def _answer(response: httpx.Response, writing: bool) -> Json:
    try:
        answer = response.json()
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        if writing:
            raise TargetError("unknown", "unknown", False, "the store answered unreadably")
        raise _unexpected("the store answered with a body it does not use")
    return answer


# --- App Store Connect ------------------------------------------------------------------------


def _apple_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list) or not errors or not isinstance(errors[0], dict):
        return ""
    code = errors[0].get("code")
    return code if isinstance(code, str) and re.fullmatch(r"[A-Z_.]{1,80}", code) else ""


async def _apple(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    params: Json | None = None,
    body: Json | None = None,
) -> Json:
    signed = auth.app_store_token(call)
    call.count()
    response = await _send(config, config.app_store_target, signed, method, path, params, body)
    status = response.status_code
    if status in (200, 201):
        return _answer(response, method != "GET")
    code = _apple_code(response)
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


def _apple_responses(document: Json) -> dict[str, str | None]:
    """The response texts the document includes, by the response's identifier."""
    found: dict[str, str | None] = {}
    for entry in document.get("included") or []:
        if isinstance(entry, dict) and entry.get("type") == "customerReviewResponses":
            attributes = entry.get("attributes") or {}
            text = attributes.get("responseBody")
            found[str(entry.get("id"))] = text if isinstance(text, str) else None
    return found


def _apple_review(record: Any, responses: dict[str, str | None]) -> Json:
    if not isinstance(record, dict) or record.get("type") != "customerReviews":
        raise _unexpected("a record is not a customer review")
    if not isinstance(record.get("id"), str):
        raise _unexpected("a review has no identifier")
    attributes = record.get("attributes") or {}
    rating = attributes.get("rating")
    relation = ((record.get("relationships") or {}).get("response") or {}).get("data")
    related = relation.get("id") if isinstance(relation, dict) else None
    return {
        "id": record["id"],
        "rating": rating if isinstance(rating, int) and not isinstance(rating, bool) else None,
        "title": attributes.get("title") if isinstance(attributes.get("title"), str) else None,
        "text": attributes.get("body") if isinstance(attributes.get("body"), str) else None,
        "territory": attributes.get("territory"),
        "language": None,
        "at": attributes.get("createdDate"),
        "version": None,
        "responded": isinstance(related, str),
        "response": responses.get(related) if isinstance(related, str) else None,
    }


def _apple_next(page: Json) -> str | None:
    """The path and query of the next page, on the configured address, or None."""
    link = (page.get("links") or {}).get("next")
    if not isinstance(link, str) or not link:
        return None
    parts = urlsplit(link)
    return parts.path + (f"?{parts.query}" if parts.query else "")


async def _apple_list(
    config: Config, call: Call, app: str, ratings: list[int] | None, limit: int
) -> tuple[list[Json], bool]:
    params: Json | None = {
        "include": "response",
        "sort": "-createdDate",
        "limit": min(APPLE_PAGE, limit),
    }
    if ratings is not None and params is not None:
        params["filter[rating]"] = ",".join(str(r) for r in ratings)
    path: str | None = f"/v1/apps/{app}/customerReviews"
    read: list[Json] = []
    more = False
    for _ in range(APPLE_PAGES):
        if path is None:
            break
        page = await _apple(config, call, "GET", path, params=params)
        data = page.get("data")
        if not isinstance(data, list):
            raise _unexpected("the answer is not a list of reviews")
        responses = _apple_responses(page)
        read.extend(_apple_review(record, responses) for record in data)
        path, params = _apple_next(page), None
        more = path is not None
        if not more or len(read) >= limit:
            break
    return read, more


async def _apple_read(config: Config, call: Call, app: str, review: str) -> Json:
    document = await _apple(
        config, call, "GET", f"/v1/customerReviews/{review}", params={"include": "response"}
    )
    return _apple_review(document.get("data"), _apple_responses(document))


async def _apple_reply(config: Config, call: Call, app: str, review: str, text: str) -> str | None:
    body = {
        "data": {
            "type": "customerReviewResponses",
            "attributes": {"responseBody": text},
            "relationships": {"review": {"data": {"type": "customerReviews", "id": review}}},
        }
    }
    written = await _apple(config, call, "POST", "/v1/customerReviewResponses", body=body)
    data = written.get("data")
    attributes = data.get("attributes") if isinstance(data, dict) else None
    state = attributes.get("state") if isinstance(attributes, dict) else None
    return state if isinstance(state, str) else None


# --- Google Play ------------------------------------------------------------------------------


def _play_status(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    status = error.get("status") if isinstance(error, dict) else None
    return status if isinstance(status, str) and STATUS.match(status) else ""


async def _play(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    params: Json | None = None,
    body: Json | None = None,
) -> Json:
    bearer = await auth.play_token(call, config.timeout, config.token())
    call.count()
    response = await _send(config, config.play_target, bearer, method, path, params, body)
    status = response.status_code
    if status == 200:
        return _answer(response, method != "GET")
    token = _play_status(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the store does not admit the token")
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


def _play_review(record: Any) -> Json:
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
    language = user.get("reviewerLanguage")
    version = user.get("appVersionName")
    return {
        "id": record["reviewId"],
        "rating": rating if isinstance(rating, int) and not isinstance(rating, bool) else None,
        "title": None,
        "text": user.get("text") if isinstance(user.get("text"), str) else None,
        "territory": None,
        "language": language if isinstance(language, str) else None,
        "at": _moment(user.get("lastModified")),
        "version": version if isinstance(version, str) else None,
        "responded": developer is not None,
        "response": reply if isinstance(reply, str) else None,
    }


def _play_root(app: str) -> str:
    return f"/androidpublisher/v3/applications/{app}/reviews"


async def _play_list(
    config: Config, call: Call, app: str, ratings: list[int] | None, limit: int
) -> tuple[list[Json], bool]:
    read: list[Json] = []
    page_token: str | None = None
    more = False
    for _ in range(PLAY_PAGES):
        params: Json = {"maxResults": PLAY_PAGE}
        if page_token is not None:
            params["token"] = page_token
        page = await _play(config, call, "GET", _play_root(app), params=params)
        found = page.get("reviews", [])
        if not isinstance(found, list):
            raise _unexpected("the answer is not a list of reviews")
        for record in found:
            one = _play_review(record)
            if ratings is None or one["rating"] in ratings:
                read.append(one)
        pagination = page.get("tokenPagination")
        following = pagination.get("nextPageToken") if isinstance(pagination, dict) else None
        page_token = following if isinstance(following, str) and following else None
        more = page_token is not None
        if not more or len(read) >= limit:
            break
    return read, more


async def _play_read(config: Config, call: Call, app: str, review: str) -> Json:
    return _play_review(await _play(config, call, "GET", f"{_play_root(app)}/{review}"))


async def _play_reply(config: Config, call: Call, app: str, review: str, text: str) -> str | None:
    written = await _play(
        config, call, "POST", f"{_play_root(app)}/{review}:reply", body={"replyText": text}
    )
    if not isinstance(written.get("result"), dict):
        raise TargetError("unknown", "unknown", False, "the store answered the reply unreadably")
    return None


# --- the operations ---------------------------------------------------------------------------


async def list_reviews(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    ratings = _ratings(input)
    limit = _limit(input)
    listing = _apple_list if platform == "ios" else _play_list
    read, more = await listing(config, call, app, ratings, limit)
    output = {
        "platform": platform,
        "app": app,
        "reviews": read[:limit],
        "complete": not more and len(read) <= limit,
    }
    return Outcome(output=output, effect={"kind": "read"})


async def read_review(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    reading = _apple_read if platform == "ios" else _play_read
    found = await reading(config, call, app, _review_id(input, platform))
    return Outcome(output=found, effect={"kind": "read"})


async def reply(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    review = _review_id(input, platform)
    longest = APPLE_MAX_TEXT if platform == "ios" else PLAY_MAX_TEXT
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > longest:
        raise invalid(f"text must be the reply's text, 1 to {longest} characters")
    replace = input.get("replace", False)
    if not isinstance(replace, bool):
        raise invalid("replace must be true or false")
    if not config.blind:
        reading = _apple_read if platform == "ios" else _play_read
        found = await reading(config, call, app, review)
        if found["responded"] and found["response"] == text:
            output = {"platform": platform, "review": review, "text": text, "state": None}
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
    writing = _apple_reply if platform == "ios" else _play_reply
    state = await writing(config, call, app, review, text)
    output = {"platform": platform, "review": review, "text": text, "state": state}
    return Outcome(output, {"kind": "write", "replayed": False, "records": _record(review, text)})


OPERATIONS = {
    "stores.reviews.list": list_reviews,
    "stores.reviews.read": read_review,
    "stores.reviews.reply": reply,
}
