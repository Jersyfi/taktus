"""What each operation does, and how a repeat is recognised.

Every outward operation here is `marked`: the idempotency key goes into the body of the record
as an HTML comment, invisible when rendered, and the operation looks for that mark **before**
acting. The connector keeps no memory of what it did; the target system does, and that memory
survives a restart of the connector — which is the point (README §4 of the contract).

Where the lookup is exact and where it is bounded is stated per operation. A pull request is
found by its head branch, which the service keeps unique among open pull requests. An issue is
found among the most recently created ones and, above the newest number that list shows, by its
number, one by one; a comment among all comments of its issue, page by page. A branch is found
by its name, and the mark at the head commit says whether it is ours; so is any other
reference. `repository.branches.read` answers the same lookup without acting, so that a run
can see before it spends whether the branch it will create is free. A label is its own mark:
the operation looks for the labels on the issue before adding any, and before removing any.
A pipeline dispatch is found by nothing: the service answers with no identifier, which is why
that operation declares `idempotency: none`.

Every function takes the service, the operation's input and the idempotency key, and returns an
`Outcome`: the operation's output and the effect report. Faults of the service arrive as
`TargetError`. Input the operation cannot use is an `invalid` error before any request is made.

**A lookup reads only what the service answers consistently** (ADR-0024, amendment of
2026-10-12): a record the service has acknowledged must be found by the next request. A pull
request by its head, the comments of one issue, a reference, one issue by its number: each is
read as written. The list of a repository's issues is not: on 2026-10-12 an issue created a
second earlier was missing from it, and a repeat that relied on it opened a second issue.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from taktus_connectors.github.api import Api, TargetError, digest_of

type Json = dict[str, Any]

MARK = re.compile(r"<!-- taktus-idempotency-key ([A-Za-z0-9_.:-]{16,128}) -->")
TRAILER = re.compile(r"^Taktus-Idempotency-Key: ([A-Za-z0-9_.:-]{16,128})$", re.MULTILINE)
RECENT = 100  # how many of the most recently created issues a repeat is looked for in
PROBES = 20  # how many numbers above the newest listed one are read one by one
MAX_PAGES = 20  # how many pages of comments a repeat is looked for in
MAX_RUNS = 50  # how many pipeline runs of one head are read
SHA = re.compile(r"^[0-9a-f]{40}$")
FILE_MODE = "100644"
EXECUTABLE_MODE = "100755"
# A file keeps the mode it has in the base: an executable that a change touches stays
# executable, and a symbolic link stays a link (DEC-0020). Anything else the base carries —
# a submodule — cannot be written back as a blob, so such a path gets the plain file mode.
# A file whose input says `executable` gets that mode instead, whether the base has it or not
# (issue #28): `true` is 100755, `false` is 100644.
BLOB_MODES = frozenset({"100644", "100755", "120000"})


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
    milestone = issue.get("milestone")
    return {
        "number": int(issue["number"]),
        "title": str(issue.get("title", "")),
        "body": str(issue.get("body") or ""),
        "state": str(issue.get("state", "")),
        "url": str(issue.get("html_url", "")),
        "author": _account(issue.get("user")),
        "created_at": str(issue.get("created_at", "")),
        "updated_at": str(issue.get("updated_at") or issue.get("created_at", "")),
        "is_pull_request": "pull_request" in issue,
        # The labels by name, sorted; the milestone by its title, or null without one. What the
        # ready standard of a backlog reads besides the body (issue #70).
        "labels": sorted(str(label.get("name", "")) for label in issue.get("labels") or []),
        "milestone": str(milestone.get("title", "")) or None if milestone else None,
    }


def pull_output(pull: Json) -> Json:
    return {
        **issue_output(pull),
        "head": str(pull.get("head", {}).get("ref", "")),
        "head_sha": str(pull.get("head", {}).get("sha") or "") or None,
        "base": str(pull.get("base", {}).get("ref", "")),
        "draft": bool(pull.get("draft", False)),
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


async def list_issues(api: Api, input: Json, key: str) -> Outcome:
    """The repository's issues in one state — `open` unless `state` says `closed` or `all` —
    without pull requests, newest first, in the shape of `repository.issues.read`. Read page by
    page up to MAX_PAGES pages of 100; `complete` says whether every page was read, so that a
    reader that must see every open issue can refuse a reading that stopped short."""
    state = input.get("state", "open")
    if state not in ("open", "closed", "all"):
        raise invalid("state is open, closed or all")
    path = api.repo("issues")
    page, next_url = await api.get_page(path, {"state": state, "per_page": 100})
    found: list[Json] = list(page)
    pages = 1
    while next_url and pages < MAX_PAGES:
        page, next_url = await api.get_url(next_url)
        found.extend(page)
        pages += 1
    issues = [issue_output(item) for item in found if "pull_request" not in item]
    output = {"state": state, "issues": issues, "complete": next_url is None}
    return Outcome(output, read_effect())


def member_output(member: Json) -> Json:
    """What a collaborator list yields of one member: the account as the intake names a sender
    (its number), its login name, person or automation, and its role. Nothing else is kept."""
    return {
        **_account(member),
        "name": str(member.get("login", "")),
        "role": str(member.get("role_name", "")),
    }


async def list_members(api: Api, input: Json, key: str) -> Outcome:
    """The repository's collaborators, page by page up to MAX_PAGES pages of 100. The service
    asks the app for read access to the repository's metadata, nothing more (DEC-0127)."""
    page, next_url = await api.get_page(api.repo("collaborators"), {"per_page": 100})
    found: list[Json] = list(page)
    pages = 1
    while next_url and pages < MAX_PAGES:
        page, next_url = await api.get_url(next_url)
        found.extend(page)
        pages += 1
    output = {"members": [member_output(m) for m in found], "complete": next_url is None}
    return Outcome(output, read_effect())


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


