#!/usr/bin/env python3
"""A fake of the repository hosting service the reference connector talks to.

The connector under `connectors/taktus_connectors/github/` speaks the REST dialect of
that service. This fake answers the subset the connector uses — issues, pull requests, comments,
labels, pipeline runs, the contents of a file at a ref, and the object interface for branches:
references, commits, blobs, trees — in the same shapes, with the same status codes for the same
faults, and keeps everything in memory. It exists so that the connector can be exercised in CI
without a network, an account or a secret: the conformance gate starts it as a process, the
adapter tests start it in a thread.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_REPOSITORY_TOKENS`, `value:scope,...`; scope `read` or `write`).
  No or unknown value: 401. A `read` scope on a write: 403. This is what lets the tests show
  that the connector acts with the requesting identity's credential and no other.
- **An app of its own** (ADR-0033), when started with one (`FAKE_REPOSITORY_APP`,
  `<app id>:<path of the app's public key>`). `GET /repos/{owner}/{repo}/installation` and
  `POST /app/installations/{id}/access_tokens` accept only a statement signed with the app's
  private key (RS256, issuer the app id, valid ten minutes at most) and answer as the service
  does: the installation, and a token that lives `token_seconds` (an hour unless changed). The
  token acts with write scope until it expires or is revoked, as a bot whose login ends in
  `[bot]`. Every repository is installed until `POST /_fake/app` says otherwise.
- **Workflow files are refused.** A tree that touches `.github/workflows/` is answered 403
  "Resource not accessible by integration", as the service answers an app that lacks the right
  to change workflows (issue #366).
- **Pull request uniqueness.** A second open pull request for the same head branch is refused
  with 422, as the real service does; so is one whose head branch does not exist.
- **An issue list that lags**, when started with `--issue-list-lag SECONDS` or told so by
  `POST /_fake/lag` with `{"seconds": 2}`: the issue list leaves out what was created less than
  that long ago, as the real service's list did on 2026-10-12, while one issue read by its
  number is there at once. Off unless asked for; the conformance gate asks for it.
- **Paging.** Comment, issue and collaborator lists page with `per_page`/`page` and a
  `Link: <…>; rel="next"` header.
- **Collaborators.** Every repository starts with two, `fake-user` (role `admin`) and
  `fake-reviewer` (role `write`), each with its number, login, kind and role — and no address,
  as the service answers an app on 2026-10-10.
- **Labels and milestones on an issue.** An issue is opened with label names and a milestone's
  number (`POST …/milestones` makes one), and is read with both, as the ready standard of a
  backlog reads them (issue #70). A directory reads as its immediate entries, each a `file` or a
  `dir`, and a branch moves to a later commit with `PATCH …/git/refs/heads/<name>`.
- **The commit a clone was made from.** `POST /_fake/clone` with `{"repository", "sha"}` makes the
  head of `main` known under the sha of a local clone, so that a branch can be made from it
  (#496).
- **References besides branches.** `POST …/git/refs` creates any `refs/<namespace>/<name>` once,
  and refuses a second with 422 "Reference already exists", as the service does; `GET
  …/git/ref/<namespace>/<name>` reads one. No pipeline runs for one, and `GET /_fake/state`
  lists them by name.
- **A pipeline per push.** Creating a reference creates one completed pipeline run for its
  commit, concluded `success` unless `POST /_fake/ci` said otherwise (`{"conclusion":
  "failure"}`, or `{"pending": true}` for a run that never completes), so that a process can
  read the pipeline's verdict for a branch it created. `POST /_fake/run` with `{"repository",
  "branch", "conclusion"}` records one completed `ci` run for the head of an existing branch, as
  a push to it would — how `main` turns red or green (#481); with `"status": "in_progress"` a run
  still running, and `"minutes_ago"` one created that long ago (ADR-0201).

- **Keeping a pull request mergeable** (ADR-0193). A pull request is read with the commit at
  its head. `GET …/compare/<base>...<head>` answers `ahead_by` and `behind_by` from the commit
  graph; `GET …/pulls/<n>/files` lists the paths changed between the merge base and the head,
  with lines added and removed and a unified patch; `POST …/merges` merges one branch or commit
  into a branch, 201 with the commit, 204 when there is nothing to merge, 409 when both sides
  changed one path differently; `PUT …/pulls/<n>/merge` merges a pull request at the head `sha`
  names, 409 for another head, 405 for one closed or conflicting. A branch moved by `PATCH` gets
  a pipeline run, as a push does. `GET …/actions/runs?status=` lists the runs in one status.

- **The repository's infrastructure** (ADR-0201). Every run carries `run_attempt`. `POST
  …/actions/runs/<id>/rerun-failed-jobs` answers 201 for a completed run and makes it queued
  again under the next attempt; for one not completed it answers 403 — the service's own answer
  for that case is not documented, and the connector never asks it. `POST …/cancel` answers 202
  and completes the run as `cancelled`, 409 for a run completed already. `GET …/actions/runners`
  lists the runners `POST /_fake/runner` added (`{"repository", "name", "status", "busy"}`).
  `GET …/branches` lists every branch with its head and `protected` (`POST /_fake/protect`
  with `{"repository", "branch"}`), 100 to a page at most. `GET /rate_limit` answers the
  resources `core`, `search` and `graphql`, `core` with the requests this fake answered.
  `GET …/dependabot/alerts` lists the alerts `POST /_fake/alert` added, filtered by `state` and
  `severity`, newest first, each with a dismisser and assignees the connector must never copy.

- **When a path last changed** (ADR-0307). Every commit carries `committer.date`, the moment it
  was made, and `POST /_fake/date` with `{"repository", "sha", "date"}` dates one commit
  otherwise. `GET …/commits?sha=<commit>&path=<path>&per_page=1` walks the first parents from
  the commit and answers the newest commit that changed anything at or below the path, in the
  service's shape (`sha`, `commit.committer.date`), or an empty list.

Test-only endpoints under `/_fake/`: `GET /_fake/state` counts what exists, `POST /_fake/reset`
empties the store, `POST /_fake/outage` with `{"on": true}` makes every other request answer 503
until switched off, `POST /_fake/hang` with `{"seconds": 2}` makes every other request wait
that long before answering, so that a client's timeout can be provoked. `POST /_fake/answer`
with `{"status": 200, "body": …}` makes every other request answer that status and body — a
shape or a status the connector does not foresee, as an interface that changed would — until
`{}` switches it off (issue #100). `POST /_fake/app` with
any of `{"installed": false, "suspended": true, "token_seconds": 120}` changes the app's
installation — removing it revokes every token it issued — and `GET /_fake/app` lists every
token and signed statement the fake has seen, so that a test can look for them where they must
not be. Standard library only, except that the app's signature is checked with the project's
JWT library, imported when an app is configured; runnable as
`python3 tests/fakes/repository_service.py --port 9200`.
"""

from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

type Json = dict[str, Any]

