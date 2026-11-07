"""How the site's REST API is asked, and its answers read.

Every request goes to `--target` under `/wp-json/wp/v2/`, authenticated as WordPress documents
for an application password: HTTP Basic, `<user>:<application password>`, the requesting
identity's credential as one value. The credential is never one of the connector's own.

**The mark of a draft.** A post is created with the slug `taktus-` and the first 16
hexadecimal digits of the SHA-256 of the idempotency key; the key itself never leaves Taktus.
Before creating, the connector asks for the posts with that slug in every status a draft can
reach — `draft`, `pending`, `publish`, `future`, `private` — in the `edit` context, which only a
user who may edit posts is answered. One found is the original, and nothing is created again. A
person who publishes the post may change its slug; a repeat after that is no longer a repeat.

**The mark of publishing.** A post already `publish` is not published again: its status is its
own mark. Weaker than a key, and stated so. A post a person scheduled (`future`) is a conflict:
publishing it now would overrule them.

How the API's answers map to the contract's causes (only the error's `code` is passed on):

| Answer | Cause |
|---|---|
| 400: a request the API refuses | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403: the user may not do this | `forbidden` |
| 404: no such post | `not_found` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

STATUSES = "draft,pending,publish,future,private"
TITLE = 300
CONTENT = 500_000
CODE = re.compile(r"^[a-z0-9_]{1,80}$")


@dataclass(frozen=True)
class Config:
    target: str
    """The site's address; the REST API answers under `/wp-json/`."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def mark(key: str) -> str:
    """The draft's slug: a digest of the key, never the key."""
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    code = body.get("code") if isinstance(body, dict) else None
    return code if isinstance(code, str) and CODE.match(code) else ""


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    body: Json | None = None,
    params: Json | None = None,
) -> Any:
    writing = method != "GET"
    call.count()
    user, _, password = call.token.partition(":")
    if not user or not password:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is not a user and a password"
        )
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(
                method,
                f"/wp-json/wp/v2/{path}",
                auth=(user, password),
                headers={"Accept": "application/json"},
                params=params,
                json=body,
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the site could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the site did not answer the write in time"
            ) from error
        raise unavailable(f"the site did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the site could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            return response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the site answered the write unreadably"
                ) from error
            raise _unexpected("the site answered with a body that is not JSON") from error
    code = _code(response)
    if status == 400:
        raise invalid(f"the site refused the request: {code or status}")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the site does not admit the user")
    if status == 403:
        raise TargetError("forbidden", "none", False, f"the user may not do this: {code}")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such post on the site")
    if status == 429 or status >= 500:
        raise unavailable(f"the site answered {status}")
    raise _unexpected(f"the site answered {status}, which the connector does not foresee")


def _identifier(input: Json) -> int:
    value = input.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise invalid("id must be a post's number")
    return value


def _text(input: Json, field: str, limit: int, *, required: bool = True) -> str | None:
    value = input.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise invalid(f"{field} must be text of at most {limit} characters")
    return value


def _rendered(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("rendered", ""))
    return str(value or "")


def post_output(found: Any) -> Json:
    if not isinstance(found, dict) or not isinstance(found.get("id"), int):
        raise _unexpected("the site answered a post in a shape the connector does not know")
    return {
        "id": found["id"],
        "status": str(found.get("status", "")),
        "title": _rendered(found.get("title")),
        "link": str(found.get("link", "")),
        "slug": str(found.get("slug", "")),
        "modified": found.get("modified"),
    }


def _write(output: Json, kind: str, *, replayed: bool) -> Outcome:
    records = [{"kind": kind, "id": str(output["id"])}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def _post(config: Config, call: Call, identifier: int) -> Json:
    found = await _request(config, call, "GET", f"posts/{identifier}", params={"context": "edit"})
    return post_output(found)


async def read(config: Config, call: Call, input: Json) -> Outcome:
    output = await _post(config, call, _identifier(input))
    return Outcome(
        {k: output[k] for k in ("id", "status", "title", "link", "modified")}, {"kind": "read"}
    )


async def draft(config: Config, call: Call, input: Json) -> Outcome:
    title = _text(input, "title", TITLE)
    content = _text(input, "content", CONTENT)
    excerpt = _text(input, "excerpt", TITLE * 4, required=False)
    slug = mark(call.key)
    listed = await _request(
        config,
        call,
        "GET",
        "posts",
        params={"slug": slug, "status": STATUSES, "context": "edit", "per_page": 1},
    )
    if not isinstance(listed, list):
        raise _unexpected("the site's list of posts is not a list")
    if listed:
        found = post_output(listed[0])
        return _write(_draft_output(found), "website.post", replayed=True)
    body: Json = {"title": title, "content": content, "status": "draft", "slug": slug}
    if excerpt is not None:
        body["excerpt"] = excerpt
    created = await _request(config, call, "POST", "posts", body=body)
    return _write(_draft_output(post_output(created)), "website.post", replayed=False)


def _draft_output(post: Json) -> Json:
    return {k: post[k] for k in ("id", "status", "link", "slug")}


async def publish(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    before = await _post(config, call, identifier)
    if before["status"] == "publish":
        return _write(_draft_output(before), "website.publish", replayed=True)
    if before["status"] == "future":
        raise TargetError(
            "conflict", "none", False, "a person scheduled the post; it is not published now"
        )
    written = await _request(
        config, call, "POST", f"posts/{identifier}", body={"status": "publish"}
    )
    return _write(_draft_output(post_output(written)), "website.publish", replayed=False)


OPERATIONS = {
    "website.posts.read": read,
    "website.posts.draft": draft,
    "website.posts.publish": publish,
}