async def read_file(api: Api, input: Json, key: str) -> Outcome:
    """One file at a ref. The ref — a branch name or a commit — is resolved to a commit first,
    and the file is read at that commit, so that what was read and where it was read agree
    even when the branch moves between the two requests; the output names the commit. The
    content is text when it decodes as UTF-8 and base64 otherwise, the shape a changeset uses.
    A path that names a directory, a link or a submodule is `invalid`: this reads files."""
    path = _tree_path(input.get("path"))
    ref = _str(input, "ref")
    commit = ref if SHA.match(ref) else await _ref(api, ref)
    if commit is None:
        raise TargetError("not_found", "none", False, f"ref {ref!r} is not a branch or a commit")
    found = await api.get(api.repo(f"contents/{quote(path)}"), {"ref": commit})
    if not isinstance(found, dict) or found.get("type") != "file":
        raise invalid(f"{path!r} at {ref!r} is not a file")
    raw = await _content_of(api, found)
    output: Json = {
        "path": path,
        "ref": ref,
        "commit": commit,
        "sha": str(found.get("sha", "")),
        "size": len(raw),
    }
    try:
        output |= {"content": raw.decode("utf-8"), "encoding": "utf-8"}
    except UnicodeDecodeError:
        output |= {"content": base64.b64encode(raw).decode(), "encoding": "base64"}
    return Outcome(output, read_effect())


MAX_FILES = 100
"""The most paths one `read_many` reads: one request each, besides the one that resolves the
ref."""


async def read_many(api: Api, input: Json, key: str) -> Outcome:
    """Several files at one ref, all at the same commit: the ref is resolved to a commit once,
    and every path is read at that commit, so that what a reader puts together from them is
    the repository as it was at one moment, even when the branch moves while it reads
    (ADR-0066). A path that names nothing at the commit, or no file, is answered with content
    `null`, never left out: the reader decides what a missing file means. The output names the
    commit and lists the files in the order of `paths`."""
    paths = [_tree_path(path) for path in _paths(input, "paths")]
    if not paths:
        raise invalid("paths names at least one file")
    if len(paths) > MAX_FILES:
        raise invalid(f"paths names {len(paths)} files; one call reads at most {MAX_FILES}")
    ref = _str(input, "ref")
    commit = ref if SHA.match(ref) else await _ref(api, ref)
    if commit is None:
        raise TargetError("not_found", "none", False, f"ref {ref!r} is not a branch or a commit")
    files: list[Json] = []
    for path in dict.fromkeys(paths):
        try:
            found = await api.get(api.repo(f"contents/{quote(path)}"), {"ref": commit})
        except TargetError as error:
            if error.cause != "not_found":
                raise
            found = None
        if not isinstance(found, dict) or found.get("type") != "file":
            files.append({"path": path, "content": None, "encoding": None})
            continue
        raw = await _content_of(api, found)
        try:
            files.append({"path": path, "content": raw.decode("utf-8"), "encoding": "utf-8"})
        except UnicodeDecodeError:
            encoded = base64.b64encode(raw).decode()
            files.append({"path": path, "content": encoded, "encoding": "base64"})
    output: Json = {"ref": ref, "commit": commit, "files": files}
    return Outcome(output, read_effect())


async def list_files(api: Api, input: Json, key: str) -> Outcome:
    """The entries of one directory at a ref, resolved to a commit first as `read_file` does:
    each with its name, its path and its type — `file`, `dir`, `symlink` or `submodule` —
    sorted by name. A path that names a file is `invalid`: this lists directories."""
    path = _tree_path(input.get("path"))
    ref = _str(input, "ref")
    commit = ref if SHA.match(ref) else await _ref(api, ref)
    if commit is None:
        raise TargetError("not_found", "none", False, f"ref {ref!r} is not a branch or a commit")
    found = await api.get(api.repo(f"contents/{quote(path)}"), {"ref": commit})
    if not isinstance(found, list):
        raise invalid(f"{path!r} at {ref!r} is not a directory")
    entries = sorted(
        (
            {
                "name": str(entry.get("name") or str(entry.get("path", "")).rsplit("/", 1)[-1]),
                "path": str(entry.get("path", "")),
                "type": str(entry.get("type", "")),
            }
            for entry in found
            if isinstance(entry, dict)
        ),
        key=lambda entry: entry["name"],
    )
    output = {"path": path, "ref": ref, "commit": commit, "entries": entries}
    return Outcome(output, read_effect())


async def _content_of(api: Api, found: Json) -> bytes:
    """The bytes of a file the contents interface answered with. A file above that
    interface's size limit comes without content (`encoding: none`) and is read as a blob."""
    content, encoding = found.get("content"), found.get("encoding")
    if encoding != "base64" or not isinstance(content, str):
        blob = await api.get(api.repo(f"git/blobs/{found.get('sha', '')}"))
        content, encoding = blob.get("content"), blob.get("encoding")
    if encoding != "base64" or not isinstance(content, str):
        raise TargetError("unavailable", "none", True, "the service sent no content")
    try:
        return base64.b64decode(content)
    except (ValueError, binascii.Error) as error:
        raise TargetError(
            "unavailable", "none", True, "the service sent content that is not base64"
        ) from error


