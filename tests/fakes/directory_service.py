#!/usr/bin/env python3
"""A fake account directory: a SCIM 2.0 service provider (RFC 7643, RFC 7644), in memory.

The directory connector under `connectors/taktus_connectors/scim/` asks `GET /Users` and
`GET /Groups`. This fake answers both as RFC 7644 §3.4.2 states them, over accounts and groups
it holds in memory, with the protocol's error response (§3.12) for what it refuses. It exists so
that the connector can be exercised in CI without a network, a directory or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication** (§2). Every request needs `Authorization: Bearer <value>` with a value the
  fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **Paging** (§3.4.2.4). `startIndex` counts from 1 (a value below 1 is read as 1), `count` is
  at most 100 here (a larger one is answered with 100, as the RFC allows a service to); the
  answer is a `ListResponse` with `totalResults`, `itemsPerPage`, `startIndex`, `Resources`.
- **Filtering** (§3.4.2.2). Only `displayName eq "<text>"` on `/Groups` and `userName eq
  "<text>"` on `/Users` are served; any other filter is 400 with `scimType` `invalidFilter`.
- **Attributes** (§3.4.2.5). `attributes` returns only the named attributes, with `id` and
  `schemas` always.

The directory: five accounts, `u1` to `u5`. `u4` is inactive and still in the group `Admins`;
`u5` is a service account (`userType` `Service`). `Admins` holds `u1` and `u4`, `Engineering`
`u1` to `u3`. Every account carries a name, e-mail addresses and a phone number, as a directory
does, so that a test can show the connector copies none. `POST /_fake/users` and
`POST /_fake/groups` replace them with a JSON list of resources in the RFC's shape.
Test-only: `GET /_fake/state` counts the requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/directory_service.py --port 9251`.
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

USER = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
MAX_COUNT = 100
FILTERS = {"/Users": "userName", "/Groups": "displayName"}
EQUALS = re.compile(r'^\s*(\w+)\s+eq\s+"([^"]*)"\s*$')

MEMBERS = {"Admins": ["u1", "u4"], "Engineering": ["u1", "u2", "u3"]}


def user(number: int, *, active: bool = True, kind: str = "Employee") -> dict[str, Any]:
    identifier = f"u{number}"
    held = [g for g, members in MEMBERS.items() if identifier in members]
    return {
        "schemas": [USER],
        "id": identifier,
        "userName": f"account{number}@org.example",
        "userType": kind,
        "active": active,
        "name": {"givenName": f"Given{number}", "familyName": f"Family{number}"},
        "displayName": f"Person {number}",
        "emails": [{"value": f"person{number}@org.example", "primary": True}],
        "phoneNumbers": [{"value": f"+49 30 000000{number}", "type": "work"}],
        "groups": [{"value": f"g-{g.lower()}", "display": g, "type": "direct"} for g in held],
        "roles": [{"value": "billing"}] if number == 2 else [],
        "meta": {
            "resourceType": "User",
            "created": "2026-01-01T00:00:00Z",
            "lastModified": f"2026-0{number}-01T00:00:00Z",
            "location": f"/Users/{identifier}",
        },
    }


def default_users() -> list[dict[str, Any]]:
    return [user(1), user(2), user(3), user(4, active=False), user(5, kind="Service")]


def default_groups() -> list[dict[str, Any]]:
    return [
        {
            "schemas": [GROUP],
            "id": f"g-{name.lower()}",
            "displayName": name,
            "members": [{"value": m, "$ref": f"/Users/{m}", "type": "User"} for m in members],
            "meta": {"resourceType": "Group", "location": f"/Groups/g-{name.lower()}"},
        }
        for name, members in MEMBERS.items()
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.resources = {"/Users": default_users(), "/Groups": default_groups()}
        self.requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/scim+json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, status: int, kind: str | None = None) -> None:
            error: dict[str, Any] = {
                "schemas": [ERROR],
                "status": str(status),
                "detail": "refused by the fake",
            }
            if kind:
                error["scimType"] = kind
            self.answer(status, error)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            target = {"/_fake/users": "/Users", "/_fake/groups": "/Groups"}.get(path)
            if target is None:
                self.refuse(404)
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.resources[target] = json.loads(body)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200, {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                    )
                return
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else None
            if token is not None:
                with state.lock:
                    state.seen_tokens.append(token)
            if token not in state.tokens:
                self.refuse(401)
                return
            if url.path not in FILTERS:
                self.refuse(404)
                return
            self._list(url.path, parse_qs(url.query))

        def _list(self, path: str, query: dict[str, list[str]]) -> None:
            with state.lock:
                every = list(state.resources[path])
            given = query.get("filter", [None])[0]
            if given is not None:
                found = EQUALS.match(given)
                if found is None or found.group(1) != FILTERS[path]:
                    self.refuse(400, "invalidFilter")
                    return
                every = [r for r in every if r.get(found.group(1)) == found.group(2)]
            try:
                start = max(1, int(query.get("startIndex", ["1"])[0]))
                count = max(0, min(MAX_COUNT, int(query.get("count", [str(MAX_COUNT)])[0])))
            except ValueError:
                self.refuse(400, "invalidValue")
                return
            page = every[start - 1 : start - 1 + count]
            attributes = query.get("attributes", [None])[0]
            if attributes:
                wanted = {"id", "schemas", *attributes.split(",")}
                page = [{k: v for k, v in r.items() if k in wanted} for r in page]
            self.answer(
                200,
                {
                    "schemas": [LIST],
                    "totalResults": len(every),
                    "itemsPerPage": len(page),
                    "startIndex": start,
                    "Resources": page,
                },
            )

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9251)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake account directory at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
