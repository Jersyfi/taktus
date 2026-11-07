"""How the social network's server is searched and its answer read.

The REST API answers `GET /api/v2/search?q=…&type=statuses&limit=…&offset=…` with
`{"accounts": [], "statuses": […], "hashtags": []}`. `limit` is at most 40 per type; `offset`
pages, and needs a user token, as does full-text search of statuses at all. Whether statuses can
be searched depends on the server: the documentation states that it needs the server's search
backend, so a server without one answers no statuses, and the connector cannot tell that from
"nothing matched" (README). The requesting identity's token is sent as a bearer token.

Each status is reduced to what sorting a mention needs: its id, its address (`url`, else `uri`),
its text with the markup taken out, its moment and `source: social`. Its account — name, handle,
avatar — is never copied: no step needs it, a person who answers opens the address, and what is
not read cannot leak. A `since` date is applied to each status's `created_at`, because the
search takes no date.

How the server's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: a request the server refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the token lacks `read:search` | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The server's own message stays out of `detail`.
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
PAGE = 40
MAX_PAGES = 20
SOURCE = "social"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Config:
    target: str
    """The address of the server searched; every server is its own."""
    timeout: float = 30.0


class _Text(HTMLParser):
    """The text of a status's markup: paragraphs and line breaks kept as lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "p") and self.parts:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def text_of(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    return re.sub(r"\n{2,}", "\n", "".join(parser.parts)).strip()


def query_of(input: Json) -> str:
    query = input.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise invalid("query must be text of 1 to 200 characters")
    return query.strip()


def since_of(input: Json) -> str | None:
    since = input.get("since")
    if since is None:
        return None
    if not isinstance(since, str) or DAY.match(since) is None:
        raise invalid("since must be a date, YYYY-MM-DD")
    try:
        date.fromisoformat(since)
    except ValueError as error:
        raise invalid("since must be a date, YYYY-MM-DD") from error
    return since


def limit_of(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


async def _get(config: Config, call: Call, params: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.get("/api/v2/search", params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the server did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the server could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise _unexpected("the server answered with a body it does not use")
        return body
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the server does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the token may not search")
    if status == 429 or status >= 500:
        raise unavailable(f"the server answered {status}")
    if status in (400, 404, 422):
        raise invalid(f"the server refused the search: {status}")
    raise _unexpected(f"the server answered {status}")


def _mention(status: Any) -> Json:
    if not isinstance(status, dict) or not isinstance(status.get("id"), str):
        raise _unexpected("a status has no identifier")
    url = status.get("url") if isinstance(status.get("url"), str) else status.get("uri")
    content = status.get("content")
    return {
        "id": status["id"],
        "url": url if isinstance(url, str) else None,
        "text": text_of(content) if isinstance(content, str) else "",
        "created_at": status.get("created_at")
        if isinstance(status.get("created_at"), str)
        else None,
        "source": SOURCE,
    }


async def query(config: Config, call: Call, input: Json) -> Outcome:
    q, since, limit = query_of(input), since_of(input), limit_of(input)
    read: list[Json] = []
    offset = 0
    more = True
    for _ in range(MAX_PAGES):
        if not more or len(read) >= limit:
            break
        page = await _get(
            config, call, {"q": q, "type": "statuses", "limit": PAGE, "offset": offset}
        )
        statuses = page.get("statuses")
        if not isinstance(statuses, list):
            raise _unexpected("the answer has no statuses")
        offset += len(statuses)
        more = len(statuses) == PAGE
        for mention in (_mention(s) for s in statuses):
            if since is None or (mention["created_at"] or "") >= since:
                read.append(mention)
    output = {
        "query": q,
        "mentions": read[:limit],
        "count": len(read[:limit]),
        "complete": not more and len(read) <= limit,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"mentions.search.query": query}