def _tree_path(path: Any) -> str:
    """A path inside the repository's tree: relative, non-empty, never leaving it."""
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
        raise invalid("a file path is relative, non-empty and never leaves the tree")
    return path


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
    """Lookup, in two parts, by mark. First the RECENT most recently created issues, from the
    issue list. That list lags: an issue created seconds ago is not in it yet. So, second, every
    number above the newest one the list shows is read on its own, upwards, until the service
    answers that a number does not exist; one issue read by its number is answered as written.
    Bounded, and stated so: a repeat is not recognised after RECENT other issues and pull
    requests were opened in between, nor when more than PROBES were opened while the list
    lagged. The service's search index would widen the window but lags by minutes."""
    title = _str(input, "title")
    body = marked(_str(input, "body", optional=True), key)
    request: Json = {"title": title, "body": body}
    labels = input.get("labels")
    if labels is not None:
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise invalid("labels must be a list of strings")
        request["labels"] = labels
    digest = digest_of(request)
    found = await _issue_marked(api, key)
    if found is not None:
        return Outcome(
            issue_output(found), write_effect(_issue_records(found), digest, replayed=True)
        )
    created = await api.post(api.repo("issues"), request)
    return Outcome(
        issue_output(created), write_effect(_issue_records(created), digest, replayed=False)
    )


async def _issue_marked(api: Api, key: str) -> Json | None:
    """The issue that carries the key, among the recent ones and those the list does not show
    yet; None when there is none. Issues and pull requests share one sequence of numbers, so
    the newest number listed may be a pull request's, and a number read may name one; a pull
    request is never the issue sought. A number the service answers as gone — deleted (410) or
    moved to another repository (301) — is passed over: it holds nothing of ours."""
    recent: list[Json] = await api.get(
        api.repo("issues"),
        {"state": "all", "sort": "created", "direction": "desc", "per_page": RECENT},
    )
    for issue in recent:
        if "pull_request" not in issue and mark_of(issue.get("body")) == key:
            return issue
    number = max((int(issue["number"]) for issue in recent), default=0)
    for _ in range(PROBES):
        number += 1
        try:
            read: Json = await api.get(api.repo(f"issues/{number}"))
        except TargetError as error:
            if error.cause == "not_found":
                return None
            if error.status in (301, 410):
                continue
            raise
        if "pull_request" not in read and mark_of(read.get("body")) == key:
            return read
    return None


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


async def reply(api: Api, input: Json, key: str) -> Outcome:
    """Taktus's answer at a reply address the intake produced (`contracts/connector/v1` §7):
    `<repository>#<number>` is a comment on that issue or pull request, made and found again
    exactly as `repository.comments.create` makes and finds one. An address without a number
    names no conversation to answer in, and is refused."""
    address = _str(input, "address")
    repository, separator, number = address.rpartition("#")
    if not separator or not number.isdigit() or int(number) < 1:
        raise invalid(f"{address!r} names no issue or pull request to answer in")
    if repository and repository.lower() != api.repository.lower():
        raise invalid(f"{address!r} is not in the repository this connector serves")
    return await create_comment(api, {"number": int(number), "body": _str(input, "text")}, key)


def _comment_records(comment: Json, number: int) -> list[Json]:
    return [
        {
            "kind": "comment",
            "id": f"{number}#{comment['id']}",
            "url": str(comment.get("html_url", "")),
        }
    ]


WORKFLOWS = ".github/workflows/"


def _workflows_named(error: TargetError, paths: list[str]) -> TargetError:
    """The service refuses a tree that touches its pipeline's workflow files to an identity
    without the right to change them, and says only "not accessible". Name the files, so that
    the reason reaches whoever reads the failure (issue #366)."""
    workflows = sorted(path for path in paths if path.startswith(WORKFLOWS))
    if error.cause != "forbidden" or not workflows:
        return error
    return TargetError(
        error.cause,
        error.effect,
        error.retryable,
        f"{error.detail}; the change touches the pipeline's workflow files "
        f"({', '.join(workflows)}), which the service lets only an identity with the right to "
        "change workflows write",
        error.status,
    )


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
    base_sha = await _base(api, base)
    base_commit = await api.get(api.repo(f"git/commits/{base_sha}"))
    tree_sha = str(base_commit.get("tree", {}).get("sha", ""))
    unflagged = [str(file["path"]) for file in files if "executable" not in file]
    modes = await _modes_in(api, tree_sha, unflagged)
    entries: list[Json] = []
    for file in files:
        blob = await api.post(
            api.repo("git/blobs"), {"content": file["content"], "encoding": file["encoding"]}
        )
        path = str(file["path"])
        entries.append(
            {"path": path, "mode": _mode_of(file, modes), "type": "blob", "sha": str(blob["sha"])}
        )
    entries.extend(
        {"path": path, "mode": FILE_MODE, "type": "blob", "sha": None} for path in deleted
    )
    if entries:
        try:
            tree = await api.post(api.repo("git/trees"), {"base_tree": tree_sha, "tree": entries})
        except TargetError as error:
            raise _workflows_named(error, [str(entry["path"]) for entry in entries]) from None
        tree_sha = str(tree["sha"])
    commit = await api.post(
        api.repo("git/commits"),
        {"message": trailed(message, key), "tree": tree_sha, "parents": [base_sha]},
    )
    sha = str(commit["sha"])
    await api.post(api.repo("git/refs"), {"ref": f"refs/heads/{name}", "sha": sha})
    output = _branch_output(api, name, sha, base, str(commit.get("html_url", "")))
    return Outcome(output, write_effect(_branch_records(output), digest, replayed=False))


