#!/usr/bin/env python3
"""A fake hosting platform: the part of the Vercel REST API the site connector uses, in memory.

The connector under `connectors/taktus_connectors/vercel/` asks:

- `GET /v9/projects/<idOrName>`: the project, with `targets.production` the deployment its
  production serves and `lastAliasRequest` the newest promotion or rollback; 404 for a project
  it does not hold;
- `GET /v13/deployments/<id>`: the deployment with its `readyState`, `readySubstate`, `target`
  and `projectId`; 404 for one it does not hold;
- `POST /v10/projects/<projectId>/promote/<deploymentId>`: production pointed at the
  deployment, answered 201, or 202 while promotions are held pending;
- `POST /v1/projects/<projectId>/rollback/<deploymentId>`: production pointed back at it,
  answered 201.

A write names the project by its identifier, as the API's paths do; a read takes its name too.
A deployment that is not `READY` is refused with 422 by both writes. A `teamId` query, where
given, must be the team the fake holds, `team_example`; otherwise 403.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **A promotion can wait.** `POST /_fake/promotion` with `{"pending": true}` makes a promotion
  answer 202 and leave production where it was, `lastAliasRequest.jobStatus` `in-progress`,
  until `{"pending": false}` carries every waiting one out.

The project `web` (`prj_` and an identifier) holds three deployments, oldest first: one `READY`
that production serves, one `READY` built for production and not promoted (`STAGED`), one in
`ERROR`. Test-only: `GET /_fake/state` names each project's production deployment and its
deployments oldest first, and counts the requests and the writes; `POST /_fake/reset` restores
the start. Standard library only; runnable as
`python3 tests/fakes/site_deployments_service.py --port 9234`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

PROJECT = "prj_8Yq2cWb3dV4eX5fZ6gA7hB8iC9jD"
TEAM = "team_example"
DEPLOYMENTS = (
    "dpl_4gHkT8mW2nR6pV9sX3yZ5aB7cD1e",
    "dpl_6jLnQ2rT5uW8xA1bC4dE7fG0hI3k",
    "dpl_9mOpS1tV4wY7zB0cD3eF6gH9iJ2l",
)
"""The deployments of the project `web`, oldest first: production, staged, failed."""


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.writes = 0
        self.pending = False
        first, second, third = DEPLOYMENTS
        self.deployments: dict[str, Json] = {
            first: self._deployment(first, "READY", "PROMOTED"),
            second: self._deployment(second, "READY", "STAGED"),
            third: self._deployment(third, "ERROR", None),
        }
        self.production: str | None = first
        self.last: Json | None = None
        self.waiting: str | None = None

    @staticmethod
    def _deployment(identifier: str, ready: str, substate: str | None) -> Json:
        made: Json = {
            "id": identifier,
            "name": "web",
            "projectId": PROJECT,
            "url": f"web-{identifier[4:13].lower()}.vercel.app",
            "readyState": ready,
            "target": "production",
            "createdAt": 1762500000000,
        }
        if substate is not None:
            made["readySubstate"] = substate
        return made

    def project(self) -> Json:
        production = self.deployments.get(self.production or "")
        return {
            "id": PROJECT,
            "name": "web",
            "accountId": TEAM,
            "targets": {"production": dict(production)} if production else {},
            "lastAliasRequest": dict(self.last) if self.last else None,
        }

    def point(self, kind: str, identifier: str) -> int:
        """Point production at the deployment, or hold the promotion; the status answered."""
        self.writes += 1
        self.last = {
            "type": kind,
            "fromDeploymentId": self.production,
            "toDeploymentId": identifier,
            "jobStatus": "in-progress",
            "requestedAt": 1762510000000,
        }
        if kind == "promote" and self.pending:
            self.waiting = identifier
            return 202
        self.finish(identifier)
        return 201

    def finish(self, identifier: str) -> None:
        if self.production in self.deployments:
            self.deployments[self.production]["readySubstate"] = "STAGED"
        self.production = identifier
        self.deployments[identifier]["readySubstate"] = "PROMOTED"
        if self.last is not None:
            self.last["jobStatus"] = "succeeded"
        self.waiting = None

    def summary(self) -> Json:
        return {
            "requests": self.requests,
            "writes": self.writes,
            "sites": {"web": {"live": self.production, "versions": list(self.deployments)}},
        }


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    project_path = re.compile(r"/v9/projects/([^/]+)")
    deployment_path = re.compile(r"/v13/deployments/([^/]+)")
    write_path = re.compile(
        r"/v10/projects/([^/]+)/(promote)/([^/]+)|/v1/projects/([^/]+)/(rollback)/([^/]+)"
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write(f"fake-site-deployments {format % args}\n")

        def answer(self, status: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def error(self, code: int, kind: str, message: str) -> None:
            self.answer(code, {"error": {"code": kind, "message": message}})

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            return json.loads(raw) if raw else {}

        def admitted(self, query: str) -> bool:
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            if given not in state.tokens:
                self.error(401, "forbidden", "Not authorized")
                return False
            team = parse_qs(query).get("teamId")
            if team is not None and team != [TEAM]:
                self.error(403, "forbidden", "You don't have permission to access this team")
                return False
            return True

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.summary())
                return
            if not self.admitted(url.query):
                return
            with state.lock:
                state.requests += 1
                if m := project_path.fullmatch(url.path):
                    if m.group(1) not in (PROJECT, "web"):
                        self.error(404, "not_found", "Project not found")
                    else:
                        self.answer(200, state.project())
                    return
                if m := deployment_path.fullmatch(url.path):
                    found = state.deployments.get(m.group(1))
                    if found is None:
                        self.error(404, "not_found", "Deployment not found")
                    else:
                        self.answer(200, found)
                    return
                self.error(404, "not_found", "Not found")

        def do_POST(self) -> None:
            url = urlparse(self.path)
            body = self.body()
            with state.lock:
                if url.path == "/_fake/reset":
                    state.reset()
                    self.answer(200, {})
                    return
                if url.path == "/_fake/promotion":
                    state.pending = bool(body.get("pending"))
                    if not state.pending and state.waiting is not None:
                        state.finish(state.waiting)
                    self.answer(200, {"pending": state.pending})
                    return
            if not self.admitted(url.query):
                return
            with state.lock:
                state.requests += 1
                m = write_path.fullmatch(url.path)
                if m is None:
                    self.error(404, "not_found", "Not found")
                    return
                project = m.group(1) or m.group(4)
                kind = m.group(2) or m.group(5)
                identifier = m.group(3) or m.group(6)
                if project != PROJECT:
                    self.error(404, "not_found", "Project not found")
                    return
                found = state.deployments.get(identifier)
                if found is None:
                    self.error(404, "not_found", "Deployment not found")
                    return
                if found["readyState"] != "READY":
                    self.error(422, "deployment_not_ready", "The deployment is not ready")
                    return
                status = state.point(kind, identifier)
                self.answer(status, {} if status == 202 else {"id": identifier})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9234)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake site deployments at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
