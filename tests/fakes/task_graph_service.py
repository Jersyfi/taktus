#!/usr/bin/env python3
"""A fake task tracker: the issues and comments of the Linear GraphQL API, in memory.

The task tracker connector under `connectors/taktus_connectors/linear/` posts GraphQL
documents to `POST /graphql`. This fake answers the root fields the connector asks —
`issues`, `issue`, `issue { comments }`, `commentCreate`, `team { issues }` and `issueCreate` —
in the API's shapes: Relay
connections with `nodes` and `pageInfo { hasNextPage endCursor }`, `first` defaulting to 50,
the filter comparators `nin` on `state.type`, `lte`/`lt` on `dueDate` and `contains` on
`description`, `issueCreate` answering `success` and the `issue`, and GraphQL errors
in `errors` with `extensions.type` (https://linear.app/developers/graphql,
https://linear.app/developers/pagination, https://linear.app/developers/filtering). It
parses no GraphQL grammar: it recognises the root field of a document and reads its variables,
which is all the connector's fixed documents need.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: <key>` with a key of `FAKE_TOKENS` (comma separated), no
  prefix, as a personal API key is sent. Otherwise HTTP 400 with an error of type
  `authentication error` and no data.
- **The filter.** A filter key other than `state` and `dueDate` is an `invalid input` error.
- **One issue.** An identifier or key it does not hold is an `invalid input` error, data null.
- **One team.** Its issues belong to the team `TEAM`; another team is `Entity not found`. A new
  issue needs `teamId` and a `title`, and takes the next key, `TSK-6` first.
- **Throttling.** After `POST /_fake/throttle`, every request is HTTP 429 with the code
  `RATELIMITED`, as the rate-limiting page states.

The issues: five, `TSK-1` to `TSK-5`, due ten days ago, yesterday, in five days, without a due
date, and three days ago but completed. Each is assigned to a named person, whom the fake
answers only if asked, so that a test shows the connector never asks. Test-only:
`GET /_fake/state` counts the requests and lists every comment written.
Standard library only; runnable as `python3 tests/fakes/task_graph_service.py --port 9254`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def _day(offset: int | None) -> str | None:
    if offset is None:
        return None
    return (datetime.now(UTC).date() + timedelta(days=offset)).isoformat()


TEAM = "00000000-0000-4000-8000-0000000000aa"
"""The one team the fake holds."""


def default_issues() -> list[dict[str, Any]]:
    rows = [
        (1, -10, "In Progress", "started"),
        (2, -1, "Todo", "unstarted"),
        (3, 5, "Todo", "unstarted"),
        (4, None, "Backlog", "backlog"),
        (5, -3, "Done", "completed"),
    ]
    return [
        {
            "id": f"00000000-0000-4000-8000-00000000000{n}",
            "identifier": f"TSK-{n}",
            "title": f"Task {n}",
            "dueDate": _day(offset),
            "url": f"https://tracker.example/team/issue/TSK-{n}",
            "createdAt": "2026-10-01T09:00:00.000Z",
            "updatedAt": "2026-10-20T09:00:00.000Z",
            "description": None,
            "state": {"name": name, "type": kind},
            "assignee": {"name": f"Person {n}", "email": f"person{n}@team.example"},
            "comments": [],
        }
        for n, offset, name, kind in rows
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.issues = default_issues()
        self.relations: list[dict[str, str]] = []
        """Every relation made, `{issue, related, type}` by the tasks' ids."""
        self.requests = 0
        self.throttled = False
        self.lock = threading.Lock()


def _error(kind: str, message: str) -> dict[str, Any]:
    return {"message": message, "extensions": {"type": kind, "userError": True}}


def _page(items: list[dict[str, Any]], variables: dict[str, Any]) -> tuple[list[Any], bool]:
    first = variables.get("first") or 50
    after = variables.get("after")
    if after is not None:
        ids = [item["id"] for item in items]
        items = items[ids.index(after) + 1 :] if after in ids else []
    return items[:first], len(items) > first


