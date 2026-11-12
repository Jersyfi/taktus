"""How the helpdesk's tickets are asked, and their answers read (ADR-0205).

Every request goes to `--target`, the account's own address (`https://<domain>.freshdesk.com`),
under `/api/v2/`. The requesting identity's credential is its API key, sent as HTTP Basic with
the key as the user name and `X` as the password, as the API's authentication section states.

**Reading.** The ticket list is read by page: `per_page=100`, `page=1, 2, …`, newest change
first (`order_by=updated_at`), while the answer's `Link` header names a next page, up to 10
pages. The API lists only the tickets created in the past 30 days unless asked otherwise; the
connector asks no more, and says so. The list has no status filter for a status of the API's
own; the connector keeps the tickets of the status asked. A ticket's conversations are read 30
to a page, the API's size, while a page is full. A ticket is reduced to the shape the other
helpdesk connector answers, so that one process runs on either: the status in that connector's
words (2 open, 3 pending, 4 solved, 5 closed; any other number `other`), the requester by
identifier, never a name or an address.

**The mark.** An internal note ends with the paragraph `[taktus:<idempotency key>]`. Before
writing, the connector reads the ticket's conversations: one that carries the key is the
original, and nothing is written again. Closing a ticket sets a tag and the status resolved;
the tag is its own mark.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a request the API refuses | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403: the identity may not do this | `forbidden` |
| 404: no such ticket | `not_found` |
| 409: the record changed at the same moment | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat with the key finds it |
| any other status, a body that is not the API's | `unexpected` |

The API's own message stays out of `detail`: only the status and its error codes are reported.
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

PER_PAGE = 100
CONVERSATIONS_PAGE = 30
MAX_PAGES = 10
LIMIT = 100
MAX_LIMIT = 1000
MAX_WITH_COMMENTS = 25
STATUS_NAMES = {2: "open", 3: "pending", 4: "solved", 5: "closed"}
SOLVED = 4
FILTERS = frozenset({"new", "open", "pending", "hold", "solved", "closed", "unsolved", "all"})
UNSOLVED = frozenset({"new", "open", "pending", "hold"})
IDENTIFIER = re.compile(r"^[1-9][0-9]{0,18}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')
MAX_TEXT = 60_000


@dataclass(frozen=True)
class Config:
    target: str
    """The account's address, `https://<domain>.freshdesk.com`, or a fake's."""
    timeout: float = 30.0


def mark(key: str) -> str:
    return f"[taktus:{key}]"


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _codes(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list):
        code = body.get("code") if isinstance(body, dict) else None
        return code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,40}", code) else ""
    codes = {
        str(e["code"])
        for e in errors
        if isinstance(e, dict)
        and isinstance(e.get("code"), str)
        and re.fullmatch(r"[a-z_]{1,40}", e["code"])
    }
    return ",".join(sorted(codes))


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    params: Json | None = None,
    body: Json | None = None,
) -> tuple[Any, str | None]:
    """The answer's body and the next page its `Link` header names, if any."""
    writing = method != "GET"
    pair = base64.b64encode(f"{call.token}:X".encode()).decode("ascii")
    headers = {"Authorization": f"Basic {pair}", "Accept": "application/json"}
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
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the helpdesk could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 201):
        try:
            answer = response.json()
        except ValueError as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the write was answered unreadably"
                ) from error
            raise _unexpected("the helpdesk answered with a body it does not use") from error
        found = NEXT.search(response.headers.get("link", ""))
        return answer, found.group(1) if found else None
    codes = _codes(response)
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the helpdesk does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "no such ticket in the helpdesk")
    if status == 409:
        raise TargetError("conflict", "none", False, "the record changed at the same moment")
    if status == 400:
        raise invalid(f"the helpdesk refused the request: {status} {codes}".rstrip())
    if status == 429 or status >= 500:
        raise unavailable(f"the helpdesk answered {status}")
    raise _unexpected(f"the helpdesk answered {status} {codes}".rstrip())


def _identifier(input: Json) -> str:
    value = input.get("id")
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid("id must be a ticket's number")
    return value


