"""How the helpdesk's tickets and the help centre's articles are asked, and their answers read
(ADR-0205).

Every request goes to `--target`, the account's own address (`https://<subdomain>.zendesk.com`),
under `/api/v2/`. The requesting identity's credential is a pair `<email>:<api token>`, sent as
HTTP Basic with the user name `<email>/token`, as the API's authentication page states.

**Reading.** A list is read by cursor: `page[size]=100`, then `page[after]` from
`meta.after_cursor` while `meta.has_more` holds, up to 100 pages. The ticket list has no status
filter (the API points to its search for that); the connector reads the tickets newest change
first (`sort=-updated_at`) and keeps those of the status asked. A ticket is reduced to what a
sorting or a drafting step needs: the requester by identifier, never a name or an address.

**The mark.** An internal note ends with the line `[taktus:<idempotency key>]`. Before writing,
the connector reads the ticket's comments: a comment that carries the key is the original, and
nothing is written again. Closing a ticket sets a tag and the status `solved`; the tag is its own
mark, as a number of replicas is the workload connector's: a ticket that carries the tag and is
solved already is not changed again. A draft article carries the label `taktus-<digest of the
key>`; a repeat finds it among the section's articles.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: a request the API refuses | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403: the identity may not do this | `forbidden` |
| 404: no such ticket, section or article | `not_found` |
| 409: the record changed at the same moment | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |

The API's own message stays out of `detail`: only the status and its `error` name are reported.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

PAGE = 100
MAX_PAGES = 100
LIMIT = 100
MAX_LIMIT = 1000
MAX_WITH_COMMENTS = 25
STATUSES = ("new", "open", "pending", "hold", "solved", "closed")
FILTERS = frozenset({*STATUSES, "unsolved", "all"})
UNSOLVED = frozenset({"new", "open", "pending", "hold"})
IDENTIFIER = re.compile(r"^[1-9][0-9]{0,18}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
LOCALE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
MAX_TEXT = 60_000


@dataclass(frozen=True)
class Config:
    target: str
    """The account's address, `https://<subdomain>.zendesk.com`, or a fake's."""
    timeout: float = 30.0


def mark(key: str) -> str:
    return f"[taktus:{key}]"


def label(key: str) -> str:
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _object(value: Any) -> Json:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _authorization(token: str) -> str:
    email, separator, secret = token.partition(":")
    if not separator or not email or not secret:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is no pair <email>:<api token>"
        )
    pair = f"{email}/token:{secret}".encode()
    return "Basic " + base64.b64encode(pair).decode("ascii")


def _kind(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, str) and re.fullmatch(r"[A-Za-z]{1,40}", error) else ""


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
    headers = {"Authorization": _authorization(call.token), "Accept": "application/json"}
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(method, path, params=params, json=body, headers=headers)
    except httpx.ConnectError as error:
        raise unavailable(f"the helpdesk could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the helpdesk did not answer the write in time"
            ) from error
        raise unavailable(f"the helpdesk did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the helpdesk could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            if writing:
                raise TargetError("unknown", "unknown", False, "the write was answered unreadably")
            raise _unexpected("the helpdesk answered with a body it does not use")
        return answer
    kind = _kind(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the helpdesk does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such record in the helpdesk")
    if status == 409:
        raise TargetError("conflict", "none", False, "the record changed at the same moment")
    if status in (400, 422):
        raise invalid(f"the helpdesk refused the request: {status} {kind}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the helpdesk answered {status}")
    raise _unexpected(f"the helpdesk answered {status} {kind}".rstrip())


async def _pages(
    config: Config, call: Call, path: str, key: str, limit: int, params: Json | None = None
) -> tuple[list[Json], bool]:
    """Every record of a cursor-paged list, up to `limit`; and whether every one was read."""
    read: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        query: Json = {**(params or {}), "page[size]": PAGE}
        if after is not None:
            query["page[after]"] = after
        page = await _request(config, call, "GET", path, params=query)
        records = page.get(key)
        meta = _object(page.get("meta"))
        if not isinstance(records, list):
            raise _unexpected(f"the answer carries no list of {key}")
        read.extend(r for r in records if isinstance(r, dict))
        more = bool(meta.get("has_more"))
        after = meta.get("after_cursor") if isinstance(meta.get("after_cursor"), str) else None
        if not more or after is None or len(read) >= limit:
            break
    return read[:limit], not more


def _identifier(input: Json, field: str = "id") -> str:
    value = input.get(field)
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid(f"{field} must be a record's number")
    return value


def _text(input: Json, field: str) -> str:
    value = input.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise invalid(f"{field} must be a text of 1 to {MAX_TEXT} characters")
    return value


def _ticket(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), int):
        raise _unexpected("a record is not a ticket")
    status = record.get("status")
    tags = _items(record.get("tags"))
    requester = record.get("requester_id")
    return {
        "id": str(record["id"]),
        "subject": record.get("subject") if isinstance(record.get("subject"), str) else "",
        "description": record.get("description")
        if isinstance(record.get("description"), str)
        else "",
        "status": status if status in STATUSES else "other",
        "requester": str(requester) if isinstance(requester, int) else None,
        "tags": [str(t) for t in tags],
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _comment(record: Json, requester: str | None) -> Json:
    body = record.get("plain_body") or record.get("body")
    author = record.get("author_id")
    return {
        "id": str(record.get("id")),
        "text": body if isinstance(body, str) else "",
        "public": bool(record.get("public")),
        "from_requester": requester is not None and str(author) == requester,
        "created_at": record.get("created_at"),
    }


async def _comments(config: Config, call: Call, ticket: Json) -> list[Json]:
    """The ticket's comments after its first, which is its description."""
    records, _ = await _pages(
        config, call, f"/api/v2/tickets/{ticket['id']}/comments", "comments", MAX_LIMIT
    )
    return [_comment(r, ticket["requester"]) for r in records[1:]]


