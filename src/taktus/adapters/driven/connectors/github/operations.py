"""What each operation does, and how a repeat is recognised.

Every outward operation here is `marked`: the idempotency key goes into the body of the record
as an HTML comment, invisible when rendered, and the operation looks for that mark **before**
acting. The connector keeps no memory of what it did; the target system does, and that memory
survives a restart of the connector — which is the point (README §4 of the contract).

Where the lookup is exact and where it is bounded is stated per operation. A pull request is
found by its head branch, which the service keeps unique among open pull requests. An issue is
found among the most recently created ones, a comment among all comments of its issue, page by
page. A pipeline dispatch is found by nothing: the service answers with no identifier, which is
why that operation declares `idempotency: none`.

Every function takes the service, the operation's input and the idempotency key, and returns an
`Outcome`: the operation's output and the effect report. Faults of the service arrive as
`TargetError`. Input the operation cannot use is an `invalid` error before any request is made.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from taktus.adapters.driven.connectors.github.api import Api, TargetError, digest_of

type Json = dict[str, Any]

MARK = re.compile(r"<!-- taktus-idempotency-key ([A-Za-z0-9_.:-]{16,128}) -->")
RECENT = 100  # how many of the most recently created issues a repeat is looked for in
MAX_PAGES = 20  # how many pages of comments a repeat is looked for in


@dataclass(frozen=True)
class Outcome:
    output: Json
    effect: Json


def marked(body: str, key: str) -> str:
    return f"{body.rstrip()}\n\n<!-- taktus-idempotency-key {key} -->\n"


def mark_of(text: str | None) -> str | None:
    match = MARK.search(text or "")
    return match.group(1) if match else None


def read_effect() -> Json:
    return {"kind": "read"}


def write_effect(records: list[Json], digest: str, *, replayed: bool) -> Json:
    return {"kind": "write", "replayed": replayed, "records": records, "content_digest": digest}


def invalid(detail: str) -> TargetError:
    return TargetError("invalid", "none", False, detail)


def _int(input: Json, name: str) -> int:
    value = input.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise invalid(f"{name} must be a positive integer")
    return value


def _str(input: Json, name: str, *, optional: bool = False) -> str:
    value = input.get(name)
    if value is None and optional:
        return ""
    if not isinstance(value, str) or (not value and not optional):
        raise invalid(f"{name} must be a non-empty string")
    return value


# --- shapes of what comes back ---------------------------------------------------------------


def _account(user: Any) -> Json:
    if not isinstance(user, dict):
        return {"account": "", "kind": "person"}
    kind = "automation" if str(user.get("type", "")).lower() == "bot" else "person"
    return {"account": str(user.get("id", "")), "kind": kind}


def issue_output(issue: Json) -> Json:
    return {
        "number": int(issue["number"]),
        "title": str(issue.get("title", "")),
        "body": str(issue.get("body") or ""),
        "state": str(issue.get("state", "")),
        "url": str(issue.get("html_url", "")),
        "author": _account(issue.get("user")),
        "created_at": str(issue.get("created_at", "")),
        "is_pull_request": "pull_request" in issue,
    }


def pull_output(pull: Json) -> Json:
    return {
        **issue_output(pull),
        "head": str(pull.get("head", {}).get("ref", "")),
        "base": str(pull.get("base", {}).get("ref", "")),
        "merged": bool(pull.get("merged", False)),
    }


def comment_output(comment: Json) -> Json:
    return {
        "id": str(comment["id"]),
        "body": str(comment.get("body") or ""),
        "url": str(comment.get("html_url", "")),
        "author": _account(comment.get("user")),
        "created_at": str(comment.get("created_at", "")),
    }


def run_output(run: Json) -> Json:
    return {
        "id": str(run["id"]),
        "name": str(run.get("name", "")),
        "status": str(run.get("status", "")),
        "conclusion": run.get("conclusion"),
        "url": str(run.get("html_url", "")),
        "created_at": str(run.get("created_at", "")),
    }


# --- reads ------------------------------------------------------------------------------------


async def read_issue(api: Api, input: Json, key: str) -> Outcome:
    number = _int(input, "number")
    issue = await api.get(api.repo(f"issues/{number}"))
    return Outcome(issue_output(issue), read_effect())


async def read_pull_request(api: Api, input: Json, key: str) -> Outcome:
    number = _int(input, "number")
    pull = await api.get(api.repo(f"pulls/{number}"))
    return Outcome(pull_output(pull), read_effect())


async def read_pipeline_run(api: Api, input: Json, key: str) -> Outcome:
    run_id = _str(input, "run")
    if not run_id.isdigit():
        raise invalid("run must be the numeric id of a pipeline run")
    run = await api.get(api.repo(f"actions/runs/{run_id}"))
    return Outcome(run_output(run), read_effect())


async def list_comments(api: Api, input: Json, key: str) -> Outcome:
    number = _int(input, "number")
    comments = [comment_output(c) for c in await _all_comments(api, number)]
    return Outcome({"number": number, "comments": comments}, read_effect())


async def _all_comments(api: Api, number: int) -> list[Json]:
    page, next_url = await api.get_page(api.repo(f"issues/{number}/comments"), {"per_page": 100})
    comments: list[Json] = list(page)
    pages = 1
    while next_url and pages < MAX_PAGES:
        page, next_url = await api.get_url(next_url)
        comments.extend(page)
        pages += 1
    return comments


# --- writes: marked ---------------------------------------------------------------------------


async def open_pull_request(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the service keeps at most one open pull request per head branch, so the head is
    the exact index. A pull request for that head that carries our mark is ours, replayed; one
    that carries another mark, or none, is somebody else's and the operation ends in `conflict`
    — as it would anyway, since the service refuses the second one."""
    head = _str(input, "head")
    base = _str(input, "base")
    title = _str(input, "title")
    body = marked(_str(input, "body", optional=True), key)
    request = {"title": title, "head": head, "base": base, "body": body}
    digest = digest_of(request)
    label = head if ":" in head else f"{api.owner}:{head}"
    existing = await api.get(api.repo("pulls"), {"head": label, "state": "all"})
    for pull in existing:
        if mark_of(pull.get("body")) == key:
            return Outcome(
                pull_output(pull), write_effect(_pull_records(pull), digest, replayed=True)
            )
    created = await api.post(api.repo("pulls"), request)
    return Outcome(
        pull_output(created), write_effect(_pull_records(created), digest, replayed=False)
    )