def _ticket(record: Any) -> Json:
    if not isinstance(record, dict) or not isinstance(record.get("id"), int):
        raise _unexpected("a record is not a ticket")
    status = record.get("status")
    tags = _items(record.get("tags"))
    requester = record.get("requester_id")
    description = record.get("description_text")
    return {
        "id": str(record["id"]),
        "subject": record.get("subject") if isinstance(record.get("subject"), str) else "",
        "description": description if isinstance(description, str) else "",
        "status": STATUS_NAMES.get(status, "other") if isinstance(status, int) else "other",
        "requester": str(requester) if isinstance(requester, int) else None,
        "tags": [str(t) for t in tags],
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _comment(record: Any, requester: str | None) -> Json:
    if not isinstance(record, dict):
        raise _unexpected("a conversation is not an object")
    text = record.get("body_text")
    author = record.get("user_id")
    return {
        "id": str(record.get("id")),
        "text": text if isinstance(text, str) else "",
        "public": not bool(record.get("private")),
        "from_requester": bool(record.get("incoming"))
        or (requester is not None and str(author) == requester),
        "created_at": record.get("created_at"),
    }


async def _comments(config: Config, call: Call, ticket: Json) -> list[Json]:
    read: list[Json] = []
    for page in range(1, MAX_PAGES + 1):
        answer, _ = await _request(
            config, call, "GET", f"/api/v2/tickets/{ticket['id']}/conversations",
            params={"page": page},
        )  # fmt: skip
        if not isinstance(answer, list):
            raise _unexpected("the conversations are not a list")
        read.extend(_comment(r, ticket["requester"]) for r in answer)
        if len(answer) < CONVERSATIONS_PAGE:
            break
    return read


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
    more = True
    for page in range(1, MAX_PAGES + 1):
        params: Json = {
            "per_page": PER_PAGE,
            "page": page,
            "order_by": "updated_at",
            "order_type": "desc",
        }
        if with_comments:
            params["include"] = "description"
        answer, following = await _request(config, call, "GET", "/api/v2/tickets", params=params)
        if not isinstance(answer, list):
            raise _unexpected("the answer is not a list of tickets")
        for ticket in (_ticket(r) for r in answer):
            wanted = (
                status == "all"
                or ticket["status"] == status
                or (status == "unsolved" and ticket["status"] in UNSOLVED)
            )
            if wanted and len(kept) < limit:
                kept.append(ticket)
        more = following is not None
        if not more or len(kept) >= limit:
            break
    if with_comments:
        for ticket in kept:
            ticket["comments"] = await _comments(config, call, ticket)
    return Outcome({"tickets": kept, "complete": not more}, {"kind": "read"})


async def _read(config: Config, call: Call, identifier: str) -> Json:
    answer, _ = await _request(config, call, "GET", f"/api/v2/tickets/{identifier}")
    ticket = _ticket(answer)
    ticket["comments"] = await _comments(config, call, ticket)
    return ticket


async def read_ticket(config: Config, call: Call, input: Json) -> Outcome:
    return Outcome(await _read(config, call, _identifier(input)), {"kind": "read"})


def _written(output: Json, kind: str, identifier: str, replayed: bool) -> Outcome:
    records = [{"kind": kind, "id": identifier}]
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


def _html(text: str) -> str:
    return "".join(f"<p>{html.escape(part)}</p>" for part in text.split("\n") if part.strip())


async def note(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise invalid(f"text must be a text of 1 to {MAX_TEXT} characters")
    record = f"{identifier}@{hashlib.sha256(call.key.encode('utf-8')).hexdigest()[:16]}"
    ticket = await _read(config, call, identifier)
    output = {"ticket": identifier}
    if any(mark(call.key) in c["text"] for c in ticket["comments"]):
        return _written(output, "helpdesk.note", record, replayed=True)
    body = {"body": _html(f"{text}\n{mark(call.key)}"), "private": True}
    await _request(config, call, "POST", f"/api/v2/tickets/{identifier}/notes", body=body)
    return _written(output, "helpdesk.note", record, replayed=False)


async def close(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    tag = input.get("tag")
    if not isinstance(tag, str) or TAG.match(tag) is None:
        raise invalid("tag must be lower case letters, digits, dashes and underscores")
    answer, _ = await _request(config, call, "GET", f"/api/v2/tickets/{identifier}")
    ticket = _ticket(answer)
    output = {"ticket": identifier, "tag": tag, "previous": ticket["status"]}
    record = f"{identifier}#{tag}"
    if tag in ticket["tags"] and ticket["status"] in ("solved", "closed"):
        return _written(output, "helpdesk.closed", record, replayed=True)
    # The tags it has are sent with the new one: the update is not documented to add them.
    tags = [*ticket["tags"], *([] if tag in ticket["tags"] else [tag])]
    body = {"status": SOLVED, "tags": tags}
    await _request(config, call, "PUT", f"/api/v2/tickets/{identifier}", body=body)
    return _written(output, "helpdesk.closed", record, replayed=False)


OPERATIONS = {
    "helpdesk.tickets.list": list_tickets,
    "helpdesk.tickets.read": read_ticket,
    "helpdesk.tickets.note": note,
    "helpdesk.tickets.close": close,
}
