"""How the feedback portal is asked and its answers read.

Every request of the API v1 is a `POST` to `https://canny.io/api/v1/<object>/<action>` with a
JSON body that carries the secret key as `apiKey`; the votes are listed through the API v2,
`POST /api/v2/votes/list`, paged by `cursor` while `hasNextPage` holds. A list of posts is paged
by `skip` and `limit` while `hasMore` holds. The requesting identity's key is the body's `apiKey`
and is sent to the configured address only.

The customer is named by e-mail address in the input, because that is what support knows of
them; `users/retrieve` turns it into the portal's user identifier. The address is never copied
into an output, nor is a post's author: the post's id, title, details, status, score and url are
what a match of a wish against the portal needs.

How the portal's answers map to the contract's causes. The documentation states 429 for a
throttled key and gives error bodies `{"error": "..."}`, and states no status for a refused key
or an unknown object, so the mapping below is by status class:

| Answer | Cause |
|---|---|
| 400, 404, a 200 whose body is `{"error": …}`: a request refused, an unknown object | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the key may not do this | `forbidden` |
| 429, 5xx, a refused connection, a read that timed out | `unavailable`, retryable |
| a write whose answer did not arrive | `unavailable`, effect `unknown`, retryable |
| any other status, a body that is not the API's | `unexpected` |

A write whose answer did not arrive is retried safely: the next attempt's lookup finds what it
made. The portal's own message stays out of `detail`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://canny.io"
LIMIT = 100
MAX_LIMIT = 1000
PAGE = 100
MAX_PAGES = 20
IDENTIFIER = re.compile(r"^[A-Za-z0-9]{1,64}$")
ADDRESS = re.compile(r"^[^@\s]{1,128}@[^@\s]{1,253}$")
REFERENCE = "ref taktus-"
"""How a created post's details end: the reference, then the digest of the idempotency key."""


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the portal's own, or a fake's."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def reference(key: str) -> str:
    """The reference a post's details carry: a digest of the key, not the key itself."""
    return REFERENCE + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


async def _post(config: Config, call: Call, path: str, body: Json, *, acting: bool = False) -> Any:
    """One request. `acting` for the request that writes: a connection lost after it was sent
    leaves its effect unknown, and the next attempt's lookup finds what it made."""
    call.count()
    effect = "unknown" if acting else "none"
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.post(path, json={**body, "apiKey": call.token})
    except httpx.ConnectError as error:
        raise unavailable(f"the portal could not be reached: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise TargetError(
            "unavailable", effect, True, f"the portal did not answer: {type(error).__name__}"
        ) from error
    status = response.status_code
    try:
        answer: Any = response.json()
    except ValueError:
        answer = response.text.strip() if status == 200 else None
    refused = isinstance(answer, dict) and "error" in answer
    if status == 200 and not refused:
        return answer
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the portal does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not do this")
    if status == 429 or status >= 500:
        raise unavailable(f"the portal answered {status}")
    if status in (200, 400, 404):
        raise invalid(f"the portal refused the request to {path}: {status}")
    raise _unexpected(f"the portal answered {status}")