def _limit(input: Json, most: int) -> int:
    limit = input.get("limit", min(LIMIT, most))
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= most:
        raise invalid(f"limit must be a whole number from 1 to {most}")
    return limit


async def list_tickets(config: Config, call: Call, input: Json) -> Outcome:
    status = input.get("status", "unsolved")
    if status not in FILTERS:
        raise invalid(f"status must be one of {', '.join(sorted(FILTERS))}")
    with_comments = input.get("with_comments", False)
    if not isinstance(with_comments, bool):
        raise invalid("with_comments must be true or false")
    limit = _limit(input, MAX_WITH_COMMENTS if with_comments else MAX_LIMIT)
    kept: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        query: Json = {"page[size]": PAGE, "sort": "-updated_at"}
        if after is not None:
            query["page[after]"] = after
        page = await _request(config, call, "GET", "/api/v2/tickets", params=query)
        records = page.get("tickets")
        meta = _object(page.get("meta"))
        if not isinstance(records, list):
            raise _unexpected("the answer carries no list of tickets")
        for ticket in (_ticket(r) for r in records):
            wanted = (
                status == "all"
                or ticket["status"] == status
                or (status == "unsolved" and ticket["status"] in UNSOLVED)
            )
            if wanted and len(kept) < limit:
                kept.append(ticket)
        more = bool(meta.get("has_more"))
        after = meta.get("after_cursor") if isinstance(meta.get("after_cursor"), str) else None
        if not more or after is None or len(kept) >= limit:
            break
    if with_comments:
        for ticket in kept:
            ticket["comments"] = await _comments(config, call, ticket)
    return Outcome({"tickets": kept, "complete": not more}, {"kind": "read"})


async def _read(config: Config, call: Call, identifier: str) -> Json:
    answer = await _request(config, call, "GET", f"/api/v2/tickets/{identifier}")
    ticket = _ticket(answer.get("ticket"))
    ticket["comments"] = await _comments(config, call, ticket)
    return ticket


async def read_ticket(config: Config, call: Call, input: Json) -> Outcome:
    return Outcome(await _read(config, call, _identifier(input)), {"kind": "read"})


