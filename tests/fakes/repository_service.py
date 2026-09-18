#!/usr/bin/env python3
"""A fake of the repository hosting service the reference connector talks to.

The connector under `src/taktus/adapters/driven/connectors/github/` speaks the REST dialect of
that service. This fake answers the subset the connector uses — issues, pull requests, comments,
labels, pipeline runs, and the object interface for branches: references, commits, blobs,
trees — in the same shapes, with the same status codes for the same faults, and keeps
everything in memory. It exists so that the connector can be exercised in CI without a network,
an account or a secret: the conformance gate starts it as a process, the adapter tests start it
in a thread.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_REPOSITORY_TOKENS`, `value:scope,...`; scope `read` or `write`).
  No or unknown value: 401. A `read` scope on a write: 403. This is what lets the tests show
  that the connector acts with the requesting identity's credential and no other.
- **Pull request uniqueness.** A second open pull request for the same head branch is refused
  with 422, as the real service does.
- **Paging.** Comment lists page with `per_page`/`page` and a `Link: <…>; rel="next"` header.
- **A pipeline per push.** Creating a reference creates one completed pipeline run for its
  commit, concluded `success` unless `POST /_fake/ci` said otherwise (`{"conclusion":
  "failure"}`, or `{"pending": true}` for a run that never completes), so that a process can
  read the pipeline's verdict for a branch it created.

Test-only endpoints under `/_fake/`: `GET /_fake/state` counts what exists, `POST /_fake/reset`
empties the store, `POST /_fake/outage` with `{"on": true}` makes every other request answer 503
until switched off, `POST /_fake/hang` with `{"seconds": 2}` makes every other request wait
that long before answering, so that a client's timeout can be provoked. Standard library only;
runnable as `python3 tests/fakes/repository_service.py --port 9200`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

TOKENS_VARIABLE = "FAKE_REPOSITORY_TOKENS"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Repository:
    owner: str
    name: str
    issues: dict[int, Json] = field(default_factory=dict)  # pull requests are issues too
    pulls: dict[int, Json] = field(default_factory=dict)
    comments: dict[int, list[Json]] = field(default_factory=dict)
    runs: dict[int, Json] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)  # branch name -> commit sha
    objects: dict[str, Json] = field(default_factory=dict)  # sha -> blob | tree | commit
    next_number: int = 1
    next_comment: int = 1
    next_run: int = 1
    next_object: int = 1

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class Store:
    base_url: str
    tokens: dict[str, str]  # value -> scope
    repositories: dict[str, Repository] = field(default_factory=dict)
    outage: bool = False
    hang_seconds: float = 0.0
    ci_conclusion: str = "success"
    ci_pending: bool = False
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
        repo.objects[sha] = {
            "sha": sha,
            "kind": kind,
            "html_url": f"{self.base_url}/{repo.full_name}/{kind}/{sha}",
            **body,
        }
        return sha

    def create_run(
        self, repo: Repository, name: str, head_sha: str, *, status: str, conclusion: str | None
    ) -> Json:
        run = {
            "id": repo.next_run,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "head_sha": head_sha,
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
            "user": {"login": login, "id": 1000 + len(repo.issues), "type": "User"},
            "labels": [],
            "html_url": f"{self.base_url}/{repo.full_name}/issues/{number}",
            "created_at": now(),
            "updated_at": now(),
        }
        repo.issues[number] = issue
        repo.comments[number] = []
        return issue

    def create_pull(
        self, repo: Repository, title: str, head: str, base: str, body: str, login: str
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
        }
        repo.pulls[number] = pull
        return pull

    def state(self) -> Json:
        return {
            full_name: {
                "issues": len([n for n in repo.issues if n not in repo.pulls]),
                "pulls": len(repo.pulls),
                "comments": sum(len(c) for c in repo.comments.values()),
                "runs": len(repo.runs),
                "branches": len(repo.refs),
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

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def _scope(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        match = re.fullmatch(r"(?:Bearer|token) (\S+)", header)
        if match is None:
            return None
        return self.store.tokens.get(match.group(1))

    def _guard(self, *, write: bool) -> bool:
        if self.store.hang_seconds:
            time.sleep(self.store.hang_seconds)
        if self.store.outage:
            self._send(503, {"message": "Service unavailable"})
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
        if not self._guard(write=False):
            return
        with self.store.lock:
            self._get(url.path, query)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        body = self._body()  # always read, so that a keep-alive connection stays in step
        if url.path == "/_fake/reset":
            with self.store.lock:
                self.store.repositories.clear()
                self.store.ci_conclusion = "success"
                self.store.ci_pending = False
            self._send(200, {"ok": True})
            return
        if url.path == "/_fake/outage":
            self.store.outage = bool(body.get("on"))
            self._send(200, {"outage": self.store.outage})
            return
        if url.path == "/_fake/hang":
            self.store.hang_seconds = float(body.get("seconds") or 0)
            self._send(200, {"hang_seconds": self.store.hang_seconds})
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

    def _get(self, path: str, query: Json) -> None:
        store = self.store
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
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)", path):
            repo = store.repository(m.group(1), m.group(2))
            issue = repo.issues.get(int(m.group(3)))
            self._send(200, issue) if issue else self._send(404, {"message": "Not Found"})
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues", path):
            repo = store.repository(m.group(1), m.group(2))
            state = query.get("state", "open")
            issues = [i for i in repo.issues.values() if state == "all" or i["state"] == state]
            issues.sort(key=lambda i: int(i["number"]), reverse=True)
            self._send(200, issues[: int(query.get("per_page", 30))])
            return
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)", path):
            repo = store.repository(m.group(1), m.group(2))
            pull = repo.pulls.get(int(m.group(3)))
            self._send(200, pull) if pull else self._send(404, {"message": "Not Found"})
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
            self._send(200, pulls)
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
        if m := re.fullmatch(r"/repos/([^/]+)/([^/]+)/branches/(.+)", path):
            repo = store.repository(m.group(1), m.group(2))
            sha = repo.refs.get(m.group(3))
            if sha is None:
                self._send(404, {"message": "Branch not found"})
                return
            self._send(200, {"name": m.group(3), "commit": {"sha": sha}})
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
        login = "fake-user"
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
                "user": {"login": login, "id": 1, "type": "User"},
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
            self._send(201, store.create_issue(repo, body["title"], body.get("body") or "", login))
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
                repo, body["title"], label.split(":", 1)[1], base, body.get("body") or "", login
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
                or not ref.startswith("refs/heads/")
                or sha not in repo.objects
            ):
                self._send(422, {"message": "Validation Failed"})
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


def tokens_from_environment() -> dict[str, str]:
    raw = os.environ.get(TOKENS_VARIABLE, "")
    tokens: dict[str, str] = {}
    for entry in filter(None, raw.split(",")):
        value, _, scope = entry.partition(":")
        tokens[value] = scope or "write"
    return tokens


def make_server(host: str, port: int, tokens: dict[str, str]) -> ThreadingHTTPServer:
    store = Store(base_url=f"http://{host}:{port}", tokens=tokens)

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
    args = parser.parse_args(argv)
    tokens = tokens_from_environment()
    if not tokens:
        sys.stderr.write(f"{TOKENS_VARIABLE} is empty: no request will authenticate\n")
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"{now()} fake-repository listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