def _due_holds(issue: dict[str, Any], test: dict[str, Any]) -> bool:
    due = issue["dueDate"]
    if due is None:
        return False
    if "lte" in test and not due <= test["lte"]:
        return False
    return not ("lt" in test and not due < test["lt"])


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/_fake/state":
                self.answer(404, {})
                return
            with state.lock:
                comments = [
                    {"issue": i["identifier"], **c} for i in state.issues for c in i["comments"]
                ]
                created = [
                    {k: v for k, v in i.items() if k != "comments"}
                    for i in state.issues
                    if i.get("created")
                ]
                self.answer(
                    200,
                    {
                        "requests": state.requests,
                        "comments": comments,
                        "created": created,
                        "relations": list(state.relations),
                    },
                )

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/_fake/throttle":
                state.throttled = True
                self.answer(200, {"ok": True})
                return
            if path == "/_fake/issues":
                with state.lock:
                    state.issues = json.loads(body)
                self.answer(200, {"ok": True})
                return
            if path != "/graphql":
                self.answer(404, {})
                return
            with state.lock:
                state.requests += 1
            if state.throttled:
                self.answer(
                    429,
                    {"errors": [{"message": "Rate limit exceeded",
                                 "extensions": {"code": "RATELIMITED"}}]},
                )  # fmt: skip
                return
            if (self.headers.get("Authorization") or "") not in state.tokens:
                self.answer(400, {"errors": [_error("authentication error", "not authenticated")]})
                return
            try:
                request = json.loads(body)
                query, variables = request["query"], request.get("variables") or {}
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"errors": [_error("invalid input", "unreadable request")]})
                return
            with state.lock:
                self.answer(200, self._resolve(query, variables))

        def _resolve(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
            if re.search(r"\bissueRelationCreate\s*\(", query):
                return self._relate(variables.get("input") or {})
            if re.search(r"\bcommentCreate\s*\(", query):
                return self._comment(variables.get("input") or {})
            if re.search(r"\bissueCreate\s*\(", query):
                return self._create(variables.get("input") or {})
            if re.search(r"\bteam\s*\(", query):
                return self._team(variables)
            if re.search(r"\bissues\s*\(", query):
                return self._issues(variables)
            if re.search(r"\bissue\s*\(", query):
                found = [
                    i for i in state.issues if variables.get("id") in (i["id"], i["identifier"])
                ]
                if not found:
                    return {"data": None, "errors": [_error("invalid input", "Entity not found")]}
                if re.search(r"\bcomments\s*\(", query):
                    nodes, more = _page(found[0]["comments"], variables)
                    end = nodes[-1]["id"] if nodes else None
                    page = {"hasNextPage": more, "endCursor": end}
                    comments = {"nodes": nodes, "pageInfo": page}
                    return {"data": {"issue": {"id": found[0]["id"], "comments": comments}}}
                if re.search(r"\brelations\s*\(", query):
                    mine = [r["related"] for r in state.relations if r["issue"] == found[0]["id"]]
                    nodes = [
                        {"relatedIssue": {"id": i["id"], "identifier": i["identifier"]}}
                        for i in state.issues
                        if i["id"] in mine
                    ]
                    issue = {
                        "id": found[0]["id"],
                        "identifier": found[0]["identifier"],
                        "relations": {"nodes": nodes},
                    }
                    return {"data": {"issue": issue}}
                return {"data": {"issue": self._node(found[0], query)}}
            return {"data": None, "errors": [_error("invalid input", "unknown field")]}

        def _node(self, issue: dict[str, Any], query: str) -> dict[str, Any]:
            hidden = ("assignee", "comments", "created")
            node = {k: v for k, v in issue.items() if k not in hidden}
            if re.search(r"\bassignee\b", query):
                node["assignee"] = issue["assignee"]
            return node

        def _issues(self, variables: dict[str, Any]) -> dict[str, Any]:
            given = variables.get("filter") or {}
            if set(given) - {"state", "dueDate"}:
                return {"data": None, "errors": [_error("invalid input", "unknown filter")]}
            excluded = ((given.get("state") or {}).get("type") or {}).get("nin") or []
            chosen = [i for i in state.issues if i["state"]["type"] not in excluded]
            if "dueDate" in given:
                chosen = [i for i in chosen if _due_holds(i, given["dueDate"])]
            nodes, more = _page(chosen, variables)
            end = nodes[-1]["id"] if nodes else None
            return {
                "data": {
                    "issues": {
                        "nodes": [self._node(i, "") for i in nodes],
                        "pageInfo": {"hasNextPage": more, "endCursor": end},
                    }
                }
            }

        def _team(self, variables: dict[str, Any]) -> dict[str, Any]:
            if variables.get("team") != TEAM:
                return {"data": None, "errors": [_error("invalid input", "Entity not found")]}
            given = variables.get("filter") or {}
            if set(given) - {"description"}:
                return {"data": None, "errors": [_error("invalid input", "unknown filter")]}
            text = (given.get("description") or {}).get("contains")
            chosen = [
                i for i in state.issues if text is None or text in (i.get("description") or "")
            ]
            nodes, more = _page(chosen, variables)
            end = nodes[-1]["id"] if nodes else None
            page = {"hasNextPage": more, "endCursor": end}
            issues = {"nodes": [self._node(i, "") for i in nodes], "pageInfo": page}
            return {"data": {"team": {"issues": issues}}}

        def _create(self, given: dict[str, Any]) -> dict[str, Any]:
            if given.get("teamId") != TEAM:
                return {"data": None, "errors": [_error("invalid input", "Entity not found")]}
            if not isinstance(given.get("title"), str) or not given["title"]:
                return {"data": None, "errors": [_error("invalid input", "title is required")]}
            n = len(state.issues) + 1
            now = datetime.now(UTC).isoformat()
            issue = {
                "id": f"00000000-0000-4000-8000-{n:012d}",
                "identifier": f"TSK-{n}",
                "title": given["title"],
                "dueDate": None,
                "url": f"https://tracker.example/team/issue/TSK-{n}",
                "createdAt": now,
                "updatedAt": now,
                "description": given.get("description"),
                "state": {"name": "Todo", "type": "unstarted"},
                "assignee": None,
                "comments": [],
                "created": True,
            }
            state.issues.append(issue)
            node = self._node(issue, "")
            return {"data": {"issueCreate": {"success": True, "issue": node}}}

        def _relate(self, given: dict[str, Any]) -> dict[str, Any]:
            def find(value: Any) -> dict[str, Any] | None:
                return next((i for i in state.issues if value in (i["id"], i["identifier"])), None)

            issue, other = find(given.get("issueId")), find(given.get("relatedIssueId"))
            if issue is None or other is None:
                return {"data": None, "errors": [_error("invalid input", "Entity not found")]}
            if given.get("type") not in ("blocks", "duplicate", "related", "similar"):
                return {"data": None, "errors": [_error("invalid input", "invalid relation type")]}
            state.relations.append(
                {"issue": issue["id"], "related": other["id"], "type": given["type"]}
            )
            return {"data": {"issueRelationCreate": {"success": True}}}

        def _comment(self, given: dict[str, Any]) -> dict[str, Any]:
            found = [i for i in state.issues if given.get("issueId") in (i["id"], i["identifier"])]
            if not found or not isinstance(given.get("body"), str):
                return {"data": None, "errors": [_error("invalid input", "Entity not found")]}
            comment = {"id": f"cmt-{sum(len(i['comments']) for i in state.issues) + 1}",
                       "body": given["body"]}  # fmt: skip
            found[0]["comments"].append(comment)
            return {"data": {"commentCreate": {"success": True, "comment": {"id": comment["id"]}}}}

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9254)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake task tracker at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
