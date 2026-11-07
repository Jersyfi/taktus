#!/usr/bin/env python3
"""A fake workspace's activity reports: the Google Workspace Admin SDK Reports API's
`activities.list` and the OAuth 2.0 token endpoint a service account signs into, in memory.

The workspace audit connector under `connectors/taktus_connectors/googleworkspace/` exchanges a
signed assertion for an access token and lists activities with it. This fake answers both in the
shapes the service's documentation states (`activities.list`; "Using OAuth 2.0 for Server to
Server Applications"), over activities it holds in memory.

What it enforces, because the connector's checks depend on it:

- **The assertion.** `POST /token` takes `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`
  and an `assertion`, a JWT whose `iss` is a service account the fake was started with
  (`FAKE_TOKENS`, comma separated client e-mail addresses), whose `scope` is
  `admin.reports.audit.readonly`, whose `sub` names an administrator, whose `aud` is this
  endpoint and which has not expired. Anything else is 400 `invalid_grant`. The fake does not
  verify the signature — only the service holds the public key — and says so here.
- **The access token.** `GET /admin/reports/v1/activity/users/all/applications/<application>`
  needs `Authorization: Bearer <token>` with a token the endpoint issued. Otherwise 401.
- **The request.** The application is one of the documented names (`admin`, `login`, `token`,
  `saml`, `groups`, `user_accounts`, `drive`) or 400; `startTime` is RFC 3339 or 400 and keeps
  the activities at or after it; `maxResults` is 1 to 1000 (default 1000; the documentation
  names no maximum, this fake keeps 1000); `pageToken` is a `nextPageToken` it gave.

The activities: by default three in the past hour of the application `admin` — an
`ASSIGN_ROLE` of the type `DELEGATED_ADMIN_SETTINGS`, a `CREATE_GROUP` and a
`CHANGE_GROUP_SETTING` of the type `GROUP_SETTINGS` — each with the actor's address, a profile
id and an IP address, unless a test replaced them with `POST /_fake/activities`, a JSON list of
activities in the API's shape. Test-only: `GET /_fake/state` counts the requests and names the
service accounts and bearer tokens seen. Standard library only; runnable as
`python3 tests/fakes/workspace_reports_service.py --port 9253`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

SCOPE = "https://www.googleapis.com/auth/admin.reports.audit.readonly"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
PATH = re.compile(r"^/admin/reports/v1/activity/users/all/applications/([a-z_]+)$")
APPLICATIONS = {"admin", "login", "token", "saml", "groups", "user_accounts", "drive"}


def activity(
    number: int,
    kind: str,
    name: str,
    minutes_ago: float,
    actor: str = "admin@org.example",
    **parameters: str,
) -> dict[str, Any]:
    at = datetime.fromtimestamp(time.time() - minutes_ago * 60, UTC)
    return {
        "kind": "audit#activity",
        "id": {
            "time": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "uniqueQualifier": f"-{1000 + number}",
            "applicationName": "admin",
            "customerId": "C03az79cb",
        },
        "actor": {"callerType": "USER", "email": actor, "profileId": f"1{number:05d}"},
        "ipAddress": f"203.0.113.{number}",
        "events": [
            {
                "type": kind,
                "name": name,
                "parameters": [{"name": k, "value": v} for k, v in parameters.items()],
            }
        ],
    }


def default_activities() -> list[dict[str, Any]]:
    return [
        activity(1, "DELEGATED_ADMIN_SETTINGS", "ASSIGN_ROLE", 5, ROLE_NAME="Super Admin",
                 USER_EMAIL="someone@org.example"),
        activity(2, "GROUP_SETTINGS", "CREATE_GROUP", 15, GROUP_EMAIL="team@org.example"),
        activity(3, "GROUP_SETTINGS", "CHANGE_GROUP_SETTING", 25, GROUP_EMAIL="team@org.example"),
    ]  # fmt: skip


def _claims(assertion: str) -> dict[str, Any] | None:
    parts = assertion.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        claims = json.loads(payload)
    except ValueError:
        return None
    return claims if isinstance(claims, dict) else None


class State:
    def __init__(self, accounts: set[str]) -> None:
        self.accounts = accounts
        self.activities = default_activities()
        self.issued: set[str] = set()
        self.requests = 0
        self.seen_accounts: list[str] = []
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


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

        def refuse(self, status: int, reason: str) -> None:
            self.answer(
                status,
                {"error": {"code": status, "message": f"refused by the fake: {reason}",
                           "errors": [{"reason": reason}]}},
            )  # fmt: skip

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/_fake/activities":
                with state.lock:
                    state.activities = json.loads(body)
                self.answer(200, {"ok": True})
                return
            if path != "/token":
                self.refuse(404, "notFound")
                return
            with state.lock:
                state.requests += 1
            form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
            claims = _claims(form.get("assertion", "")) if form.get("grant_type") == GRANT else None
            if claims is not None:
                with state.lock:
                    state.seen_accounts.append(str(claims.get("iss")))
            if (
                claims is None
                or claims.get("iss") not in state.accounts
                or claims.get("scope") != SCOPE
                or not claims.get("sub")
                or not str(claims.get("aud", "")).endswith("/token")
                or not isinstance(claims.get("exp"), int)
                or claims["exp"] < time.time()
            ):
                self.answer(400, {"error": "invalid_grant", "error_description": "refused"})
                return
            token = "ya29.fake-" + secrets.token_hex(12)
            with state.lock:
                state.issued.add(token)
            self.answer(200, {"access_token": token, "expires_in": 3599, "token_type": "Bearer"})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200,
                        {"requests": state.requests, "seen_accounts": list(state.seen_accounts),
                         "seen_tokens": list(state.seen_tokens)},
                    )  # fmt: skip
                return
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            if token is not None:
                with state.lock:
                    state.seen_tokens.append(token)
            if token not in state.issued:
                self.refuse(401, "authError")
                return
            found = PATH.match(url.path)
            if found is None:
                self.refuse(404, "notFound")
                return
            if found.group(1) not in APPLICATIONS:
                self.refuse(400, "invalid")
                return
            self._list(found.group(1), parse_qs(url.query))

        def _list(self, application: str, query: dict[str, list[str]]) -> None:
            with state.lock:
                every = [a for a in state.activities if a["id"]["applicationName"] == application]
            start = query.get("startTime", [None])[0]
            if start is not None:
                try:
                    bound = datetime.fromisoformat(start.replace("Z", "+00:00"))
                except ValueError:
                    self.refuse(400, "invalid")
                    return
                every = [
                    a
                    for a in every
                    if datetime.fromisoformat(a["id"]["time"].replace("Z", "+00:00")) >= bound
                ]
            every.sort(key=lambda a: a["id"]["time"], reverse=True)
            try:
                size = int(query.get("maxResults", ["1000"])[0])
                offset = int(query.get("pageToken", ["0"])[0])
            except ValueError:
                self.refuse(400, "invalid")
                return
            if not 1 <= size <= 1000:
                self.refuse(400, "invalid")
                return
            body: dict[str, Any] = {
                "kind": "reports#activities",
                "etag": '"fake"',
                "items": every[offset : offset + size],
            }
            if offset + size < len(every):
                body["nextPageToken"] = str(offset + size)
            self.answer(200, body)

    return Handler


def make_server(host: str, port: int, accounts: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(accounts)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9253)
    args = parser.parse_args()
    accounts = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, accounts)
    sys.stderr.write(f"fake workspace reports at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
