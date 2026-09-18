"""What each operation does, and how a repeat is recognised.

Every outward operation here is `marked`: the idempotency key goes into the body of the record
as an HTML comment, invisible when rendered, and the operation looks for that mark **before**
acting. The connector keeps no memory of what it did; the target system does, and that memory
survives a restart of the connector — which is the point (README §4 of the contract).

Where the lookup is exact and where it is bounded is stated per operation. A pull request is
found by its head branch, which the service keeps unique among open pull requests. An issue is
found among the most recently created ones, a comment among all comments of its issue, page by
page. A branch is found by its name, and the mark at the head commit says whether it is ours. A
label is its own mark: the operation looks for the labels on the issue before adding any. A
pipeline dispatch is found by nothing: the service answers with no identifier, which is why
that operation declares `idempotency: none`.

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
TRAILER = re.compile(r"^Taktus-Idempotency-Key: ([A-Za-z0-9_.:-]{16,128})$", re.MULTILINE)
RECENT = 100  # how many of the most recently created issues a repeat is looked for in
MAX_PAGES = 20  # how many pages of comments a repeat is looked for in
MAX_RUNS = 50  # how many pipeline runs of one head are read
SHA = re.compile(r"^[0-9a-f]{40}$")
FILE_MODE = "100644"


@dataclass(frozen=True)
class Outcome:
    output: Json
    effect: Json


def marked(body: str, key: str) -> str:
    return f"{body.rstrip()}\n\n<!-- taktus-idempotency-key {key} -->\n"


def mark_of(text: str | None) -> str | None:
    match = MARK.search(text or "")
    return match.group(1) if match else None


def trailed(message: str, key: str) -> str:
    """A commit message with the key as a trailer: the mark in the form git keeps for
    metadata, readable in a log and found again by `trailer_of`."""
    return f"{message.rstrip()}\n\nTaktus-Idempotency-Key: {key}\n"


def trailer_of(message: str | None) -> str | None:
    match = TRAILER.search(message or "")
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


async def pipeline_status(api: Api, input: Json, key: str) -> Outcome:
    """The pipeline runs for the head of a branch, and one word for their state: `none` when
    there is no run for that head, `pending` while any is not completed, `success` when every
    completed one concluded success (or was skipped), `failure` otherwise. The verdict is the
    pipeline's, read from the service; nothing here judges the work."""
    ref = _str(input, "ref")
    if SHA.match(ref):
        sha = ref
    else:
        branch = await api.get(api.repo(f"branches/{ref}"))
        sha = str(branch.get("commit", {}).get("sha", ""))
        if not sha:
            raise TargetError("not_found", "none", False, f"branch {ref!r} has no head")
    listed = await api.get(api.repo("actions/runs"), {"head_sha": sha, "per_page": MAX_RUNS})
    runs = [run_output(r) for r in (listed or {}).get("workflow_runs", [])]
    workflow = input.get("workflow")
    if workflow is not None:
        if not isinstance(workflow, str) or not workflow:
            raise invalid("workflow must be a non-empty string")
        runs = [r for r in runs if r["name"] == workflow]
    return Outcome({"ref": ref, "sha": sha, "runs": runs, "state": _state_of(runs)}, read_effect())


def _state_of(runs: list[Json]) -> str:
    if not runs:
        return "none"
    if any(r["status"] != "completed" for r in runs):
        return "pending"
    if all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
        return "success"
    return "failure"


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