def _written(output: Json, kind: str, identifier: str, replayed: bool) -> Outcome:
    records = [{"kind": kind, "id": identifier}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


async def note(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    text = _text(input, "text")
    record = f"{identifier}@{hashlib.sha256(call.key.encode('utf-8')).hexdigest()[:16]}"
    ticket = await _read(config, call, identifier)
    output = {"ticket": identifier}
    if any(mark(call.key) in c["text"] for c in ticket["comments"]):
        return _written(output, "helpdesk.note", record, replayed=True)
    body = {"ticket": {"comment": {"body": f"{text}\n\n{mark(call.key)}", "public": False}}}
    await _request(config, call, "PUT", f"/api/v2/tickets/{identifier}", body=body)
    return _written(output, "helpdesk.note", record, replayed=False)


async def close(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    tag = input.get("tag")
    if not isinstance(tag, str) or TAG.match(tag) is None:
        raise invalid("tag must be lower case letters, digits, dashes and underscores")
    answer = await _request(config, call, "GET", f"/api/v2/tickets/{identifier}")
    ticket = _ticket(answer.get("ticket"))
    output = {"ticket": identifier, "tag": tag, "previous": ticket["status"]}
    record = f"{identifier}#{tag}"
    if tag in ticket["tags"] and ticket["status"] in ("solved", "closed"):
        return _written(output, "helpdesk.closed", record, replayed=True)
    # `tags` replaces the ticket's tags on an update: the ones it has are sent with the new one.
    tags = [*ticket["tags"], *([] if tag in ticket["tags"] else [tag])]
    body = {"ticket": {"status": "solved", "tags": tags}}
    await _request(config, call, "PUT", f"/api/v2/tickets/{identifier}", body=body)
    return _written(output, "helpdesk.closed", record, replayed=False)


def _article(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), int):
        raise _unexpected("a record is not an article")
    labels = _items(record.get("label_names"))
    section = record.get("section_id")
    return {
        "id": str(record["id"]),
        "title": record.get("title") if isinstance(record.get("title"), str) else "",
        "section": str(section) if isinstance(section, int) else None,
        "draft": bool(record.get("draft")),
        "url": record.get("html_url"),
        "labels": [str(n) for n in labels],
        "updated_at": record.get("updated_at"),
    }


async def list_articles(config: Config, call: Call, input: Json) -> Outcome:
    limit = _limit(input, MAX_LIMIT)
    records, complete = await _pages(
        config, call, "/api/v2/help_center/articles", "articles", limit
    )
    output = {"articles": [_article(r) for r in records], "complete": complete}
    return Outcome(output, {"kind": "read"})


async def draft(config: Config, call: Call, input: Json) -> Outcome:
    section = _identifier(input, "section")
    title = _text(input, "title")
    if len(title) > 255:
        raise invalid("title must be at most 255 characters")
    body = _text(input, "body")
    locale = input.get("locale", "en-us")
    if not isinstance(locale, str) or LOCALE.match(locale) is None:
        raise invalid("locale must be a locale such as en-us")
    marker = label(call.key)
    path = f"/api/v2/help_center/sections/{section}/articles"
    existing, _ = await _pages(config, call, path, "articles", MAX_LIMIT)
    found = next(
        (a for a in map(_article, existing) if marker in a["labels"]),
        None,
    )
    if found is not None:
        output = {**found, "published": False}
        return _written(output, "helpcentre.article", found["id"], replayed=True)
    article = {
        "article": {
            "title": title,
            "body": body,
            "locale": locale,
            "draft": True,
            "label_names": [marker],
        },
        "notify_subscribers": False,
    }
    answer = await _request(config, call, "POST", path, body=article)
    made = _article(answer.get("article"))
    if not made["draft"]:
        raise _unexpected("the help centre created the article as published, not as a draft")
    output = {**made, "published": False}
    return _written(output, "helpcentre.article", made["id"], replayed=False)


OPERATIONS = {
    "helpdesk.tickets.list": list_tickets,
    "helpdesk.tickets.read": read_ticket,
    "helpdesk.tickets.note": note,
    "helpdesk.tickets.close": close,
    "helpcentre.articles.list": list_articles,
    "helpcentre.articles.draft": draft,
}