def _pull_records(pull: Json) -> list[Json]:
    return [
        {"kind": "vcs.pullrequest", "id": str(pull["number"]), "url": str(pull.get("html_url", ""))}
    ]


async def create_issue(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the RECENT most recently created issues, by mark. Bounded, and stated so: a repeat
    that arrives after RECENT other issues were opened in between is not recognised. The
    service's search index would widen the window but lags by minutes, which is worse than a
    bound that is exact."""
    title = _str(input, "title")
    body = marked(_str(input, "body", optional=True), key)
    request: Json = {"title": title, "body": body}
    labels = input.get("labels")
    if labels is not None:
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise invalid("labels must be a list of strings")
        request["labels"] = labels
    digest = digest_of(request)
    recent = await api.get(
        api.repo("issues"),
        {"state": "all", "sort": "created", "direction": "desc", "per_page": RECENT},
    )
    for issue in recent:
        if "pull_request" not in issue and mark_of(issue.get("body")) == key:
            return Outcome(
                issue_output(issue), write_effect(_issue_records(issue), digest, replayed=True)
            )
    created = await api.post(api.repo("issues"), request)
    return Outcome(
        issue_output(created), write_effect(_issue_records(created), digest, replayed=False)
    )


def _issue_records(issue: Json) -> list[Json]:
    return [{"kind": "issue", "id": str(issue["number"]), "url": str(issue.get("html_url", ""))}]


async def create_comment(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: every comment of the issue, page by page, by mark. Exact up to MAX_PAGES pages of
    a hundred comments."""
    number = _int(input, "number")
    body = marked(_str(input, "body"), key)
    request = {"body": body}
    digest = digest_of(request)
    for comment in await _all_comments(api, number):
        if mark_of(comment.get("body")) == key:
            return Outcome(
                comment_output(comment),
                write_effect(_comment_records(comment, number), digest, replayed=True),
            )
    created = await api.post(api.repo(f"issues/{number}/comments"), request)
    return Outcome(
        comment_output(created),
        write_effect(_comment_records(created, number), digest, replayed=False),
    )


def _comment_records(comment: Json, number: int) -> list[Json]:
    return [
        {
            "kind": "comment",
            "id": f"{number}#{comment['id']}",
            "url": str(comment.get("html_url", "")),
        }
    ]


# --- writes: none -----------------------------------------------------------------------------


async def trigger_pipeline(api: Api, input: Json, key: str) -> Outcome:
    """No lookup is possible: the dispatch answers 204 with no run identifier, and the key can
    be passed as an input only where the workflow declares one. The record names the workflow
    and the ref; `replayed` is always false, and Taktus never repeats this call on its own."""
    workflow = _str(input, "workflow")
    ref = _str(input, "ref")
    request: Json = {"ref": ref}
    inputs = input.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            raise invalid("inputs must be an object")
        request["inputs"] = inputs
    digest = digest_of(request)
    await api.post(api.repo(f"actions/workflows/{workflow}/dispatches"), request)
    records = [{"kind": "pipeline.dispatch", "id": f"{workflow}@{ref}"}]
    return Outcome(
        {"workflow": workflow, "ref": ref, "accepted": True},
        write_effect(records, digest, replayed=False),
    )


type Operation = Callable[[Api, Json, str], Awaitable[Outcome]]

OPERATIONS: dict[str, Operation] = {
    "repository.issues.read": read_issue,
    "repository.issues.create": create_issue,
    "repository.pullrequests.read": read_pull_request,
    "repository.pullrequests.open": open_pull_request,
    "repository.pipelines.read": read_pipeline_run,
    "repository.pipelines.trigger": trigger_pipeline,
    "repository.comments.list": list_comments,
    "repository.comments.create": create_comment,
}