async def read_branch(api: Api, input: Json, key: str) -> Outcome:
    """A branch by its name: whether it exists, the commit at its head, and the idempotency key
    that commit carries as a trailer, or null. Given a `key`, `free` says whether
    `repository.branches.create` under that key would create the branch or find it as its own:
    no branch of that name exists, or its head carries exactly that key. Without one, `free`
    says only that no such branch exists. Nothing here judges whose a branch is beyond the key
    at its head: a branch somebody pushed onto after the marked commit is not free."""
    name = _str(input, "name")
    wanted = _str(input, "key", optional=True)
    sha = await _ref(api, name)
    if sha is None:
        output: Json = {"name": name, "exists": False, "sha": None, "key": None, "free": True}
        return Outcome(output, read_effect())
    head = await api.get(api.repo(f"git/commits/{sha}"))
    carried = trailer_of(head.get("message"))
    free = bool(wanted) and carried == wanted
    output = {"name": name, "exists": True, "sha": sha, "key": carried, "free": free}
    return Outcome(output, read_effect())


def _mode_of(file: Json, modes: dict[str, str]) -> str:
    """The mode a file is written with: what its input says, else what the base has, else a
    plain file."""
    flag = file.get("executable")
    if flag is True:
        return EXECUTABLE_MODE
    if flag is False:
        return FILE_MODE
    return modes.get(str(file["path"]), FILE_MODE)


async def _modes_in(api: Api, tree_sha: str, paths: list[str]) -> dict[str, str]:
    """The mode each of `paths` already has in the base tree, for the paths that are there.

    A tree entry carries the file's mode, and a write that does not carry it forward silently
    makes the file plain: an executable script that a change touches stops being executable,
    and the first thing that runs it fails (DEC-0020). The whole tree comes in one request;
    a tree too large for one answer comes back marked truncated, and the paths it did not
    carry are then looked up along their own directories, one request per directory.
    """
    if not paths or not tree_sha:
        return {}
    wanted = set(paths)
    answer = await api.get(api.repo(f"git/trees/{tree_sha}"), {"recursive": "1"})
    modes = _blob_modes(answer, wanted)
    if answer.get("truncated"):
        for path in sorted(wanted - set(modes)):
            if (mode := await _mode_along(api, tree_sha, path)) is not None:
                modes[path] = mode
    return modes


def _blob_modes(tree: Json, wanted: set[str]) -> dict[str, str]:
    """The entries of one tree answer that are blobs, are wanted, and carry a mode a blob may
    be written back with."""
    found: dict[str, str] = {}
    for entry in tree.get("tree", []):
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path, mode = str(entry.get("path", "")), str(entry.get("mode", ""))
        if path in wanted and mode in BLOB_MODES:
            found[path] = mode
    return found


async def _mode_along(api: Api, tree_sha: str, path: str) -> str | None:
    """One path's mode, walking the directories from the root tree. Used only where the tree
    was too large to come in one answer."""
    head, *rest = path.split("/")
    answer = await api.get(api.repo(f"git/trees/{tree_sha}"))
    for entry in answer.get("tree", []):
        if not isinstance(entry, dict) or entry.get("path") != head:
            continue
        if not rest:
            mode = str(entry.get("mode", ""))
            return mode if entry.get("type") == "blob" and mode in BLOB_MODES else None
        if entry.get("type") != "tree":
            return None
        return await _mode_along(api, str(entry.get("sha", "")), "/".join(rest))
    return None


COMMIT = re.compile(r"^[0-9a-f]{40}$")


async def _base(api: Api, base: str) -> str:
    """The commit a branch is made from: a branch's head, or a commit named by its full sha —
    the one a worker's workspace was cloned from, so that the change lands on the base it was
    made against and nothing the branch gained meanwhile is reverted (#496)."""
    sha = await _ref(api, base)
    if sha is not None:
        return sha
    if COMMIT.match(base):
        try:
            await api.get(api.repo(f"git/commits/{base}"))
        except TargetError as error:
            if error.cause == "not_found":
                raise TargetError(
                    "not_found", "none", False, f"base commit {base} does not exist"
                ) from error
            raise
        return base
    raise TargetError("not_found", "none", False, f"base branch {base!r} does not exist")


async def _ref(api: Api, name: str) -> str | None:
    """The sha a branch points at, or None when there is no such branch."""
    return await _reference(api, f"refs/heads/{name}")


async def _reference(api: Api, name: str) -> str | None:
    """The sha a fully qualified reference points at, or None when there is no such reference.
    The interface answers one reference by its exact name, as written."""
    try:
        ref = await api.get(api.repo(f"git/ref/{name.removeprefix('refs/')}"))
    except TargetError as error:
        if error.cause == "not_found":
            return None
        raise
    if not isinstance(ref, dict):
        return None
    return str(ref.get("object", {}).get("sha", "")) or None


REFERENCE = re.compile(r"^refs(/[A-Za-z0-9_][A-Za-z0-9._-]*){2,}$")
MAX_REFERENCES = 10
"""The most references one `create_references` creates: three requests each at most, besides
the two that resolve the target."""


def _reference_names(input: Json) -> list[str]:
    names = _paths(input, "names")
    if not names:
        raise invalid("names names at least one reference")
    if len(names) > MAX_REFERENCES:
        raise invalid(f"names names {len(names)} references; one call creates {MAX_REFERENCES}")
    for name in names:
        if REFERENCE.match(name) is None or name.endswith(".lock") or ".." in name:
            raise invalid(
                f"{name!r} is not a fully qualified reference: refs/<namespace>/<name>, of "
                "letters, digits, '.', '_' and '-'"
            )
    return list(dict.fromkeys(names))