TOKENS_VARIABLE = "FAKE_REPOSITORY_TOKENS"
APP_VARIABLE = "FAKE_REPOSITORY_APP"
APP_LOGIN = "taktus-fake[bot]"
APP_INSTALLATION = 7


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def collaborator(login: str, number: int, role: str) -> Json:
    """One collaborator, in the shape the service lists it: no address among the fields."""
    return {
        "login": login,
        "id": number,
        "type": "User",
        "site_admin": False,
        "role_name": role,
        "permissions": {"pull": True, "push": role != "read", "admin": role == "admin"},
    }


@dataclass
class Repository:
    owner: str
    name: str
    issues: dict[int, Json] = field(default_factory=dict)  # pull requests are issues too
    pulls: dict[int, Json] = field(default_factory=dict)
    comments: dict[int, list[Json]] = field(default_factory=dict)
    runs: dict[int, Json] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)  # branch name -> commit sha
    # Any other reference, by its full name -> commit sha: no pipeline runs for one.
    references: dict[str, str] = field(default_factory=dict)
    objects: dict[str, Json] = field(default_factory=dict)  # sha -> blob | tree | commit
    milestones: dict[int, Json] = field(default_factory=dict)
    created: dict[int, float] = field(default_factory=dict)  # number -> monotonic moment
    collaborators: list[Json] = field(
        default_factory=lambda: [
            collaborator("fake-user", 1, "admin"),
            collaborator("fake-reviewer", 2, "write"),
        ]
    )
    runners: list[Json] = field(default_factory=list)
    protected: set[str] = field(default_factory=set)
    alerts: list[Json] = field(default_factory=list)
    next_number: int = 1
    next_comment: int = 1
    next_run: int = 1
    next_object: int = 1

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class App:
    """The app the fake knows: its identifier, its public key, and its one installation."""

    app_id: str
    public_key: str
    installed: bool = True
    suspended: bool = False
    token_seconds: int = 3600
    issued: list[str] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)
    requested: list[Json] = field(default_factory=list)  # the bodies of every exchange


@dataclass
class Store:
    base_url: str
    tokens: dict[str, str]  # value -> scope
    app: App | None = None
    expiry: dict[str, float] = field(default_factory=dict)  # an app token's value -> its end
    repositories: dict[str, Repository] = field(default_factory=dict)
    outage: bool = False
    answer: Json | None = None  # {"status", "body"}: what every other request answers instead
    hang_seconds: float = 0.0
    ci_conclusion: str = "success"
    ci_pending: bool = False
    issue_list_lag: float = 0.0  # seconds an issue stays out of the issue list
    answered: int = 0  # reads answered under a credential, as `GET /rate_limit` counts them
    lock: threading.Lock = field(default_factory=threading.Lock)

    def repository(self, owner: str, name: str) -> Repository:
        key = f"{owner}/{name}"
        if key not in self.repositories:
            repo = Repository(owner, name)
            self.repositories[key] = repo
            self._seed(repo)
        return self.repositories[key]

    def _seed(self, repo: Repository) -> None:
        """Every repository starts with issue #1 and a `main` branch with one commit, so that a
        read has something to read and a branch has something to start from."""
        self.create_issue(repo, "Seed issue", "The first issue of every fake repository.", "seed")
        tree = self.new_object(repo, "tree", {"tree": []})
        commit = self.new_object(
            repo,
            "commit",
            {"message": "seed", "tree": {"sha": tree}, "parents": []},
        )
        repo.refs["main"] = commit
        self.create_run(repo, "ci", commit, status="completed", conclusion="success")

    def new_object(self, repo: Repository, kind: str, body: Json) -> str:
        sha = f"{repo.next_object:040x}"
        repo.next_object += 1
        dated: Json = {}
        if kind == "commit":
            moment = {"name": "fake", "email": "fake@example.invalid", "date": now()}
            dated = {"author": dict(moment), "committer": dict(moment)}
        repo.objects[sha] = {
            "sha": sha,
            "kind": kind,
            "html_url": f"{self.base_url}/{repo.full_name}/{kind}/{sha}",
            **dated,
            **body,
        }
        return sha

    def last_change(self, repo: Repository, start: str, path: str) -> Json | None:
        """The newest commit on the first-parent line from `start` that changed anything at or
        below `path`, as `GET …/commits?path=` answers it; None when none did."""

        def below(commit: Json) -> dict[str, str]:
            tree = repo.objects[commit["tree"]["sha"]]["tree"]
            prefix = path.rstrip("/") + "/"
            return {
                str(e["path"]): str(e["sha"])
                for e in tree
                if e["path"] == path or str(e["path"]).startswith(prefix)
            }

        sha: str | None = start
        while sha is not None:
            commit = repo.objects.get(sha)
            if commit is None or commit["kind"] != "commit":
                return None
            parents = commit.get("parents") or []
            parent = repo.objects.get(parents[0]["sha"]) if parents else None
            mine = below(commit)
            before = below(parent) if parent is not None else {}
            if mine != before:
                return {
                    "sha": sha,
                    "commit": {
                        "message": commit.get("message", ""),
                        "committer": commit.get("committer"),
                        "author": commit.get("author"),
                    },
                }
            sha = parents[0]["sha"] if parents else None
        return None

    def create_run(
        self, repo: Repository, name: str, head_sha: str, *, status: str, conclusion: str | None
    ) -> Json:
        run = {
            "id": repo.next_run,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "head_sha": head_sha,
            "run_attempt": 1,
            "html_url": f"{self.base_url}/{repo.full_name}/actions/runs/{repo.next_run}",
            "created_at": now(),
        }
        repo.runs[repo.next_run] = run
        repo.next_run += 1
        return run

    def create_issue(self, repo: Repository, title: str, body: str, login: str) -> Json:
        number = repo.next_number
        repo.next_number += 1
        issue = {
            "number": number,
            "title": title,
            "body": body,
            "state": "open",
            "user": {"login": login, "id": 1000 + len(repo.issues), "type": kind_of(login)},
            "labels": [],
            "html_url": f"{self.base_url}/{repo.full_name}/issues/{number}",
            "created_at": now(),
            "updated_at": now(),
        }
        repo.issues[number] = issue
        repo.created[number] = time.monotonic()
        repo.comments[number] = []
        return issue

    def create_pull(
        self,
        repo: Repository,
        title: str,
        head: str,
        base: str,
        body: str,
        login: str,
        draft: bool = False,
    ) -> Json:
        issue = self.create_issue(repo, title, body, login)
        number = int(issue["number"])
        issue["html_url"] = f"{self.base_url}/{repo.full_name}/pull/{number}"
        issue["pull_request"] = {"url": f"{self.base_url}/{repo.full_name}/pull/{number}"}
        pull = {
            **issue,
            "head": {"ref": head, "label": f"{repo.owner}:{head}"},
            "base": {"ref": base, "label": f"{repo.owner}:{base}"},
            "merged": False,
            "merged_at": None,
            "draft": draft,
            "merge_commit_sha": None,
        }
        repo.pulls[number] = pull
        return pull

    def contents(self, repo: Repository, path: str, ref: str | None) -> tuple[int, Any]:
        """What the contents interface answers for one path at a ref — a branch or a commit,
        `main` when none is given: a file with its content in base64, a directory as the list
        of its entries, or 404. Trees here are flat, one entry per full path."""
        sha = repo.refs.get(ref or "main", ref or "")
        commit = repo.objects.get(sha)
        if commit is None or commit["kind"] != "commit":
            return 404, {"message": "No commit found for the ref"}
        entries = repo.objects[commit["tree"]["sha"]]["tree"]
        for entry in entries:
            if entry["path"] == path and entry.get("type") == "blob":
                blob = repo.objects[entry["sha"]]
                raw = (
                    base64.b64decode(blob["content"])
                    if blob.get("encoding") == "base64"
                    else str(blob["content"]).encode("utf-8")
                )
                return 200, {
                    "type": "file",
                    "name": path.rsplit("/", 1)[-1],
                    "path": path,
                    "sha": entry["sha"],
                    "size": len(raw),
                    "encoding": "base64",
                    "content": base64.encodebytes(raw).decode(),
                }
        prefix = path.rstrip("/") + "/"
        children: dict[str, Json] = {}
        for entry in entries:
            full = str(entry["path"])
            if not full.startswith(prefix):
                continue
            name, _, deeper = full[len(prefix) :].partition("/")
            kind = "dir" if deeper else "file"
            sha = "" if deeper else entry["sha"]
            children.setdefault(
                name, {"type": kind, "name": name, "path": prefix + name, "sha": sha}
            )
        if children:
            return 200, [children[name] for name in sorted(children)]
        return 404, {"message": "Not Found"}

    # --- the commit graph (ADR-0193) -------------------------------------------------------

    def resolve(self, repo: Repository, ref: str) -> str | None:
        """A branch's head or a commit's sha; None when neither exists."""
        sha = repo.refs.get(ref, ref)
        found = repo.objects.get(sha)
        return sha if found is not None and found["kind"] == "commit" else None

    def ancestors(self, repo: Repository, sha: str) -> list[str]:
        """Every commit reachable from `sha`, itself first, breadth first."""
        seen: list[str] = []
        todo = [sha]
        while todo:
            current = todo.pop(0)
            if current in seen or current not in repo.objects:
                continue
            seen.append(current)
            todo.extend(p["sha"] for p in repo.objects[current].get("parents", []))
        return seen

    def merge_base(self, repo: Repository, a: str, b: str) -> str | None:
        of_b = set(self.ancestors(repo, b))
        return next((sha for sha in self.ancestors(repo, a) if sha in of_b), None)

    def files_at(self, repo: Repository, sha: str | None) -> dict[str, Json]:
        """The tree of a commit, by path; empty for no commit."""
        if sha is None:
            return {}
        tree = repo.objects[repo.objects[sha]["tree"]["sha"]]["tree"]
        return {e["path"]: e for e in tree if e.get("type") == "blob"}

    def text(self, repo: Repository, entry: Json | None) -> str:
        if entry is None:
            return ""
        blob = repo.objects[entry["sha"]]
        if blob.get("encoding") == "base64":
            return base64.b64decode(blob["content"]).decode("utf-8", "replace")
        return str(blob["content"])

    def merged_tree(self, repo: Repository, ours: str, theirs: str) -> str | None:
        """The tree of `ours` with what `theirs` changed since their merge base; None when both
        changed one path differently."""
        base = self.files_at(repo, self.merge_base(repo, ours, theirs))
        mine, other = self.files_at(repo, ours), self.files_at(repo, theirs)
        result = dict(mine)
        for path in set(base) | set(other):
            if base.get(path, {}).get("sha") == other.get(path, {}).get("sha"):
                continue  # their side did not change it
            if base.get(path, {}).get("sha") != mine.get(path, {}).get("sha") and mine.get(
                path, {}
            ).get("sha") != other.get(path, {}).get("sha"):
                return None  # both changed it, differently
            if path in other:
                result[path] = other[path]
            else:
                result.pop(path, None)
        return self.new_object(repo, "tree", {"tree": list(result.values())})

    def pushed(self, repo: Repository, sha: str) -> None:
        """A pipeline run for a commit a branch moved to, as a push starts one."""
        if self.ci_pending:
            self.create_run(repo, "ci", sha, status="in_progress", conclusion=None)
        else:
            self.create_run(repo, "ci", sha, status="completed", conclusion=self.ci_conclusion)

    def touched(self, repo: Repository, branch: str) -> None:
        """A push to a branch updates every open pull request from it, as the service's do."""
        for pull in repo.pulls.values():
            if pull["head"]["ref"] == branch and pull["state"] == "open":
                pull["updated_at"] = now()
                repo.issues[int(pull["number"])]["updated_at"] = now()

    def pull_view(self, repo: Repository, pull: Json) -> Json:
        """A pull request as the service answers it: with the commit at its head."""
        head = dict(pull["head"], sha=repo.refs.get(pull["head"]["ref"]))
        return {**pull, "head": head}

    def state(self) -> Json:
        return {
            full_name: {
                "issues": len([n for n in repo.issues if n not in repo.pulls]),
                "pulls": len(repo.pulls),
                "comments": sum(len(c) for c in repo.comments.values()),
                "runs": len(repo.runs),
                "branches": len(repo.refs),
                "references": sorted(repo.references),
                "labels": sum(len(i.get("labels", [])) for i in repo.issues.values()),
            }
            for full_name, repo in self.repositories.items()
        }