async def create_branch(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the branch by name, which the service keeps unique. The commit at its head
    carries our key as a trailer: ours, replayed. A branch of that name whose head carries
    another key, or none, is somebody else's, and the operation ends in `conflict` — the
    service would refuse the reference anyway. The files go into one commit on top of the base
    through the object interface: blobs, a tree, a commit, the reference. With no files, the
    commit is empty and still carries the mark; that is what makes a bare branch findable."""
    name = _str(input, "name")
    base = _str(input, "base")
    message = _str(input, "message", optional=True) or f"taktus: branch {name}"
    files = _files(input)
    deleted = _paths(input, "deleted")
    request: Json = {"name": name, "base": base, "message": message, "files": files}
    if deleted:
        request["deleted"] = deleted
    digest = digest_of(request)
    existing = await _ref(api, name)
    if existing is not None:
        head = await api.get(api.repo(f"git/commits/{existing}"))
        if trailer_of(head.get("message")) == key:
            output = _branch_output(api, name, existing, base, str(head.get("html_url", "")))
            return Outcome(output, write_effect(_branch_records(output), digest, replayed=True))
        raise TargetError(
            "conflict", "none", False, f"branch {name!r} exists and was not created for this step"
        )
    base_sha = await _ref(api, base)
    if base_sha is None:
        raise TargetError("not_found", "none", False, f"base branch {base!r} does not exist")
    base_commit = await api.get(api.repo(f"git/commits/{base_sha}"))
    tree_sha = str(base_commit.get("tree", {}).get("sha", ""))
    entries: list[Json] = []
    for file in files:
        blob = await api.post(
            api.repo("git/blobs"), {"content": file["content"], "encoding": file["encoding"]}
        )
        entries.append(
            {"path": file["path"], "mode": FILE_MODE, "type": "blob", "sha": str(blob["sha"])}
        )
    entries.extend(
        {"path": path, "mode": FILE_MODE, "type": "blob", "sha": None} for path in deleted
    )
    if entries:
        tree = await api.post(api.repo("git/trees"), {"base_tree": tree_sha, "tree": entries})
        tree_sha = str(tree["sha"])
    commit = await api.post(
        api.repo("git/commits"),
        {"message": trailed(message, key), "tree": tree_sha, "parents": [base_sha]},
    )
    sha = str(commit["sha"])
    await api.post(api.repo("git/refs"), {"ref": f"refs/heads/{name}", "sha": sha})
    output = _branch_output(api, name, sha, base, str(commit.get("html_url", "")))
    return Outcome(output, write_effect(_branch_records(output), digest, replayed=False))


async def _ref(api: Api, name: str) -> str | None:
    """The sha a branch points at, or None when there is no such branch."""
    try:
        ref = await api.get(api.repo(f"git/ref/heads/{name}"))
    except TargetError as error:
        if error.cause == "not_found":
            return None
        raise
    return str(ref.get("object", {}).get("sha", "")) or None


def _files(input: Json) -> list[Json]:
    raw = input.get("files")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise invalid("files must be a list of {path, content}")
    files: list[Json] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise invalid("files must be a list of {path, content}")
        path = entry.get("path")
        content = entry.get("content")
        encoding = entry.get("encoding", "utf-8")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise invalid("a file path is relative, non-empty and never leaves the tree")
        if not isinstance(content, str):
            raise invalid(f"the content of {path!r} must be a string")
        if encoding not in ("utf-8", "base64"):
            raise invalid(f"the encoding of {path!r} must be utf-8 or base64")
        files.append({"path": path, "content": content, "encoding": encoding})
    return files


def _paths(input: Json, name: str) -> list[str]:
    raw = input.get(name)
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) and x for x in raw):
        raise invalid(f"{name} must be a list of paths")
    return list(raw)


def _branch_output(api: Api, name: str, sha: str, base: str, commit_url: str) -> Json:
    return {
        "name": name,
        "sha": sha,
        "base": base,
        "url": f"{api.web}/{api.repository}/tree/{name}",
        "commit_url": commit_url,
    }


def _branch_records(output: Json) -> list[Json]:
    return [
        {"kind": "vcs.branch", "id": str(output["name"]), "url": str(output["url"])},
        {"kind": "vcs.commit", "id": str(output["sha"]), "url": str(output["commit_url"])},
    ]


async def set_labels(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the labels on the issue, which is the record this operation writes into. The mark
    is the label itself — a field the target keeps — so the lookup is by label, not by key: a
    repeat with any key that finds every requested label present adds nothing and reports
    `replayed`. Stated so, because it is weaker than a key in a body."""
    number = _int(input, "number")
    labels = _paths(input, "labels")
    if not labels:
        raise invalid("labels must name at least one label")
    request: Json = {"labels": labels}
    digest = digest_of(request)
    issue = await api.get(api.repo(f"issues/{number}"))
    present = {str(label.get("name", "")) for label in issue.get("labels", []) or []}
    records = [{"kind": "label", "id": f"{number}#{label}"} for label in labels]
    if set(labels) <= present:
        output = {"number": number, "labels": sorted(present)}
        return Outcome(output, write_effect(records, digest, replayed=True))
    updated = await api.post(api.repo(f"issues/{number}/labels"), request)
    names = sorted(str(label.get("name", "")) for label in (updated or []))
    return Outcome(
        {"number": number, "labels": names}, write_effect(records, digest, replayed=False)
    )


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
    "repository.pipelines.status": pipeline_status,
    "repository.pipelines.trigger": trigger_pipeline,
    "repository.comments.list": list_comments,
    "repository.comments.create": create_comment,
    "repository.branches.create": create_branch,
    "repository.labels.set": set_labels,
}
