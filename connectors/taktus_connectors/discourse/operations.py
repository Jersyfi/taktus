"""How the forum is searched and its answer read.

The API answers `GET /search.json?q=…&page=…` with `posts`, `topics`, `users`, `categories`,
`tags`, `groups` and `grouped_search_result`, whose `more_full_page_results` says whether a
further page holds more. A date is part of the query itself: `after:YYYY-MM-DD`. Every request
carries `Api-Key`, the requesting identity's key, and `Api-Username`, the forum user it acts
as, which is configuration.

Each post is reduced to what sorting a mention needs: its id, its address
(`<forum>/t/<topic_id>/<post_number>`, which the forum resolves to the post), its excerpt
(`blurb`) without markup, its moment and `source: forum`. Its `name`, `username` and
`avatar_template` are never copied: no step needs them, a person who answers opens the address,
and what is not read cannot leak.

How the forum's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: a request the forum refuses, a page past the last | `invalid` |
| 401, 403 with `error_type` `invalid_access`: key or user not admitted | `unauthenticated` |
| any other 403: the user may not search | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The forum's own message stays out of `detail`; only its `error_type` is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

LIMIT = 40
MAX_LIMIT = 400
MAX_PAGES = 20
SOURCE = "forum"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KIND = re.compile(r"^[a-z_]{1,40}$")


@dataclass(frozen=True)
class Config:
    target: str
    """The forum's address."""
    username: str = "system"
    """The forum user the key acts as: configuration, not a secret."""
    timeout: float = 30.0


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def text_of(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _kind(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    kind = body.get("error_type") if isinstance(body, dict) else None
    return kind if isinstance(kind, str) and KIND.match(kind) else ""


async def _get(config: Config, call: Call, params: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={
                "Api-Key": call.token,
                "Api-Username": config.username,
                "Accept": "application/json",
            },
        ) as client:
            response = await client.get("/search.json", params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the forum did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the forum could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise _unexpected("the forum answered with a body it does not use")
        return body
    kind = _kind(response)
    if status == 401 or (status == 403 and kind == "invalid_access"):
        raise TargetError("unauthenticated", "none", False, "the forum does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, f"the key may not search {kind}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the forum answered {status} {kind}".rstrip())
    if status in (400, 404, 422):
        raise invalid(f"the forum refused the search: {status} {kind}".rstrip())
    raise _unexpected(f"the forum answered {status} {kind}".rstrip())


def _mention(config: Config, post: Any) -> Json:
    if not isinstance(post, dict) or not isinstance(post.get("id"), int):
        raise _unexpected("a post has no identifier")
    topic, number = post.get("topic_id"), post.get("post_number")
    url = (
        f"{config.target.rstrip('/')}/t/{topic}/{number}"
        if isinstance(topic, int) and isinstance(number, int)
        else None
    )
    blurb = post.get("blurb")
    return {
        "id": str(post["id"]),
        "url": url,
        "text": text_of(blurb) if isinstance(blurb, str) else "",
        "created_at": post.get("created_at") if isinstance(post.get("created_at"), str) else None,
        "source": SOURCE,
    }


async def query(config: Config, call: Call, input: Json) -> Outcome:
    q = input.get("query")
    if not isinstance(q, str) or not q.strip() or len(q) > 200:
        raise invalid("query must be text of 1 to 200 characters")
    q = q.strip()
    since = input.get("since")
    if since is not None:
        if not isinstance(since, str) or DAY.match(since) is None:
            raise invalid("since must be a date, YYYY-MM-DD")
        try:
            date.fromisoformat(since)
        except ValueError as error:
            raise invalid("since must be a date, YYYY-MM-DD") from error
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    searched = f"{q} after:{since}" if since else q
    read: list[Json] = []
    more = True
    for page in range(1, MAX_PAGES + 1):
        answer = await _get(config, call, {"q": searched, "page": page})
        posts = answer.get("posts")
        grouped = answer.get("grouped_search_result")
        if not isinstance(posts, list):
            raise _unexpected("the answer has no posts")
        read.extend(_mention(config, post) for post in posts)
        more = bool(grouped.get("more_full_page_results")) if isinstance(grouped, dict) else False
        if not more or not posts or len(read) >= limit:
            break
    output = {
        "query": q,
        "mentions": read[:limit],
        "count": len(read[:limit]),
        "complete": not more and len(read) <= limit,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"mentions.search.query": query}