class Handler(BaseHTTPRequestHandler):
    store: Store  # set by serve()
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{now()} fake-repository {format % args}\n")

    # --- plumbing --------------------------------------------------------------------------------

    def _send(
        self, status: int, body: Json | list[Json] | None, headers: Json | None = None
    ) -> None:
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _paged(self, path: str, query: Json, items: list[Json]) -> None:
        per_page = max(1, min(100, int(query.get("per_page", 30))))
        page = max(1, int(query.get("page", 1)))
        headers = {}
        if page * per_page < len(items):
            rest = "".join(
                f"{k}={v}&" for k, v in sorted(query.items()) if k not in ("page", "per_page")
            )
            headers["Link"] = (
                f"<{self.store.base_url}{path}?{rest}per_page={per_page}"
                f'&page={page + 1}>; rel="next"'
            )
        self._send(200, items[(page - 1) * per_page : page * per_page], headers)

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def _bearer(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        match = re.fullmatch(r"(?:Bearer|token) (\S+)", header)
        return None if match is None else match.group(1)

    def _scope(self) -> str | None:
        value = self._bearer()
        if value is None:
            return None
        end = self.store.expiry.get(value)
        if end is not None and time.time() >= end:
            return None
        return self.store.tokens.get(value)

    def _login(self) -> str:
        return APP_LOGIN if self._bearer() in self.store.expiry else "fake-user"

    # --- the app ---------------------------------------------------------------------------------

    def _app_route(self, method: str, path: str, body: Json) -> bool:
        """Answer the two requests an app signs, if this is one of them."""
        installation = re.fullmatch(r"/repos/([^/]+)/([^/]+)/installation", path)
        exchange = re.fullmatch(r"/app/installations/(\d+)/access_tokens", path)
        if not ((method == "GET" and installation) or (method == "POST" and exchange)):
            return False
        if self.store.outage:
            self._send(503, {"message": "Service unavailable"})
            return True
        app = self.store.app
        if app is None or not self._signed_by(app):
            self._send(401, {"message": "A JSON web token could not be decoded"})
            return True
        with self.store.lock:
            if installation:
                if not app.installed:
                    self._send(404, {"message": "Not Found"})
                    return True
                self._send(200, {"id": APP_INSTALLATION, "app_id": app.app_id})
                return True
            assert exchange is not None
            if not app.installed or int(exchange.group(1)) != APP_INSTALLATION:
                self._send(404, {"message": "Not Found"})
                return True
            if app.suspended:
                self._send(403, {"message": "This installation has been suspended"})
                return True
            app.requested.append(body)
            token = "ghs_fake" + secrets.token_hex(16)
            end = time.time() + app.token_seconds
            app.issued.append(token)
            self.store.tokens[token] = "write"
            self.store.expiry[token] = end
            expires_at = datetime.fromtimestamp(end, UTC).isoformat(timespec="seconds")
            self._send(
                201,
                {
                    "token": token,
                    "expires_at": expires_at.replace("+00:00", "Z"),
                    "permissions": {"contents": "write", "issues": "write", "metadata": "read"},
                    "repository_selection": "selected",
                },
            )
            return True

    def _signed_by(self, app: App) -> bool:
        import jwt  # the one import outside the standard library, and only for the app

        statement = self._bearer()
        if statement is None:
            return False
        app.statements.append(statement)
        try:
            claims = jwt.decode(
                statement,
                app.public_key,
                algorithms=["RS256"],
                issuer=app.app_id,
                leeway=60,
                options={"require": ["exp", "iat", "iss"]},
            )
        except jwt.PyJWTError:
            return False
        return int(claims["exp"]) - int(claims["iat"]) <= 660

    def _guard(self, *, write: bool) -> bool:
        if self.store.hang_seconds:
            time.sleep(self.store.hang_seconds)
        if self.store.outage:
            self._send(503, {"message": "Service unavailable"})
            return False
        if self.store.answer is not None:
            self._send(int(self.store.answer["status"]), self.store.answer.get("body"))
            return False
        scope = self._scope()
        if scope is None:
            self._send(401, {"message": "Bad credentials"})
            return False
        if write and scope != "write":
            self._send(403, {"message": "Resource not accessible by integration"})
            return False
        return True

    # --- routing ---------------------------------------------------------------------------------

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if url.path == "/_fake/state":
            self._send(200, self.store.state())
            return
        if url.path == "/_fake/app":
            app = self.store.app
            self._send(
                200,
                {}
                if app is None
                else {
                    "issued": app.issued,
                    "statements": app.statements,
                    "requested": app.requested,
                },
            )
            return
        if self._app_route("GET", url.path, {}):
            return
        if not self._guard(write=False):
            return
        with self.store.lock:
            self._get(url.path, query)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        body = self._body()  # always read, so that a keep-alive connection stays in step
        if url.path == "/_fake/clone":
            # The commit a worker's workspace was cloned from, made known under its own sha: the
            # head of `main` as it is now. On the service the clone and the branches share one
            # history; here the clone is a local repository, and this joins the two (#496).
            with self.store.lock:
                repo = self.store.repository(*str(body["repository"]).split("/", 1))
                head = dict(repo.objects[repo.refs["main"]])
                sha = str(body["sha"])
                repo.objects[sha] = {**head, "sha": sha}
            self._send(200, {"sha": sha})
            return
        if url.path == "/_fake/run":
            with self.store.lock:
                repo = self.store.repository(*str(body["repository"]).split("/", 1))
                head = repo.refs[str(body["branch"])]
                status = str(body.get("status") or "completed")
                conclusion = (
                    None if status != "completed" else str(body.get("conclusion") or "success")
                )
                run = self.store.create_run(repo, "ci", head, status=status, conclusion=conclusion)
                if body.get("minutes_ago"):
                    moment = datetime.now(UTC) - timedelta(minutes=int(body["minutes_ago"]))
                    run["created_at"] = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
            self._send(201, run)
            return
        if url.path == "/_fake/date":
            with self.store.lock:
                repo = self.store.repository(*str(body["repository"]).split("/", 1))
                commit = repo.objects.get(str(body["sha"]))
                if commit is None or commit["kind"] != "commit":
                    self._send(404, {"message": "Not Found"})
                    return
                for side in ("author", "committer"):
                    commit[side] = {**(commit.get(side) or {}), "date": str(body["date"])}
            self._send(200, {"sha": commit["sha"], "date": str(body["date"])})
            return
        if url.path == "/_fake/reset":
            with self.store.lock:
                self.store.repositories.clear()
                self.store.ci_conclusion = "success"
                self.store.ci_pending = False
                self.store.answer = None
            if self.store.app is not None:
                self.store.app.installed, self.store.app.suspended = True, False
                self.store.app.token_seconds = 3600
            self._send(200, {"ok": True})
            return
        if url.path == "/_fake/app":
            app = self.store.app
            if app is None:
                self._send(404, {"message": "no app configured"})
                return
            with self.store.lock:
                if "installed" in body:
                    app.installed = bool(body["installed"])
                    if not app.installed:
                        for token in app.issued:
                            self.store.tokens.pop(token, None)
                if "suspended" in body:
                    app.suspended = bool(body["suspended"])
                if "token_seconds" in body:
                    app.token_seconds = int(body["token_seconds"])
            self._send(200, {"installed": app.installed, "suspended": app.suspended})
            return
        if self._app_route("POST", url.path, body):
            return
        if url.path == "/_fake/answer":
            self.store.answer = dict(body) if "status" in body else None
            self._send(200, {"answer": self.store.answer})
            return
        if url.path == "/_fake/outage":
            self.store.outage = bool(body.get("on"))
            self._send(200, {"outage": self.store.outage})
            return
        if url.path == "/_fake/lag":
            self.store.issue_list_lag = float(body.get("seconds") or 0)
            self._send(200, {"issue_list_lag": self.store.issue_list_lag})
            return
        if url.path == "/_fake/hang":
            self.store.hang_seconds = float(body.get("seconds") or 0)
            self._send(200, {"hang_seconds": self.store.hang_seconds})
            return
        if url.path in ("/_fake/runner", "/_fake/protect", "/_fake/alert"):
            with self.store.lock:
                repo = self.store.repository(*str(body["repository"]).split("/", 1))
                if url.path == "/_fake/runner":
                    runner = {
                        "id": 100 + len(repo.runners),
                        "name": str(body["name"]),
                        "os": "Linux",
                        "status": str(body.get("status") or "online"),
                        "busy": bool(body.get("busy")),
                        "labels": [{"id": 1, "name": "self-hosted", "type": "read-only"}],
                    }
                    repo.runners.append(runner)
                    self._send(201, runner)
                elif url.path == "/_fake/protect":
                    repo.protected.add(str(body["branch"]))
                    self._send(200, {"protected": sorted(repo.protected)})
                else:
                    alert = alert_of(self.store.base_url, repo, body)
                    repo.alerts.append(alert)
                    self._send(201, alert)
            return
        if url.path == "/_fake/ci":
            self.store.ci_conclusion = str(body.get("conclusion") or "success")
            self.store.ci_pending = bool(body.get("pending"))
            self._send(
                200, {"conclusion": self.store.ci_conclusion, "pending": self.store.ci_pending}
            )
            return
        if not self._guard(write=True):
            return
        with self.store.lock:
            self._post(url.path, body)

    def do_PATCH(self) -> None:
        """Moving a branch to another commit, as the service's reference interface does — how
        a test puts files on `main`. A move that is not a fast-forward needs `force`."""
        url = urlparse(self.path)
        body = self._body()
        if not self._guard(write=True):
            return
        with self.store.lock:
            if i := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)", url.path):
                self._patch_issue(
                    self.store.repository(i.group(1), i.group(2)), int(i.group(3)), body
                )
                return
            m = re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/refs/heads/(.+)", url.path)
            if m is None:
                self._send(404, {"message": "Not Found"})
                return
            repo = self.store.repository(m.group(1), m.group(2))
            name, sha = m.group(3), body.get("sha")
            if name not in repo.refs:
                self._send(422, {"message": "Reference does not exist"})
                return
            commit = repo.objects.get(str(sha))
            if commit is None or commit["kind"] != "commit":
                self._send(422, {"message": "Object does not exist"})
                return
            parents = {p["sha"] for p in commit.get("parents", [])}
            if repo.refs[name] not in parents and not body.get("force"):
                self._send(422, {"message": "Update is not a fast forward"})
                return
            repo.refs[name] = str(sha)
            self.store.pushed(repo, str(sha))
            self.store.touched(repo, name)
            self._send(200, {"ref": f"refs/heads/{name}", "object": {"type": "commit", "sha": sha}})

    def do_PUT(self) -> None:
        """A pull request merged at the head `sha` names (ADR-0194): 409 for another head, 405
        for one that is closed or conflicts with its base, 200 and the merge commit otherwise."""
        url = urlparse(self.path)
        body = self._body()
        if not self._guard(write=True):
            return
        with self.store.lock:
            m = re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)/merge", url.path)
            if m is None:
                self._send(404, {"message": "Not Found"})
                return
            store = self.store
            repo = store.repository(m.group(1), m.group(2))
            number = int(m.group(3))
            pull = repo.pulls.get(number)
            if pull is None:
                self._send(404, {"message": "Not Found"})
                return
            if pull["state"] != "open" or pull.get("merged"):
                self._send(405, {"message": "Pull Request is not mergeable"})
                return
            head = repo.refs.get(pull["head"]["ref"])
            if body.get("sha") is not None and body.get("sha") != head:
                self._send(
                    409, {"message": "Head branch was modified. Review and try the merge again."}
                )
                return
            base = pull["base"]["ref"]
            ours = repo.refs[base]
            tree = store.merged_tree(repo, ours, str(head))
            if tree is None:
                self._send(405, {"message": "Pull Request is not mergeable"})
                return
            title = body.get("commit_title") or f"{pull['title']} (#{number})"
            message = f"{title}\n\n{body.get('commit_message') or ''}".rstrip()
            parents = [{"sha": ours}] + (
                [{"sha": head}] if body.get("merge_method", "merge") == "merge" else []
            )
            sha = store.new_object(
                repo, "commit", {"message": message, "tree": {"sha": tree}, "parents": parents}
            )
            repo.refs[base] = sha
            store.pushed(repo, sha)
            changes = {
                "state": "closed",
                "merged": True,
                "merged_at": now(),
                "merge_commit_sha": sha,
                "updated_at": now(),
            }
            pull.update(changes)
            repo.issues[number].update(state="closed", updated_at=now())
            self._send(
                200, {"sha": sha, "merged": True, "message": "Pull Request successfully merged"}
            )

    def do_DELETE(self) -> None:
        """A label taken off an issue, as the service's issue interface does: the labels left,
        or 404 when the issue does not carry it."""
        url = urlparse(self.path)
        self._body()
        if not self._guard(write=True):
            return
        with self.store.lock:
            m = re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)/labels/(.+)", url.path)
            if m is None:
                self._send(404, {"message": "Not Found"})
                return
            repo = self.store.repository(m.group(1), m.group(2))
            issue = repo.issues.get(int(m.group(3)))
            name = unquote(m.group(4))
            if issue is None or name not in {label["name"] for label in issue["labels"]}:
                self._send(404, {"message": "Label does not exist"})
                return
            issue["labels"] = [label for label in issue["labels"] if label["name"] != name]
            self._send(200, issue["labels"])

    def _patch_issue(self, repo: Repository, number: int, body: Json) -> None:
        """An issue or a pull request changed as the issue interface changes it: its state
        (closed with a reason, or open), its title and text, and its milestone by number. A pull
        request closed so is closed, never merged."""
        issue = repo.issues.get(number)
        if issue is None:
            self._send(404, {"message": "Not Found"})
            return
        changes: Json = {k: str(body[k]) for k in ("title", "body") if k in body}
        if "state" in body:
            if body["state"] not in ("open", "closed"):
                self._send(422, {"message": "Validation Failed: state"})
                return
            changes["state"] = body["state"]
            changes["state_reason"] = body.get("state_reason")
        if "milestone" in body:
            milestone = body["milestone"]
            if milestone is not None and milestone not in repo.milestones:
                self._send(422, {"message": "Validation Failed: no such milestone"})
                return
            changes["milestone"] = None if milestone is None else repo.milestones[milestone]
        issue.update(changes, updated_at=now())
        if number in repo.pulls:
            repo.pulls[number].update(changes, updated_at=now())
        self._send(200, issue)

    def _search_code(self, query: Json) -> None:
        """The service's code search, as far as a connector asks it: `"<text>"` and one
        `repo:<owner>/<name>`, matched as a substring of each file's text on `main`, paged by
        `per_page` and `page`, in the service's shape — `total_count`, `incomplete_results`,
        `items` with `name`, `path`, `sha` and the repository."""
        m = re.fullmatch(r'"([^"]+)" repo:([^/\s]+)/([^/\s]+)', str(query.get("q", "")))
        if m is None:
            self._send(422, {"message": "Validation Failed"})
            return
        repo = self.store.repository(m.group(2), m.group(3))
        items = [
            {"name": p.rsplit("/", 1)[-1], "path": p, "sha": e["sha"],
             "repository": {"full_name": repo.full_name}}
            for p, e in sorted(self.store.files_at(repo, repo.refs.get("main")).items())
            if m.group(1) in self.store.text(repo, e)
        ]  # fmt: skip
        per_page = max(1, min(100, int(query.get("per_page", 30))))
        page = max(1, int(query.get("page", 1)))
        self._send(
            200,
            {
                "total_count": len(items),
                "incomplete_results": False,
                "items": items[(page - 1) * per_page : page * per_page],
            },
        )

    def _get(self, path: str, query: Json) -> None:
        store = self.store
        store.answered += 1
        if path == "/rate_limit":
            reset = int(time.time()) + 1800
            used = store.answered
            resources = {
                "core": {"limit": 5000, "used": used, "remaining": 5000 - used, "reset": reset},
                "search": {"limit": 30, "used": 0, "remaining": 30, "reset": reset},
                "graphql": {"limit": 5000, "used": 0, "remaining": 5000, "reset": reset},
            }
            self._send(200, {"resources": resources, "rate": resources["core"]})
            return
        if path == "/search/code":
            self._search_code(query)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/actions/runners", path):
            repo = store.repository(m.group(1), m.group(2))
            self._send(200, {"total_count": len(repo.runners), "runners": repo.runners})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/branches", path):
            repo = store.repository(m.group(1), m.group(2))
            branches = [
                {"name": n, "commit": {"sha": sha}, "protected": n in repo.protected}
                for n, sha in sorted(repo.refs.items())
            ]
            if "protected" in query:
                wanted = query["protected"] == "true"
                branches = [b for b in branches if b["protected"] is wanted]
            self._paged(path, query, branches)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/dependabot/alerts", path):
            repo = store.repository(m.group(1), m.group(2))
            states = str(query.get("state") or "open,fixed,dismissed,auto_dismissed").split(",")
            severities = query.get("severity")
            alerts = [
                a
                for a in reversed(repo.alerts)
                if a["state"] in states
                and (
                    severities is None
                    or a["security_vulnerability"]["severity"] in str(severities).split(",")
                )
            ]
            self._paged(path, query, alerts)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/milestones", path):
            repo = store.repository(m.group(1), m.group(2))
            state = query.get("state", "open")
            listed = [x for x in repo.milestones.values() if state == "all" or x["state"] == state]
            self._send(200, sorted(listed, key=lambda x: int(x["number"])))
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)/comments", path):
            repo = store.repository(m.group(1), m.group(2))
            number = int(m.group(3))
            if number not in repo.issues:
                self._send(404, {"message": "Not Found"})
                return
            per_page = max(1, min(100, int(query.get("per_page", 30))))
            page = max(1, int(query.get("page", 1)))
            comments = repo.comments[number]
            chunk = comments[(page - 1) * per_page : page * per_page]
            headers = {}
            if page * per_page < len(comments):
                headers["Link"] = (
                    f'<{store.base_url}{path}?per_page={per_page}&page={page + 1}>; rel="next"'
                )
            self._send(200, chunk, headers)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/collaborators", path):
            repo = store.repository(m.group(1), m.group(2))
            per_page = max(1, min(100, int(query.get("per_page", 30))))
            page = max(1, int(query.get("page", 1)))
            headers = {}
            if page * per_page < len(repo.collaborators):
                headers["Link"] = (
                    f'<{store.base_url}{path}?per_page={per_page}&page={page + 1}>; rel="next"'
                )
            self._send(200, repo.collaborators[(page - 1) * per_page : page * per_page], headers)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)", path):
            repo = store.repository(m.group(1), m.group(2))
            issue = repo.issues.get(int(m.group(3)))
            self._send(200, issue) if issue else self._send(404, {"message": "Not Found"})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues", path):
            repo = store.repository(m.group(1), m.group(2))
            state = query.get("state", "open")
            listed_before = time.monotonic() - store.issue_list_lag
            issues = [
                i
                for i in repo.issues.values()
                if (state == "all" or i["state"] == state)
                and repo.created[int(i["number"])] <= listed_before
            ]
            issues.sort(key=lambda i: int(i["number"]), reverse=True)
            per_page = max(1, min(100, int(query.get("per_page", 30))))
            page = max(1, int(query.get("page", 1)))
            headers = {}
            if page * per_page < len(issues):
                headers["Link"] = (
                    f"<{store.base_url}{path}?state={state}&per_page={per_page}"
                    f'&page={page + 1}>; rel="next"'
                )
            self._send(200, issues[(page - 1) * per_page : page * per_page], headers)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)/files", path):
            repo = store.repository(m.group(1), m.group(2))
            pull = repo.pulls.get(int(m.group(3)))
            head = None if pull is None else repo.refs.get(pull["head"]["ref"])
            if pull is None or head is None:
                self._send(404, {"message": "Not Found"})
                return
            base_head = repo.refs.get(pull["base"]["ref"])
            since = self.store.merge_base(repo, head, base_head) if base_head else None
            before, after = store.files_at(repo, since), store.files_at(repo, head)
            listed: list[Json] = []
            for name in sorted(set(before) | set(after)):
                if before.get(name, {}).get("sha") == after.get(name, {}).get("sha"):
                    continue
                old = store.text(repo, before.get(name)).splitlines()
                new = store.text(repo, after.get(name)).splitlines()
                diff = list(difflib.unified_diff(old, new, lineterm=""))[2:]
                listed.append(
                    {
                        "filename": name,
                        "status": "added"
                        if name not in before
                        else "removed"
                        if name not in after
                        else "modified",
                        "additions": sum(1 for d in diff if d.startswith("+")),
                        "deletions": sum(1 for d in diff if d.startswith("-")),
                        "patch": "\n".join(diff),
                    }
                )
            per_page = max(1, min(100, int(query.get("per_page", 30))))
            page = max(1, int(query.get("page", 1)))
            headers = {}
            if page * per_page < len(listed):
                headers["Link"] = (
                    f'<{store.base_url}{path}?per_page={per_page}&page={page + 1}>; rel="next"'
                )
            self._send(200, listed[(page - 1) * per_page : page * per_page], headers)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/compare/(.+)\.\.\.(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            base = store.resolve(repo, unquote(m.group(3)))
            head = store.resolve(repo, unquote(m.group(4)))
            if base is None or head is None:
                self._send(404, {"message": "Not Found"})
                return
            of_base, of_head = store.ancestors(repo, base), store.ancestors(repo, head)
            ahead = len([c for c in of_head if c not in of_base])
            behind = len([c for c in of_base if c not in of_head])
            status = (
                "identical"
                if not ahead and not behind
                else "ahead"
                if not behind
                else "behind"
                if not ahead
                else "diverged"
            )
            self._send(200, {"status": status, "ahead_by": ahead, "behind_by": behind})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)", path):
            repo = store.repository(m.group(1), m.group(2))
            pull = repo.pulls.get(int(m.group(3)))
            if pull is None:
                self._send(404, {"message": "Not Found"})
                return
            self._send(200, store.pull_view(repo, pull))
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls", path):
            repo = store.repository(m.group(1), m.group(2))
            state = query.get("state", "open")
            head = query.get("head")
            pulls = [
                p
                for p in repo.pulls.values()
                if (state == "all" or p["state"] == state)
                and (head is None or p["head"]["label"] == head)
            ]
            pulls.sort(key=lambda p: int(p["number"]), reverse=True)
            self._send(200, [store.pull_view(repo, p) for p in pulls])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/actions/runs/(\d+)", path):
            repo = store.repository(m.group(1), m.group(2))
            run = repo.runs.get(int(m.group(3)))
            self._send(200, run) if run else self._send(404, {"message": "Not Found"})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/actions/runs", path):
            repo = store.repository(m.group(1), m.group(2))
            runs = sorted(repo.runs.values(), key=lambda r: int(r["id"]), reverse=True)
            head = query.get("head_sha")
            if head is not None:
                runs = [r for r in runs if r.get("head_sha") == head]
            if query.get("status") is not None:
                runs = [r for r in runs if r.get("status") == query["status"]]
            self._send(200, {"total_count": len(runs), "workflow_runs": runs})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/ref/heads/(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            sha = repo.refs.get(m.group(3))
            if sha is None:
                self._send(404, {"message": "Not Found"})
                return
            self._send(
                200, {"ref": f"refs/heads/{m.group(3)}", "object": {"type": "commit", "sha": sha}}
            )
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/ref/(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            name = f"refs/{m.group(3)}"
            sha = repo.references.get(name)
            if sha is None:
                self._send(404, {"message": "Not Found"})
                return
            self._send(200, {"ref": name, "object": {"type": "commit", "sha": sha}})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/branches/(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            sha = repo.refs.get(m.group(3))
            if sha is None:
                self._send(404, {"message": "Branch not found"})
                return
            self._send(200, {"name": m.group(3), "commit": {"sha": sha}})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/commits", path):
            repo = store.repository(m.group(1), m.group(2))
            start = str(query.get("sha") or "main")
            start = repo.refs.get(start, start)
            if start not in repo.objects:
                self._send(404, {"message": "No commit found for SHA"})
                return
            found = store.last_change(repo, start, str(query.get("path") or ""))
            self._send(200, [] if found is None else [found])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/contents/(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            status, answer = store.contents(repo, unquote(m.group(3)), query.get("ref"))
            self._send(status, answer)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/(commits|trees|blobs)/([0-9a-f]+)", path):
            repo = store.repository(m.group(1), m.group(2))
            obj = repo.objects.get(m.group(4))
            if obj is None or obj["kind"] != m.group(3).rstrip("s"):
                self._send(404, {"message": "Not Found"})
                return
            self._send(200, obj)
            return
        self._send(404, {"message": "Not Found"})

    def _post(self, path: str, body: Json) -> None:
        store = self.store
        login = self._login()
        run_act = r"/repos/([^/]+)/([^/]+)/actions/runs/(\d+)/(rerun-failed-jobs|cancel)"
        if m := re.fullmatch(run_act, path):
            repo = store.repository(m.group(1), m.group(2))
            run = repo.runs.get(int(m.group(3)))
            if run is None:
                self._send(404, {"message": "Not Found"})
                return
            if m.group(4) == "cancel":
                if run["status"] == "completed":
                    self._send(409, {"message": "Cannot cancel a workflow run that is completed."})
                    return
                run.update(status="completed", conclusion="cancelled")
                self._send(202, {})
                return
            if run["status"] != "completed":
                self._send(403, {"message": "This workflow is already running"})
                return
            attempt = int(run.get("run_attempt", 1)) + 1
            run.update(status="queued", conclusion=None, run_attempt=attempt)
            self._send(201, {})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)/comments", path):
            repo = store.repository(m.group(1), m.group(2))
            number = int(m.group(3))
            if number not in repo.issues:
                self._send(404, {"message": "Not Found"})
                return
            if not isinstance(body.get("body"), str) or not body["body"]:
                self._send(422, {"message": "Validation Failed"})
                return
            comment = {
                "id": repo.next_comment,
                "body": body["body"],
                "user": {"login": login, "id": 1, "type": kind_of(login)},
                "html_url": (
                    f"{store.base_url}/{repo.full_name}/issues/{number}"
                    f"#issuecomment-{repo.next_comment}"
                ),
                "created_at": now(),
            }
            repo.next_comment += 1
            repo.comments[number].append(comment)
            self._send(201, comment)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues", path):
            repo = store.repository(m.group(1), m.group(2))
            if not isinstance(body.get("title"), str) or not body["title"]:
                self._send(422, {"message": "Validation Failed"})
                return
            labels, milestone = body.get("labels") or [], body.get("milestone")
            if not isinstance(labels, list) or not all(isinstance(n, str) for n in labels):
                self._send(422, {"message": "Validation Failed"})
                return
            if milestone is not None and milestone not in repo.milestones:
                self._send(422, {"message": "Validation Failed: no such milestone"})
                return
            issue = store.create_issue(repo, body["title"], body.get("body") or "", login)
            issue["labels"] = [{"name": name, "color": "ededed"} for name in labels]
            if milestone is not None:
                issue["milestone"] = repo.milestones[milestone]
            self._send(201, issue)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/milestones", path):
            repo = store.repository(m.group(1), m.group(2))
            if not isinstance(body.get("title"), str) or not body["title"]:
                self._send(422, {"message": "Validation Failed"})
                return
            number = len(repo.milestones) + 1
            repo.milestones[number] = {"number": number, "title": body["title"], "state": "open"}
            self._send(201, repo.milestones[number])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls", path):
            repo = store.repository(m.group(1), m.group(2))
            head, base = body.get("head"), body.get("base")
            if not all(isinstance(v, str) and v for v in (body.get("title"), head, base)):
                self._send(422, {"message": "Validation Failed"})
                return
            if head == base:
                self._send(422, {"message": "Validation Failed: head and base are the same"})
                return
            label = head if ":" in head else f"{repo.owner}:{head}"
            if label.split(":", 1)[1] not in repo.refs:
                self._send(
                    422,
                    {
                        "message": "Validation Failed",
                        "errors": [{"resource": "PullRequest", "field": "head", "code": "invalid"}],
                    },
                )
                return
            if any(
                p["state"] == "open" and p["head"]["label"] == label for p in repo.pulls.values()
            ):
                self._send(
                    422,
                    {
                        "message": "Validation Failed",
                        "errors": [{"message": f"A pull request already exists for {label}."}],
                    },
                )
                return
            pull = store.create_pull(
                repo,
                body["title"],
                label.split(":", 1)[1],
                base,
                body.get("body") or "",
                login,
                bool(body.get("draft", False)),
            )
            self._send(201, pull)
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)/labels", path):
            repo = store.repository(m.group(1), m.group(2))
            issue = repo.issues.get(int(m.group(3)))
            if issue is None:
                self._send(404, {"message": "Not Found"})
                return
            names = body.get("labels")
            if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
                self._send(422, {"message": "Validation Failed"})
                return
            present = {label["name"] for label in issue["labels"]}
            for name in names:
                if name not in present:
                    issue["labels"].append({"name": name, "color": "ededed"})
                    present.add(name)
            self._send(200, issue["labels"])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/merges", path):
            repo = store.repository(m.group(1), m.group(2))
            into, source = body.get("base"), body.get("head")
            if not isinstance(into, str) or into not in repo.refs or not isinstance(source, str):
                self._send(404, {"message": "Base does not exist"})
                return
            theirs = store.resolve(repo, source)
            if theirs is None:
                self._send(404, {"message": "Head does not exist"})
                return
            ours = repo.refs[into]
            if theirs in store.ancestors(repo, ours):
                self._send(204, None)
                return
            tree = store.merged_tree(repo, ours, theirs)
            if tree is None:
                self._send(409, {"message": "Merge conflict"})
                return
            message = body.get("commit_message") or f"Merge {source} into {into}"
            sha = store.new_object(
                repo,
                "commit",
                {
                    "message": message,
                    "tree": {"sha": tree},
                    "parents": [{"sha": ours}, {"sha": theirs}],
                },
            )
            repo.refs[into] = sha
            store.pushed(repo, sha)
            store.touched(repo, into)
            self._send(201, repo.objects[sha])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/blobs", path):
            repo = store.repository(m.group(1), m.group(2))
            if not isinstance(body.get("content"), str):
                self._send(422, {"message": "Validation Failed"})
                return
            sha = store.new_object(
                repo,
                "blob",
                {"content": body["content"], "encoding": body.get("encoding", "utf-8")},
            )
            self._send(201, repo.objects[sha])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/trees", path):
            repo = store.repository(m.group(1), m.group(2))
            base = body.get("base_tree")
            entries = body.get("tree")
            if not isinstance(entries, list) or (base is not None and base not in repo.objects):
                self._send(422, {"message": "Validation Failed"})
                return
            if any(str(e.get("path", "")).startswith(".github/workflows/") for e in entries):
                # An app without the right to change workflows, as Taktus's own is (#366).
                self._send(403, {"message": "Resource not accessible by integration"})
                return
            merged: dict[str, Json] = {}
            if base is not None:
                merged = {e["path"]: e for e in repo.objects[base]["tree"]}
            for entry in entries:
                if entry.get("sha") is None:
                    merged.pop(entry["path"], None)
                else:
                    merged[entry["path"]] = {k: v for k, v in entry.items()}
            sha = store.new_object(repo, "tree", {"tree": list(merged.values())})
            self._send(201, repo.objects[sha])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/commits", path):
            repo = store.repository(m.group(1), m.group(2))
            tree, parents = body.get("tree"), body.get("parents")
            if not isinstance(body.get("message"), str) or tree not in repo.objects:
                self._send(422, {"message": "Validation Failed"})
                return
            sha = store.new_object(
                repo,
                "commit",
                {
                    "message": body["message"],
                    "tree": {"sha": tree},
                    "parents": [{"sha": p} for p in (parents or [])],
                },
            )
            self._send(201, repo.objects[sha])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/refs", path):
            repo = store.repository(m.group(1), m.group(2))
            ref, sha = body.get("ref"), body.get("sha")
            if (
                not isinstance(ref, str)
                or not ref.startswith("refs/")
                or ref.count("/") < 2
                or sha not in repo.objects
            ):
                self._send(422, {"message": "Validation Failed"})
                return
            if not ref.startswith("refs/heads/"):
                if ref in repo.references:
                    self._send(422, {"message": "Reference already exists"})
                    return
                repo.references[ref] = sha
                self._send(201, {"ref": ref, "object": {"type": "commit", "sha": sha}})
                return
            name = ref.removeprefix("refs/heads/")
            if name in repo.refs:
                self._send(422, {"message": "Reference already exists"})
                return
            repo.refs[name] = sha
            if store.ci_pending:
                store.create_run(repo, "ci", sha, status="in_progress", conclusion=None)
            else:
                store.create_run(
                    repo, "ci", sha, status="completed", conclusion=store.ci_conclusion
                )
            self._send(201, {"ref": ref, "object": {"type": "commit", "sha": sha}})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/actions/workflows/([^/]+)/dispatches", path):
            repo = store.repository(m.group(1), m.group(2))
            if not isinstance(body.get("ref"), str) or not body["ref"]:
                self._send(422, {"message": "Validation Failed"})
                return
            run = {
                "id": repo.next_run,
                "name": m.group(3),
                "status": "queued",
                "conclusion": None,
                "html_url": f"{store.base_url}/{repo.full_name}/actions/runs/{repo.next_run}",
                "created_at": now(),
            }
            repo.runs[repo.next_run] = run
            repo.next_run += 1
            self._send(204, None)
            return
        self._send(404, {"message": "Not Found"})


def alert_of(base_url: str, repo: Repository, body: Json) -> Json:
    """A dependency alert in the service's shape, with the people the connector leaves out."""
    number = len(repo.alerts) + 1
    package = {"ecosystem": str(body.get("ecosystem") or "pip"), "name": str(body["package"])}
    severity = str(body.get("severity") or "high")
    patched = body.get("patched")
    return {
        "number": number,
        "state": str(body.get("state") or "open"),
        "dependency": {
            "package": package,
            "manifest_path": str(body.get("manifest") or "requirements.txt"),
            "scope": "runtime",
            "relationship": "direct",
        },
        "security_advisory": {
            "ghsa_id": str(body.get("ghsa_id") or f"GHSA-fake-{number:04d}-xxxx"),
            "cve_id": body.get("cve_id"),
            "summary": str(body.get("summary") or f"A flaw in {package['name']}"),
            "description": "A longer description.",
            "severity": severity,
        },
        "security_vulnerability": {
            "package": package,
            "severity": severity,
            "vulnerable_version_range": str(body.get("vulnerable") or "< 2.0.0"),
            "first_patched_version": None if patched is None else {"identifier": str(patched)},
        },
        "url": f"{base_url}/repos/{repo.full_name}/dependabot/alerts/{number}",
        "html_url": f"{base_url}/{repo.full_name}/security/dependabot/{number}",
        "created_at": str(body.get("created_at") or now()),
        "updated_at": now(),
        "dismissed_by": {"login": "a-person", "id": 7, "name": "A Person"},
        "assignees": [{"login": "another-person", "id": 8}],
    }


def kind_of(login: str) -> str:
    return "Bot" if login.endswith("[bot]") else "User"


def app_from_environment() -> App | None:
    raw = os.environ.get(APP_VARIABLE, "")
    if not raw:
        return None
    app_id, _, key_path = raw.partition(":")
    with open(key_path, encoding="utf-8") as handle:
        return App(app_id, handle.read())


def tokens_from_environment() -> dict[str, str]:
    raw = os.environ.get(TOKENS_VARIABLE, "")
    tokens: dict[str, str] = {}
    for entry in filter(None, raw.split(",")):
        value, _, scope = entry.partition(":")
        tokens[value] = scope or "write"
    return tokens


def make_server(
    host: str,
    port: int,
    tokens: dict[str, str],
    app: App | None = None,
    *,
    issue_list_lag: float = 0.0,
) -> ThreadingHTTPServer:
    store = Store(
        base_url=f"http://{host}:{port}", tokens=tokens, app=app, issue_list_lag=issue_list_lag
    )

    class Bound(Handler):
        pass

    Bound.store = store
    server = ThreadingHTTPServer((host, port), Bound)
    store.base_url = f"http://{host}:{server.server_address[1]}"
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake repository hosting service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9200)
    parser.add_argument(
        "--issue-list-lag",
        type=float,
        default=0.0,
        help="seconds a new issue stays out of the issue list, as on the real service",
    )
    args = parser.parse_args(argv)
    tokens = tokens_from_environment()
    app = app_from_environment()
    if not tokens and app is None:
        sys.stderr.write(f"{TOKENS_VARIABLE} is empty: no request will authenticate\n")
    server = make_server(args.host, args.port, tokens, app, issue_list_lag=args.issue_list_lag)
    sys.stderr.write(f"{now()} fake-repository listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