def _text(value: Any, what: str, longest: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > longest:
        raise invalid(f"{what} must be text of 1 to {longest} characters")
    return value.strip()


def _identifier(value: Any, what: str) -> str:
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid(f"{what} must be the portal's identifier, letters and digits")
    return value


def _post_record(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str):
        raise _unexpected("a post has no identifier")
    board = record.get("board")
    score = record.get("score")
    return {
        "id": record["id"],
        "board": board.get("id") if isinstance(board, dict) else None,
        "title": record.get("title") if isinstance(record.get("title"), str) else "",
        "details": record.get("details") if isinstance(record.get("details"), str) else "",
        "status": record.get("status") if isinstance(record.get("status"), str) else None,
        "score": score if isinstance(score, int) and not isinstance(score, bool) else 0,
        "url": record.get("url") if isinstance(record.get("url"), str) else None,
    }


async def _posts(config: Config, call: Call, query: Json, limit: int) -> tuple[list[Json], bool]:
    read: list[Json] = []
    more = True
    for _ in range(MAX_PAGES):
        page = await _post(
            config,
            call,
            "/api/v1/posts/list",
            {**query, "limit": min(PAGE, limit - len(read)), "skip": len(read)},
        )
        posts = page.get("posts") if isinstance(page, dict) else None
        if not isinstance(posts, list):
            raise _unexpected("the answer is not a list of posts")
        read.extend(_post_record(record) for record in posts)
        more = bool(page.get("hasMore"))
        if not more or not posts or len(read) >= limit:
            break
    return read[:limit], not more


async def _user(config: Config, call: Call, email: Any) -> str:
    if not isinstance(email, str) or ADDRESS.match(email) is None:
        raise invalid("email must be the customer's e-mail address")
    user = await _post(config, call, "/api/v1/users/retrieve", {"email": email})
    if not isinstance(user, dict) or not isinstance(user.get("id"), str):
        raise _unexpected("the portal answered no user")
    return str(user["id"])


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    board = _identifier(input.get("board"), "board")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    query: Json = {"boardID": board}
    if input.get("search") is not None:
        query["search"] = _text(input.get("search"), "search", 200)
    posts, complete = await _posts(config, call, query, limit)
    return Outcome(
        output={"board": board, "posts": posts, "count": len(posts), "complete": complete},
        effect={"kind": "read"},
    )


def _write(output: Json, record: str, kind: str, *, replayed: bool) -> Outcome:
    return Outcome(
        output, {"kind": "write", "replayed": replayed, "records": [{"kind": kind, "id": record}]}
    )


async def create(config: Config, call: Call, input: Json) -> Outcome:
    board = _identifier(input.get("board"), "board")
    title = _text(input.get("title"), "title", 400)
    details = _text(input.get("details"), "details", 9000)
    author = await _user(config, call, input.get("email"))
    mark = reference(call.key)
    # Before acting: the customer's own posts on the board, searched for the reference.
    own, _ = await _posts(config, call, {"boardID": board, "authorID": author}, MAX_LIMIT)
    for post in own:
        if mark in post["details"]:
            return _write(
                {"id": post["id"], "url": post["url"], "board": board},
                post["id"],
                "feedback.post",
                replayed=True,
            )
    made = await _post(
        config,
        call,
        "/api/v1/posts/create",
        {
            "authorID": author,
            "boardID": board,
            "title": title,
            "details": f"{details}\n\n[{mark}]",
        },
        acting=True,
    )
    if not isinstance(made, dict) or not isinstance(made.get("id"), str):
        raise TargetError("unexpected", "unknown", True, "the portal answered no post")
    url = made.get("url") if isinstance(made.get("url"), str) else None
    return _write(
        {"id": made["id"], "url": url, "board": board}, made["id"], "feedback.post", replayed=False
    )


async def _voted(config: Config, call: Call, post: str, voter: str) -> bool:
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        body: Json = {"postID": post, "limit": 100}
        if cursor:
            body["cursor"] = cursor
        page = await _post(config, call, "/api/v2/votes/list", body)
        items = page.get("items") if isinstance(page, dict) else None
        if not isinstance(items, list):
            raise _unexpected("the answer is not a list of votes")
        for vote in items:
            who = vote.get("voter") if isinstance(vote, dict) else None
            if isinstance(who, dict) and who.get("id") == voter:
                return True
        if not page.get("hasNextPage"):
            return False
        cursor = page.get("cursor") if isinstance(page.get("cursor"), str) else None
        if not cursor:
            return False
    raise _unexpected("the votes of the post did not end within the pages read")


async def vote(config: Config, call: Call, input: Json) -> Outcome:
    post = _identifier(input.get("post"), "post")
    voter = await _user(config, call, input.get("email"))
    record = f"{post}/{voter}"
    if await _voted(config, call, post, voter):
        return _write({"post": post, "counted": True}, record, "feedback.vote", replayed=True)
    answered = await _post(
        config, call, "/api/v1/votes/create", {"postID": post, "voterID": voter}, acting=True
    )
    if answered != "success":
        raise TargetError("unexpected", "unknown", True, "the portal did not confirm the vote")
    return _write({"post": post, "counted": True}, record, "feedback.vote", replayed=False)


OPERATIONS = {
    "feedback.posts.list": list_,
    "feedback.posts.create": create,
    "feedback.posts.vote": vote,
}
