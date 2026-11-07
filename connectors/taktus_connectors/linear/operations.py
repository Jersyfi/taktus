"""How the tasks are asked and their answers read (ADR-0209).

The API is one GraphQL endpoint, `POST /graphql`. A personal API key is sent as the
`Authorization` header itself, without a prefix, as the API's documentation states it. The
connector sends four fixed documents, each with its variables:

- `issues(filter:, first:, after:)` for the open tasks: the filter keeps the states whose type
  is neither `completed` nor `canceled`, and, with `overdue_by_days`, a `dueDate` at most that
  many days before today. The answer is a Relay connection: `nodes` and `pageInfo` with
  `hasNextPage` and `endCursor`, followed with `after` up to 100 pages of 50.
- `issue(id:)` for one task, by its identifier or its key (`ENG-123`).
- `issue(id:) { comments }` for the reminders written already.
- `commentCreate(input: {issueId, body})` for a reminder.

Each task is reduced to `{id, key, title, due, days_overdue, state, created_at, updated_at,
url}`. Its assignee, its creator and its description are never asked: a reminder reaches the
assignee through the tracker's own notification, and no count is ever made per person
(principle 14, ADR-0015). `days_overdue` is the whole days from the due date to today in UTC,
by the connector's clock; null without a due date, never negative.

**The mark.** A reminder's last line is `Taktus reference: <idempotency key>`. Before writing,
the connector reads the task's comments; one whose body carries the line is the original, and
nothing is written again.

How the API's answers map to the contract's causes. The API answers a GraphQL error in the body
with `errors`, each with `extensions`, often under HTTP 200 with partial data; its documentation
names no status for a refused key, so the connector reads the error's code as well as the
status:

| Answer | Cause |
|---|---|
| 401, or an error whose code or type names authentication | `unauthenticated` |
| 403, or an error whose code names `FORBIDDEN` | `forbidden` |
| 429, or the code `RATELIMITED`; 5xx; a refused or timed-out connection | `unavailable`, retryable |
| any other GraphQL error: an unknown task, a filter refused | `invalid` |
| a timeout or an unreadable answer on the write | `unknown`, effect `unknown`: a repeat finds the mark |
| any other status, a body that is not the API's | `unexpected` |

The API's own message stays out of `detail`: only its code is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.linear.app"
LIMIT = 500
MAX_LIMIT = 5000
PAGE = 50
MAX_PAGES = 100
MAX_TEXT = 4000
CLOSED = ["completed", "canceled"]
IDENTIFIER = re.compile(r"^([0-9a-fA-F-]{36}|[A-Z][A-Z0-9]{0,9}-[0-9]{1,9})$")
MARK = "Taktus reference: "

TASK_FIELDS = "id identifier title dueDate url createdAt updatedAt state { name type }"
LIST = (
    "query OpenTasks($filter: IssueFilter, $first: Int, $after: String) {"
    f" issues(filter: $filter, first: $first, after: $after) {{ nodes {{ {TASK_FIELDS} }}"
    " pageInfo { hasNextPage endCursor } } }"
)
READ = f"query Task($id: String!) {{ issue(id: $id) {{ {TASK_FIELDS} }} }}"
COMMENTS = (
    "query TaskComments($id: String!, $after: String) { issue(id: $id) { id"
    " comments(first: 50, after: $after) { nodes { id body }"
    " pageInfo { hasNextPage endCursor } } } }"
)
REMIND = (
    "mutation Remind($input: CommentCreateInput!) {"
    " commentCreate(input: $input) { success comment { id } } }"
)


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the product's own, or a fake's."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def today() -> date:
    return datetime.now(UTC).date()


def _codes(body: Any) -> list[str]:
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list):
        return []
    codes = []
    for error in errors:
        extensions = error.get("extensions") if isinstance(error, dict) else None
        if isinstance(extensions, dict):
            for field in ("code", "type"):
                if isinstance(extensions.get(field), str):
                    codes.append(extensions[field].upper().replace(" ", "_"))
                    break
            else:
                codes.append("UNKNOWN")
        else:
            codes.append("UNKNOWN")
    return codes


async def _graphql(
    config: Config, call: Call, document: str, variables: Json, *, writing: bool = False
) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": call.token, "Content-Type": "application/json"},
        ) as client:
            response = await client.post(
                "/graphql", json={"query": document, "variables": variables}
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the tracker could not be reached: {type(error).__name__}") from error
    except httpx.TimeoutException as error:
        if writing:
            raise TargetError(
                "unknown", "unknown", False, "the tracker did not answer the write in time"
            ) from error
        raise unavailable(f"the tracker did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the key among it.
        raise unavailable(f"the tracker could not be reached: {type(error).__name__}") from error
    status = response.status_code
    try:
        body: Any = response.json()
    except ValueError:
        body = None
    codes = _codes(body)
    named = " ".join(codes)
    if status == 401 or "AUTHENTICATION" in named:
        raise TargetError("unauthenticated", "none", False, "the tracker does not admit the key")
    if status == 403 or "FORBIDDEN" in named:
        raise TargetError("forbidden", "none", False, "the key may not do this")
    if status == 429 or "RATELIMITED" in named or status >= 500:
        raise unavailable(f"the tracker answered {status} {named}".rstrip())
    if codes:
        raise invalid(f"the tracker refused the request: {named}")
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        if writing and status == 200:
            raise TargetError("unknown", "unknown", False, "the tracker answered unreadably")
        raise _unexpected(f"the tracker answered {status} with a body it does not use")
    data: Json = body["data"]
    return data


def _due(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def task(node: Any) -> Json:
    """One task in the contract's shape, from the API's node."""
    if not isinstance(node, dict) or not isinstance(node.get("id"), str):
        raise _unexpected("a task has no identifier")
    state = node.get("state") if isinstance(node.get("state"), dict) else {}
    due = _due(node.get("dueDate"))
    overdue = max((today() - due).days, 0) if due is not None else None
    return {
        "id": node["id"],
        "key": node.get("identifier"),
        "title": node.get("title") if isinstance(node.get("title"), str) else "",
        "due": due.isoformat() if due is not None else None,
        "days_overdue": overdue,
        "state": state.get("name"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "url": node.get("url"),
        "open": state.get("type") not in CLOSED,
    }


def _identifier(input: Json) -> str:
    value = input.get("id")
    if not isinstance(value, str) or IDENTIFIER.match(value) is None:
        raise invalid("id must be a task's identifier or its key, such as ENG-123")
    return value


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    overdue = input.get("overdue_by_days")
    filter_: Json = {"state": {"type": {"nin": CLOSED}}}
    if overdue is not None:
        if isinstance(overdue, bool) or not isinstance(overdue, int) or not 0 <= overdue <= 3650:
            raise invalid("overdue_by_days must be a whole number from 0 to 3650")
        filter_["dueDate"] = {"lte": (today() - timedelta(days=overdue)).isoformat()}
    read: list[Json] = []
    after: str | None = None
    more = True
    for _ in range(MAX_PAGES):
        variables: Json = {"filter": filter_, "first": min(PAGE, limit - len(read))}
        if after is not None:
            variables["after"] = after
        data = await _graphql(config, call, LIST, variables)
        issues = data.get("issues")
        nodes = issues.get("nodes") if isinstance(issues, dict) else None
        page = issues.get("pageInfo") if isinstance(issues, dict) else None
        if not isinstance(nodes, list) or not isinstance(page, dict):
            raise _unexpected("the answer is not a connection of tasks")
        read.extend(task(node) for node in nodes)
        more = bool(page.get("hasNextPage"))
        after = page.get("endCursor") if isinstance(page.get("endCursor"), str) else None
        if not more or not nodes or after is None or len(read) >= limit:
            break
    items = [{k: v for k, v in t.items() if k != "open"} for t in read[:limit]]
    return Outcome(output={"items": items, "complete": not more}, effect={"kind": "read"})


async def read(config: Config, call: Call, input: Json) -> Outcome:
    data = await _graphql(config, call, READ, {"id": _identifier(input)})
    if not isinstance(data.get("issue"), dict):
        raise invalid("the tracker knows no such task")
    return Outcome(output=task(data["issue"]), effect={"kind": "read"})


async def _reminded(config: Config, call: Call, identifier: str, key: str) -> str | None:
    """The comment that carries the key, if one does."""
    after: str | None = None
    for _ in range(MAX_PAGES):
        variables: Json = {"id": identifier}
        if after is not None:
            variables["after"] = after
        data = await _graphql(config, call, COMMENTS, variables)
        issue = data.get("issue")
        if not isinstance(issue, dict):
            raise invalid("the tracker knows no such task")
        comments = issue.get("comments") if isinstance(issue.get("comments"), dict) else {}
        nodes = comments.get("nodes")
        if not isinstance(nodes, list):
            raise _unexpected("the answer is not a connection of comments")
        for node in nodes:
            body = node.get("body") if isinstance(node, dict) else None
            if isinstance(body, str) and f"{MARK}{key}" in body:
                return str(node.get("id"))
        page = comments.get("pageInfo") if isinstance(comments.get("pageInfo"), dict) else {}
        after = page.get("endCursor") if isinstance(page.get("endCursor"), str) else None
        if not page.get("hasNextPage") or after is None:
            return None
    return None


async def remind(config: Config, call: Call, input: Json) -> Outcome:
    identifier = _identifier(input)
    text = input.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise invalid(f"text must be the reminder, 1 to {MAX_TEXT} characters")
    found = await _reminded(config, call, identifier, call.key)
    if found is not None:
        return _written(identifier, found, replayed=True)
    body = f"{text.rstrip()}\n\n{MARK}{call.key}"
    data = await _graphql(
        config,
        call,
        REMIND,
        {"input": {"issueId": identifier, "body": body}},
        writing=True,
    )
    made = data.get("commentCreate")
    comment = made.get("comment") if isinstance(made, dict) else None
    if not isinstance(made, dict) or not made.get("success") or not isinstance(comment, dict):
        raise TargetError("unknown", "unknown", False, "the tracker did not confirm the comment")
    return _written(identifier, str(comment.get("id")), replayed=False)


def _written(task_id: str, comment: str, *, replayed: bool) -> Outcome:
    return Outcome(
        output={"task": task_id, "comment": comment},
        effect={
            "kind": "write",
            "replayed": replayed,
            "records": [{"kind": "task.comment", "id": f"{task_id}/{comment}"}],
        },
    )


OPERATIONS = {
    "tasks.items.list": list_,
    "tasks.items.read": read,
    "tasks.items.remind": remind,
}
