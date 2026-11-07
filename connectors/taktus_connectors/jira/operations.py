"""How the issues are asked and their answers read (ADR-0209).

The REST API v3 of the site at `--target`, for the one project `--project` names. The
requesting identity's credential is a pair, `<e-mail>:<API token>`, sent as HTTP Basic
authentication, as the API states for a script.

- `GET /rest/api/3/search/jql` for the open issues: the JQL `project = "<KEY>" AND
  statusCategory != Done`, with `AND duedate <= "<date>"` for `overdue_by_days`, ordered by due
  date and key; `fields=summary,duedate,status,created,updated`; pages of 100 followed by
  `nextPageToken` until `isLast` or no token, up to 50 pages. The older `GET /rest/api/3/search`
  is not used.
- `GET /rest/api/3/issue/<KEY>` for one issue, with the same fields. An issue of another
  project is refused before the site is asked.
- `GET /rest/api/3/issue/<KEY>/comment` for the reminders written already, `startAt` and
  `maxResults`, and `POST` to the same path for a reminder, its body a document in the
  Atlassian Document Format, one paragraph per block of text.

Each issue is reduced to the shape of the `linear` connector: `{id, key, title, due,
days_overdue, state, created_at, updated_at, url}`, `id` and `key` both the issue's key, `url`
its page under `/browse/`. Its assignee, reporter and description are never asked (principle
14, ADR-0015). `days_overdue` is the whole days from the due date to today in UTC, by the
connector's clock.

**The mark.** A reminder's last paragraph is `Taktus reference: <idempotency key>`. Before
writing, the connector reads the issue's comments and the text of each; one that carries the
line is the original, and nothing is written again.

| Answer | Cause |
|---|---|
| 400, 404: a query refused, an issue the site does not know | `invalid` |
| 401: the pair is not admitted | `unauthenticated` |
| 403: the account may not do this | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable |
| a write timed out or answered unreadably | `unknown`, effect `unknown`; a repeat finds the mark |
| any other status, a body that is not the API's | `unexpected` |

The site's own messages (`errorMessages`, `errors`) stay out of `detail`.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

LIMIT = 500
MAX_LIMIT = 5000
PAGE = 100
MAX_PAGES = 50
MAX_TEXT = 4000
FIELDS = "summary,duedate,status,created,updated"
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-[0-9]{1,9}$")
MARK = "Taktus reference: "


@dataclass(frozen=True)
class Config:
    target: str
    """The site's address, `https://<site>.atlassian.net`, or a fake's."""
    project: str
    """The key of the one project the connector reads."""
    timeout: float = 30.0


def _obj(value: Any) -> Json:
    """The value when it is an object, else an empty one."""
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    """The value when it is a text, else None."""
    return value if isinstance(value, str) else None


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def today() -> date:
    return datetime.now(UTC).date()


def _authorization(token: str) -> str:
    if ":" not in token:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is not an e-mail and a token"
        )
    return "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")


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
    authorization = _authorization(call.token)
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": authorization, "Accept": "application/json"},
        ) as client:
            response = await client.request(method, path, params=params, json=body)
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
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            if writing:
                raise TargetError("unknown", "unknown", False, "the site answered unreadably")
            raise _unexpected("the site answered with a body it does not use")
        return answer
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the site does not admit the pair")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the account may not do this")
    if status == 429 or status >= 500:
        raise unavailable(f"the site answered {status}")
    if status in (400, 404):
        raise invalid(f"the site refused the request: {status}")
    raise _unexpected(f"the site answered {status}")


def _due(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def task(config: Config, issue: Any) -> Json:
    """One issue in the contract's shape, from the API's issue."""
    if not isinstance(issue, dict) or not isinstance(issue.get("key"), str):
        raise _unexpected("an issue has no key")
    fields = _obj(issue.get("fields"))
    status = _obj(fields.get("status"))
    category = _obj(status.get("statusCategory"))
    due = _due(fields.get("duedate"))
    return {
        "id": issue["key"],
        "key": issue["key"],
        "title": fields.get("summary") if isinstance(fields.get("summary"), str) else "",
        "due": due.isoformat() if due is not None else None,
        "days_overdue": max((today() - due).days, 0) if due is not None else None,
        "state": status.get("name"),
        "created_at": fields.get("created"),
        "updated_at": fields.get("updated"),
        "url": f"{config.target.rstrip('/')}/browse/{issue['key']}",
        "open": category.get("key") != "done",
    }


def _project(config: Config) -> str:
    if PROJECT.match(config.project) is None:
        raise invalid("the connector is configured with no valid project key")
    return config.project


def _key(config: Config, input: Json) -> str:
    value = input.get("id")
    if not isinstance(value, str) or KEY.match(value) is None:
        raise invalid("id must be an issue's key, such as OPS-123")
    if not value.startswith(f"{_project(config)}-"):
        raise invalid("the issue is not of the project the connector reads")
    return value


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    jql = f'project = "{_project(config)}" AND statusCategory != Done'
    overdue = input.get("overdue_by_days")
    if overdue is not None:
        if isinstance(overdue, bool) or not isinstance(overdue, int) or not 0 <= overdue <= 3650:
            raise invalid("overdue_by_days must be a whole number from 0 to 3650")
        jql += f' AND duedate <= "{(today() - timedelta(days=overdue)).isoformat()}"'
    jql += " ORDER BY duedate ASC, key ASC"
    read: list[Json] = []
    token: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        params: Json = {"jql": jql, "fields": FIELDS, "maxResults": min(PAGE, limit - len(read))}
        if token is not None:
            params["nextPageToken"] = token
        page = await _request(config, call, "GET", "/rest/api/3/search/jql", params=params)
        issues = page.get("issues")
        if not isinstance(issues, list):
            raise _unexpected("the answer is not a page of issues")
        read.extend(task(config, issue) for issue in issues)
        token = _str(page.get("nextPageToken"))
        more = token is not None and not page.get("isLast", False)
        if not more or not issues or len(read) >= limit:
            break
    items = [{k: v for k, v in t.items() if k != "open"} for t in read[:limit]]
    return Outcome(output={"items": items, "complete": not more}, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    key = _key(config, input)
    issue = await _request(
        config, call, "GET", f"/rest/api/3/issue/{key}", params={"fields": FIELDS}
    )
    return Outcome(output=task(config, issue), effect={"kind": "read"})


def text_of(node: Any) -> str:
    """The text of a document in the Atlassian Document Format: its text nodes, in order."""
    if isinstance(node, dict):
        own = _str(node.get("text")) or ""
        inner = "".join(text_of(child) for child in node.get("content") or [])
        return own + inner + ("\n" if node.get("type") == "paragraph" else "")
    if isinstance(node, list):
        return "".join(text_of(child) for child in node)
    return ""


def document(text: str) -> Json:
    """A text as a document: one paragraph per block separated by a blank line."""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": block}]} for block in blocks
        ],
    }


async def _reminded(config: Config, call: Call, key: str, mark: str) -> str | None:
    start = 0
    for _ in range(MAX_PAGES):
        page = await _request(
            config,
            call,
            "GET",
            f"/rest/api/3/issue/{key}/comment",
            params={"startAt": start, "maxResults": PAGE},
        )
        comments = page.get("comments")
        if not isinstance(comments, list):
            raise _unexpected("the answer is not a page of comments")
        for comment in comments:
            if isinstance(comment, dict) and f"{MARK}{mark}" in text_of(comment.get("body")):
                return str(comment.get("id"))
        start += len(comments)
        total = page.get("total")
        if not comments or not isinstance(total, int) or start >= total:
            return None
    return None


async def remind(config: Config, call: Call, input: Json) -> Outcome:
    key = _key(config, input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise invalid(f"text must be the reminder, 1 to {MAX_TEXT} characters")
    found = await _reminded(config, call, key, call.key)
    if found is not None:
        return _written(key, found, replayed=True)
    made = await _request(
        config,
        call,
        "POST",
        f"/rest/api/3/issue/{key}/comment",
        body={"body": document(f"{text.rstrip()}\n\n{MARK}{call.key}")},
    )
    if not isinstance(made.get("id"), str):
        raise TargetError("unknown", "unknown", False, "the site did not name the comment")
    return _written(key, made["id"], replayed=False)


def _written(key: str, comment: str, *, replayed: bool) -> Outcome:
    return Outcome(
        output={"task": key, "comment": comment},
        effect={
            "kind": "write",
            "replayed": replayed,
            "records": [{"kind": "task.comment", "id": f"{key}/{comment}"}],
        },
    )


OPERATIONS = {
    "tasks.items.list": list_,
    "tasks.items.read": read,
    "tasks.items.remind": remind,
}