async def create_references(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: each reference by its exact name, which the service keeps unique. Each points at
    a commit of its own — a child of the target with the target's tree, that changes nothing —
    whose message carries our key as a trailer: a reference found with our key is ours,
    replayed. A reference found with another key, or none, is somebody else's, and the operation
    ends in `conflict` naming it — the service would refuse it anyway. Creating a reference is
    atomic on the service: of two callers that create the same name, exactly one succeeds, and
    the other is answered `conflict` too. What makes a reference a reservation, a marker or
    anything else is the caller's; this operation knows no namespace.

    The references are created in the order given. A conflict on one leaves those before it
    created; a repeat with the same key finds them and goes on to the next."""
    names = _reference_names(input)
    target = _str(input, "target")
    message = _str(input, "message", optional=True) or "taktus: reference"
    request: Json = {"names": names, "target": target, "message": message}
    digest = digest_of(request)
    records: list[Json] = []
    shas: dict[str, str] = {}
    created = False
    parent: str | None = None
    tree_sha = ""
    for name in names:
        existing = await _reference(api, name)
        if existing is not None:
            head = await api.get(api.repo(f"git/commits/{existing}"))
            if trailer_of(head.get("message")) != key:
                raise TargetError(
                    "conflict",
                    "none",
                    False,
                    f"reference {name!r} exists and was not created for this step",
                )
            shas[name] = existing
            records.append({"kind": "vcs.reference", "id": name})
            continue
        if parent is None:
            parent = target if SHA.match(target) else await _ref(api, target)
            if parent is None:
                raise TargetError("not_found", "none", False, f"target {target!r} does not exist")
            commit = await api.get(api.repo(f"git/commits/{parent}"))
            tree_sha = str(commit.get("tree", {}).get("sha", ""))
        made = await api.post(
            api.repo("git/commits"),
            {
                "message": trailed(f"{message.rstrip()}\n\n{name}", key),
                "tree": tree_sha,
                "parents": [parent],
            },
        )
        sha = str(made["sha"])
        await api.post(api.repo("git/refs"), {"ref": name, "sha": sha})
        shas[name] = sha
        records.append({"kind": "vcs.reference", "id": name})
        created = True
    output: Json = {
        "target": target,
        "references": [{"name": name, "sha": shas[name]} for name in names],
    }
    return Outcome(output, write_effect(records, digest, replayed=not created))


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
        path = _tree_path(entry.get("path"))
        content = entry.get("content")
        encoding = entry.get("encoding", "utf-8")
        if not isinstance(content, str):
            raise invalid(f"the content of {path!r} must be a string")
        if encoding not in ("utf-8", "base64"):
            raise invalid(f"the encoding of {path!r} must be utf-8 or base64")
        file: Json = {"path": path, "content": content, "encoding": encoding}
        if "executable" in entry:
            if not isinstance(entry["executable"], bool):
                raise invalid(f"executable of {path!r} must be true or false")
            file["executable"] = entry["executable"]
        files.append(file)
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


MAX_LABELS_REMOVED = 5  # what one call removes at most: one request per label


async def remove_labels(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the labels on the issue, as for `repository.labels.set`. The mark is the label's
    absence: a repeat with any key that finds none of the requested labels present removes
    nothing and reports `replayed`. A label removed by somebody else between the lookup and the
    removal is gone either way, and is not an error. At most five labels in one call."""
    number = _int(input, "number")
    labels = _paths(input, "labels")
    if not labels:
        raise invalid("labels must name at least one label")
    if len(labels) > MAX_LABELS_REMOVED:
        raise invalid(f"labels names at most {MAX_LABELS_REMOVED} labels to remove")
    request: Json = {"remove": labels}
    digest = digest_of(request)
    issue = await api.get(api.repo(f"issues/{number}"))
    present = {str(label.get("name", "")) for label in issue.get("labels", []) or []}
    records = [{"kind": "label", "id": f"{number}#{label}"} for label in labels]
    present_now = [label for label in labels if label in present]
    if not present_now:
        output = {"number": number, "labels": sorted(present)}
        return Outcome(output, write_effect(records, digest, replayed=True))
    remaining = set(present)
    for label in present_now:
        try:
            left = await api.delete(api.repo(f"issues/{number}/labels/{quote(label, safe='')}"))
        except TargetError as error:
            if error.status != 404:
                raise
            left = None
        remaining.discard(label)
        if isinstance(left, list):
            remaining = {str(item.get("name", "")) for item in left}
    return Outcome(
        {"number": number, "labels": sorted(remaining)},
        write_effect(records, digest, replayed=False),
    )


async def close_issue(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the comment that says why, among every comment of the item, by mark — exactly as
    `repository.comments.create` finds one — and the item's state. The comment is written
    first and the item closed after it, so a call that stopped between the two finds its
    comment on the next attempt and only closes. A pull request is closed as an issue is: the
    service's issue interface serves both, and nothing here can merge one."""
    number = _int(input, "number")
    reason = _str(input, "reason")
    request: Json = {"number": number, "reason": reason, "state": "closed"}
    digest = digest_of(request)
    commented = await create_comment(api, {"number": number, "body": reason}, key)
    issue = await api.get(api.repo(f"issues/{number}"))
    records = [*commented.effect["records"], *_issue_records(issue)]
    if str(issue.get("state", "")) == "closed" and commented.effect["replayed"]:
        return Outcome(issue_output(issue), write_effect(records, digest, replayed=True))
    closed = await api.patch(
        api.repo(f"issues/{number}"), {"state": "closed", "state_reason": "not_planned"}
    )
    return Outcome(issue_output(closed), write_effect(records, digest, replayed=False))


async def set_milestone(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the item's milestone, which is the record this operation writes into. The mark
    is the milestone itself, as a label is for `repository.labels.set`: a repeat that finds it
    set changes nothing and reports `replayed`. The milestone is found by its title among the
    open ones; a title no open milestone has is `not_found`, and nothing is changed."""
    number = _int(input, "number")
    title = _str(input, "milestone")
    request: Json = {"number": number, "milestone": title}
    digest = digest_of(request)
    issue = await api.get(api.repo(f"issues/{number}"))
    records = _issue_records(issue)
    if issue_output(issue)["milestone"] == title:
        return Outcome(issue_output(issue), write_effect(records, digest, replayed=True))
    milestones = await api.get(api.repo("milestones"), {"state": "open", "per_page": 100})
    found = next((m for m in milestones or [] if str(m.get("title", "")) == title), None)
    if found is None:
        raise TargetError("not_found", "none", False, f"no open milestone is titled {title!r}")
    updated = await api.patch(api.repo(f"issues/{number}"), {"milestone": int(found["number"])})
    return Outcome(issue_output(updated), write_effect(records, digest, replayed=False))


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


# --- keeping a pull request mergeable (ADR-0193, ADR-0194) -------------------------------------

MAX_WITH_STATE = 30  # how many pull requests `with_state` reads the state of: three requests each
MAX_FILE_PAGES = 30  # the service lists at most 3000 files of a pull request, 100 to a page
MAX_PATCH = 20_000  # the characters of one file's patch handed on; longer ones are cut and said so
WALK = 20  # how many first parents `repository.branches.commit` looks for its key in
RUN_STATUSES = ("queued", "in_progress", "completed")


def _moment(text: Any) -> datetime | None:
    """A timestamp of the service, ISO 8601 with `Z`, or None when it is none."""
    if not isinstance(text, str) or not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _whole(since: Any, now: datetime, seconds: int) -> int | None:
    """Whole units of `seconds` from a timestamp of the service to now, rounded down; None when
    the service gave no timestamp. Never negative: a clock a little behind reads zero."""
    moment = _moment(since)
    if moment is None:
        return None
    return max(0, int((now - moment).total_seconds()) // seconds)


def _now() -> datetime:
    return datetime.now(UTC)


def _read_at(now: datetime) -> str:
    return now.isoformat(timespec="seconds").replace("+00:00", "Z")


def _listed_pull(pull: Json, now: datetime) -> Json:
    """One pull request of a list: its reading, its labels by name, and its two ages."""
    return {
        **pull_output(pull),
        "updated_at": str(pull.get("updated_at") or pull.get("created_at", "")),
        "idle_hours": _whole(pull.get("updated_at") or pull.get("created_at"), now, 3600),
        "open_hours": _whole(pull.get("created_at"), now, 3600),
    }


async def list_pull_requests(api: Api, input: Json, key: str) -> Outcome:
    """The pull requests in one state — `open` unless `state` says `closed` or `all` — newest
    first, page by page up to MAX_PAGES pages of 100. With `with_state`, the first `limit` of
    them (at most MAX_WITH_STATE) carry how far their head is behind and ahead of their base,
    the pipeline's word for their head and the key their head commit carries (ADR-0193 §1)."""
    state = input.get("state", "open")
    if state not in ("open", "closed", "all"):
        raise invalid("state is open, closed or all")
    with_state = input.get("with_state", False)
    if not isinstance(with_state, bool):
        raise invalid("with_state is true or false")
    limit = input.get("limit", MAX_WITH_STATE)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_WITH_STATE:
        raise invalid(f"limit is a number from 1 to {MAX_WITH_STATE}")
    page, next_url = await api.get_page(api.repo("pulls"), {"state": state, "per_page": 100})
    found: list[Json] = list(page)
    pages = 1
    while next_url and pages < MAX_PAGES:
        page, next_url = await api.get_url(next_url)
        found.extend(page)
        pages += 1
    now = _now()
    pulls = [_listed_pull(pull, now) for pull in found]
    complete = next_url is None
    if with_state:
        if len(pulls) > limit:
            complete = False
        pulls = pulls[:limit]
        for pull in pulls:
            pull.update(await _state_of_pull(api, pull))
    output = {"state": state, "pulls": pulls, "complete": complete, "read_at": _read_at(now)}
    return Outcome(output, read_effect())


async def _state_of_pull(api: Api, pull: Json) -> Json:
    head, base = str(pull.get("head_sha") or ""), str(pull["base"])
    if not head:
        head = await _ref(api, str(pull["head"])) or ""
    if not head:
        return {"behind": None, "ahead": None, "pipeline": "none", "head_key": None}
    compared = await api.get(api.repo(f"compare/{quote(base, safe='')}...{head}"))
    listed = await api.get(api.repo("actions/runs"), {"head_sha": head, "per_page": MAX_RUNS})
    runs = [run_output(r) for r in (listed or {}).get("workflow_runs", [])]
    commit = await api.get(api.repo(f"git/commits/{head}"))
    return {
        "head_sha": head,
        "behind": int(compared.get("behind_by", 0)),
        "ahead": int(compared.get("ahead_by", 0)),
        "pipeline": _state_of(runs),
        "head_key": trailer_of(commit.get("message")),
    }


async def pull_request_files(api: Api, input: Json, key: str) -> Outcome:
    """The paths a pull request changes, at the head commit the service names for it when it is
    read: one request for the pull request, one per page of 100 files. `complete` is false when
    the service has more pages than are read, or lists the most it answers (ADR-0194 §2)."""
    number = _int(input, "number")
    patches = input.get("patches", False)
    if not isinstance(patches, bool):
        raise invalid("patches is true or false")
    pull = await api.get(api.repo(f"pulls/{number}"))
    head = str(pull.get("head", {}).get("sha") or "")
    page, next_url = await api.get_page(api.repo(f"pulls/{number}/files"), {"per_page": 100})
    listed: list[Json] = list(page)
    pages = 1
    while next_url and pages < MAX_FILE_PAGES:
        page, next_url = await api.get_url(next_url)
        listed.extend(page)
        pages += 1
    files: list[Json] = []
    for item in listed:
        entry: Json = {
            "path": str(item.get("filename", "")),
            "status": str(item.get("status", "")),
            "additions": int(item.get("additions", 0)),
            "deletions": int(item.get("deletions", 0)),
            "previous_path": item.get("previous_filename"),
        }
        if patches:
            patch = str(item.get("patch") or "")
            entry["patch"] = patch[:MAX_PATCH]
            entry["patch_cut"] = len(patch) > MAX_PATCH
        files.append(entry)
    output = {
        "number": number,
        "head_sha": head or None,
        "files": files,
        "count": len(files),
        "additions": sum(f["additions"] for f in files),
        "deletions": sum(f["deletions"] for f in files),
        "complete": next_url is None and len(files) < MAX_FILE_PAGES * 100,
    }
    return Outcome(output, read_effect())


async def list_pipeline_runs(api: Api, input: Json, key: str) -> Outcome:
    """The pipeline runs in one status, newest first, at most `limit` (100), each with its
    age in whole minutes at the moment of the reading (ADR-0193 §3)."""
    status = input.get("status", "in_progress")
    if status not in RUN_STATUSES:
        raise invalid("status is queued, in_progress or completed")
    limit = input.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise invalid("limit is a number from 1 to 100")
    listed = await api.get(api.repo("actions/runs"), {"status": status, "per_page": limit})
    now = _now()
    runs = []
    for run in (listed or {}).get("workflow_runs", [])[:limit]:
        runs.append(
            {
                **run_output(run),
                "head_sha": str(run.get("head_sha") or "") or None,
                "branch": str(run.get("head_branch") or "") or None,
                "age_minutes": _whole(run.get("created_at"), now, 60),
            }
        )
    total = int((listed or {}).get("total_count", len(runs)))
    output = {
        "status": status,
        "runs": runs,
        "count": len(runs),
        "complete": total <= len(runs),
        "read_at": _read_at(now),
    }
    return Outcome(output, read_effect())


async def update_branch(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the head of the branch; a head that carries our key is the merge we made,
    replayed. Otherwise the base is merged into the branch by the service's merge interface, in
    one commit that carries the key as a trailer: 201 is the commit, 204 means the branch
    contains its base already and nothing was written, 409 a conflict, nothing written."""
    name = _str(input, "name")
    base = _str(input, "base")
    expected = _str(input, "expected", optional=True)
    if expected and not SHA.match(expected):
        raise invalid("expected must be a full commit sha")
    request: Json = {"name": name, "base": base, "expected": expected or None}
    digest = digest_of(request)
    head = await _ref(api, name)
    if head is None:
        raise TargetError("not_found", "none", False, f"branch {name!r} does not exist")
    commit = await api.get(api.repo(f"git/commits/{head}"))
    if trailer_of(commit.get("message")) == key:
        output = {"name": name, "base": base, "updated": True, "sha": head, "previous": None}
        return Outcome(output, write_effect(_commit_records(api, head), digest, replayed=True))
    if expected and head != expected:
        raise TargetError(
            "conflict", "none", False, f"branch {name!r} moved: its head is not the expected commit"
        )
    message = trailed(f"Merge {base} into {name}", key)
    merged = await api.post(
        api.repo("merges"), {"base": name, "head": base, "commit_message": message}
    )
    if merged is None:
        output = {"name": name, "base": base, "updated": False, "sha": head, "previous": head}
        return Outcome(output, write_effect([], digest, replayed=False))
    sha = str(merged.get("sha", ""))
    output = {"name": name, "base": base, "updated": True, "sha": sha, "previous": head}
    return Outcome(output, write_effect(_commit_records(api, sha), digest, replayed=False))


async def commit_to_branch(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the branch's first parents from its head, at most WALK, for a commit that carries
    our key: the original, replayed. Otherwise the head must be `expected`, the commit the change
    was made against; the files go into one commit on top of it, and the reference is moved
    forward to it, never forced (ADR-0193 §1)."""
    name = _str(input, "name")
    expected = _str(input, "expected")
    if not SHA.match(expected):
        raise invalid("expected must be a full commit sha")
    message = _str(input, "message", optional=True) or f"taktus: change on {name}"
    files = _files(input)
    deleted = _paths(input, "deleted")
    if not files and not deleted:
        raise invalid("a commit onto a branch carries at least one file or one deletion")
    request: Json = {"name": name, "expected": expected, "message": message, "files": files}
    if deleted:
        request["deleted"] = deleted
    digest = digest_of(request)
    head = await _ref(api, name)
    if head is None:
        raise TargetError("not_found", "none", False, f"branch {name!r} does not exist")
    sha: str | None = head
    head_commit: Json | None = None
    for _ in range(WALK):
        if sha is None:
            break
        commit = await api.get(api.repo(f"git/commits/{sha}"))
        head_commit = head_commit or commit
        if trailer_of(commit.get("message")) == key:
            output = {
                "name": name,
                "sha": sha,
                "parent": None,
                "url": str(commit.get("html_url", "")),
            }
            return Outcome(output, write_effect(_commit_records(api, sha), digest, replayed=True))
        parents = commit.get("parents") or []
        sha = str(parents[0].get("sha", "")) if parents else None
    if head != expected:
        raise TargetError(
            "conflict", "none", False, f"branch {name!r} moved: its head is not the expected commit"
        )
    tree_sha = str((head_commit or {}).get("tree", {}).get("sha", ""))
    unflagged = [str(file["path"]) for file in files if "executable" not in file]
    modes = await _modes_in(api, tree_sha, unflagged)
    entries: list[Json] = []
    for file in files:
        blob = await api.post(
            api.repo("git/blobs"), {"content": file["content"], "encoding": file["encoding"]}
        )
        path = str(file["path"])
        entries.append(
            {"path": path, "mode": _mode_of(file, modes), "type": "blob", "sha": str(blob["sha"])}
        )
    entries.extend(
        {"path": path, "mode": FILE_MODE, "type": "blob", "sha": None} for path in deleted
    )
    try:
        tree = await api.post(api.repo("git/trees"), {"base_tree": tree_sha, "tree": entries})
    except TargetError as error:
        raise _workflows_named(error, [str(entry["path"]) for entry in entries]) from None
    commit = await api.post(
        api.repo("git/commits"),
        {"message": trailed(message, key), "tree": str(tree["sha"]), "parents": [head]},
    )
    new = str(commit["sha"])
    try:
        await api.patch(api.repo(f"git/refs/heads/{name}"), {"sha": new, "force": False})
    except TargetError as error:
        if error.cause == "invalid" and "fast forward" in error.detail:
            raise TargetError(
                "conflict", "none", False, f"branch {name!r} moved while the commit was written"
            ) from None
        raise
    output = {"name": name, "sha": new, "parent": head, "url": str(commit.get("html_url", ""))}
    return Outcome(output, write_effect(_commit_records(api, new), digest, replayed=False))


MERGE_METHODS = ("merge", "squash")


async def merge_pull_request(api: Api, input: Json, key: str) -> Outcome:
    """Lookup: the pull request. Merged, with our key in its merge commit: the original,
    replayed; merged without it: somebody else's, `conflict`. Otherwise it is merged at the head
    commit `sha` names and no other, the commit message carrying the key (ADR-0194 §1). The
    service's refusal to merge — closed, a conflict, a rule of the repository — is `conflict`."""
    number = _int(input, "number")
    sha = _str(input, "sha")
    if not SHA.match(sha):
        raise invalid("sha must be the full commit the pull request is merged at")
    method = input.get("method", "squash")
    if method not in MERGE_METHODS:
        raise invalid("method is merge or squash: a rebase carries no commit for the key")
    title = _str(input, "title", optional=True)
    request: Json = {"number": number, "sha": sha, "method": method, "title": title or None}
    digest = digest_of(request)
    pull = await api.get(api.repo(f"pulls/{number}"))
    if pull.get("merged"):
        merge_sha = str(pull.get("merge_commit_sha") or "")
        commit = await api.get(api.repo(f"git/commits/{merge_sha}")) if merge_sha else {}
        if trailer_of(commit.get("message")) == key:
            output = {"number": number, "merged": True, "sha": merge_sha, "head_sha": sha}
            return Outcome(output, write_effect(_pull_records(pull), digest, replayed=True))
        raise TargetError(
            "conflict", "none", False, f"pull request {number} was merged by somebody else"
        )
    body: Json = {"sha": sha, "merge_method": method, "commit_message": trailed("", key).strip()}
    if title:
        body["commit_title"] = title
    try:
        merged = await api.put(api.repo(f"pulls/{number}/merge"), body)
    except TargetError as error:
        if error.status in (405, 409):
            raise TargetError(
                "conflict",
                "none",
                False,
                f"the service did not merge pull request {number}: "
                + ("its head is not the commit named" if error.status == 409 else "not mergeable"),
            ) from None
        raise
    output = {"number": number, "merged": True, "sha": str(merged.get("sha", "")), "head_sha": sha}
    return Outcome(output, write_effect(_pull_records(pull), digest, replayed=False))


def _commit_records(api: Api, sha: str) -> list[Json]:
    return [{"kind": "vcs.commit", "id": sha, "url": f"{api.web}/{api.repository}/commit/{sha}"}]


type Operation = Callable[[Api, Json, str], Awaitable[Outcome]]

OPERATIONS: dict[str, Operation] = {
    "repository.issues.read": read_issue,
    "repository.issues.list": list_issues,
    "repository.issues.create": create_issue,
    "repository.issues.close": close_issue,
    "repository.issues.milestone": set_milestone,
    "repository.pullrequests.read": read_pull_request,
    "repository.pullrequests.open": open_pull_request,
    "repository.pullrequests.list": list_pull_requests,
    "repository.pullrequests.files": pull_request_files,
    "repository.pullrequests.merge": merge_pull_request,
    "repository.pipelines.read": read_pipeline_run,
    "repository.pipelines.status": pipeline_status,
    "repository.pipelines.trigger": trigger_pipeline,
    "repository.pipelines.list": list_pipeline_runs,
    "repository.comments.list": list_comments,
    "repository.comments.create": create_comment,
    "channel.repo.reply": reply,
    "repository.branches.read": read_branch,
    "repository.branches.create": create_branch,
    "repository.branches.update": update_branch,
    "repository.branches.commit": commit_to_branch,
    "repository.refs.create": create_references,
    "repository.labels.set": set_labels,
    "repository.labels.remove": remove_labels,
    "repository.files.read": read_file,
    "repository.files.read_many": read_many,
    "repository.files.list": list_files,
    "repository.members.list": list_members,
}
