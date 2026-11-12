#!/usr/bin/env python3
"""A fake hosting service: the part of the Netlify API the site connector uses, in memory.

The connector under `connectors/taktus_connectors/netlify/` asks, under `/api/v1/`:

- `GET sites/<site_id>`: the site, with `published_deploy` the deploy it publishes; 404 for a
  site it does not hold;
- `GET sites/<site_id>/deploys/<deploy_id>`: the deploy with its `state`; 404 for one the site
  does not hold;
- `POST sites/<site_id>/deploys/<deploy_id>/restore`: the deploy published, answered 201 with
  it, as `restoreSiteDeploy` answers. A deploy that is not `ready` is refused with 422.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **One published deploy per site.** A restore makes the deploy the site's published one and
  stamps its `published_at`.

The site `web` holds three deploys, oldest first: one `ready` and published, one `ready` and not
published, one in `error`. Their identifiers are 24 hexadecimal digits, as the service's are.
Test-only: `GET /_fake/state` names each site's published deploy and its deploys oldest first,
and counts the requests and the restores; `POST /_fake/reset` restores the start. Standard
library only; runnable as `python3 tests/fakes/site_deploys_service.py --port 9233`.
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
from urllib.parse import urlparse

type Json = dict[str, Any]

DEPLOYS = ("6553f2a1c0de4b0008a1b201", "6553f2a1c0de4b0008a1b202", "6553f2a1c0de4b0008a1b203")
"""The deploys of the site `web`, oldest first: published, ready, failed."""


def deploy(site: str, identifier: str, state: str, published: bool) -> Json:
    return {
        "id": identifier,
        "site_id": site,
        "state": state,
        "name": site,
        "deploy_url": f"https://{identifier}--{site}.netlify.app",
        "published_at": "2026-11-01T10:00:00.000Z" if published else None,
        "created_at": "2026-11-01T09:00:00.000Z",
        "error_message": "Build script returned non-zero exit code: 2"
        if state == "error"
        else None,
        "context": "production",
    }


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.restores = 0
        first, second, third = DEPLOYS
        self.deploys: dict[str, dict[str, Json]] = {
            "web": {
                first: deploy("web", first, "ready", True),
                second: deploy("web", second, "ready", False),
                third: deploy("web", third, "error", False),
            }
        }
        self.published: dict[str, str] = {"web": first}

    def site(self, name: str) -> Json:
        published = self.deploys[name][self.published[name]]
        return {
            "id": name,
            "name": name,
            "url": f"https://{name}.netlify.app",
            "state": "current",
            "published_deploy": dict(published),
        }

    def summary(self) -> Json:
        return {
            "requests": self.requests,
            "restores": self.restores,
            "sites": {
                name: {"live": self.published[name], "versions": list(deploys)}
                for name, deploys in self.deploys.items()
            },
        }


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    site_path = re.compile(r"/api/v1/sites/([^/]+)")
    deploy_path = re.compile(r"/api/v1/sites/([^/]+)/deploys/([^/]+)(/restore)?")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write(f"fake-site-deploys {format % args}\n")

        def answer(self, status: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def error(self, code: int, message: str) -> None:
            self.answer(code, {"code": code, "message": message})

        def drain(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)

        def admitted(self) -> bool:
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            if given not in state.tokens:
                self.error(401, "Access Denied")
                return False
            return True

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.summary())
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                if m := deploy_path.fullmatch(url.path):
                    if m.group(3):
                        self.error(404, "Not Found")
                        return
                    found = state.deploys.get(m.group(1), {}).get(m.group(2))
                    if found is None:
                        self.error(404, "Not Found")
                    else:
                        self.answer(200, found)
                    return
                if m := site_path.fullmatch(url.path):
                    if m.group(1) not in state.deploys:
                        self.error(404, "Not Found")
                    else:
                        self.answer(200, state.site(m.group(1)))
                    return
                self.error(404, "Not Found")

        def do_POST(self) -> None:
            url = urlparse(self.path)
            self.drain()
            if url.path == "/_fake/reset":
                with state.lock:
                    state.reset()
                self.answer(200, {})
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                m = deploy_path.fullmatch(url.path)
                if m is None or not m.group(3):
                    self.error(404, "Not Found")
                    return
                site, identifier = m.group(1), m.group(2)
                found = state.deploys.get(site, {}).get(identifier)
                if found is None:
                    self.error(404, "Not Found")
                    return
                if found["state"] != "ready":
                    self.error(422, "Deploy is not ready")
                    return
                state.restores += 1
                state.published[site] = identifier
                found["published_at"] = "2026-11-07T12:00:00.000Z"
                self.answer(201, found)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9233)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake site deploys at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
