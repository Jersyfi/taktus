#!/usr/bin/env python3
"""A fake of the Firebase Hosting REST API v1beta1: the part the site connector uses, in memory.

The connector under `connectors/taktus_connectors/firebase/` asks, under `/v1beta1/sites/<site>/`
(https://firebase.google.com/docs/reference/hosting/rest/v1beta1/sites.releases,
`sites.versions`, `sites.channels`):

- `GET channels/live`: the live channel with its current `release`;
- `GET versions/<id>`: a version with its `status`, 404 for one the site does not hold;
- `GET releases?pageSize=&pageToken=`: the releases, newest first, at most `pageSize` per page
  with `nextPageToken`;
- `POST releases?versionName=sites/<site>/versions/<id>` with a `Release` body: a release of the
  version, its `message` kept. A `versionName` of another site, or none, is 400; an unknown
  version 404; a version not `FINALIZED` 400 `FAILED_PRECONDITION`. The release becomes the live
  channel's current one; its `type` is `DEPLOY`, or `ROLLBACK` for a version released before.

And `POST /token`, the OAuth token endpoint (`google_oauth.py`): every other request needs a token
it issued. The site `web` holds three versions, oldest first: `0f1e2d3c4b5a6978` (finalized and
live), `a1b2c3d4e5f60718` (finalized, never released) and `3c3c3c3c3c3c3c3c` (created, not
finalized). Test-only: `GET /_fake/state` names, per site, the live version, the versions oldest
first and how many releases it has; `POST /_fake/reset` restores the start. Runnable as
`python3 tests/fakes/hosting_releases_service.py --port 9232`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from fakes.google_oauth import Tokens, keys_from
except ImportError:  # run as a script from its own directory
    from google_oauth import Tokens, keys_from  # type: ignore[import-not-found,no-redef]

type Json = dict[str, Any]

LIVE, NEXT, UNFINISHED = "0f1e2d3c4b5a6978", "a1b2c3d4e5f60718", "3c3c3c3c3c3c3c3c"


class State:
    def __init__(self, keys: set[str]) -> None:
        self.tokens = Tokens(keys)
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.clock = 0
        self.versions: dict[str, list[Json]] = {
            "web": [
                self.version("web", LIVE, "FINALIZED"),
                self.version("web", NEXT, "FINALIZED"),
                self.version("web", UNFINISHED, "CREATED"),
            ]
        }
        self.releases: dict[str, list[Json]] = {"web": []}
        self.release("web", LIVE, "first deploy")

    def moment(self) -> str:
        self.clock += 1
        return f"2026-11-01T10:{self.clock // 60:02d}:{self.clock % 60:02d}Z"

    def version(self, site: str, id: str, status: str) -> Json:
        return {
            "name": f"sites/{site}/versions/{id}",
            "status": status,
            "createTime": self.moment(),
        }

    def release(self, site: str, id: str, message: str) -> Json:
        version = next(v for v in self.versions[site] if v["name"].endswith(f"/{id}"))
        before = any(r["version"]["name"] == version["name"] for r in self.releases[site])
        made = {
            "name": f"sites/{site}/releases/{secrets.token_hex(8)}",
            "version": dict(version),
            "type": "ROLLBACK" if before else "DEPLOY",
            "releaseTime": self.moment(),
            "releaseUser": {"email": "release@example.iam.gserviceaccount.com"},
            "message": message,
        }
        self.releases[site].insert(0, made)  # newest first
        return made

    def snapshot(self) -> Json:
        return {
            "sites": {
                site: {
                    "live": self.releases[site][0]["version"]["name"].rsplit("/", 1)[-1]
                    if self.releases[site]
                    else None,
                    "versions": [v["name"].rsplit("/", 1)[-1] for v in self.versions[site]],
                    "releases": len(self.releases[site]),
                }
                for site in self.versions
            },
            "requests": self.requests,
            "grants": self.tokens.grants,
        }


def _error(status: int, word: str, message: str) -> Json:
    return {"error": {"code": status, "message": message, "status": word}}


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def missing(self) -> None:
            self.answer(404, _error(404, "NOT_FOUND", "Requested entity was not found."))

        def admitted(self) -> bool:
            if state.tokens.admits(self.headers.get("Authorization")):
                return True
            self.answer(401, _error(401, "UNAUTHENTICATED", "Request had invalid credentials."))
            return False

        def parts(self, path: str) -> list[str] | None:
            prefix = "/v1beta1/sites/"
            if not path.startswith(prefix):
                return None
            parts = path[len(prefix) :].split("/")
            return parts if parts and parts[0] in state.versions else None

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.snapshot())
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                parts = self.parts(url.path)
                if parts is None:
                    self.missing()
                    return
                site = parts[0]
                if parts[1:] == ["channels", "live"]:
                    current = state.releases[site][0] if state.releases[site] else None
                    channel: Json = {
                        "name": f"sites/{site}/channels/live",
                        "url": f"https://{site}.web.app",
                        "retainedReleaseCount": 10,
                    }
                    if current is not None:
                        channel["release"] = current
                    self.answer(200, channel)
                    return
                if len(parts) == 3 and parts[1] == "versions":
                    found = next(
                        (v for v in state.versions[site] if v["name"].endswith(f"/{parts[2]}")),
                        None,
                    )
                    if found is None:
                        self.missing()
                    else:
                        self.answer(200, found)
                    return
                if parts[1:] == ["releases"]:
                    query = parse_qs(url.query)
                    size = int((query.get("pageSize") or ["100"])[0])
                    start = int((query.get("pageToken") or ["0"])[0])
                    items = state.releases[site][start : start + size]
                    page: Json = {"releases": items}
                    if start + size < len(state.releases[site]):
                        page["nextPageToken"] = str(start + size)
                    self.answer(200, page)
                    return
                self.missing()

        def do_POST(self) -> None:
            url = urlparse(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if url.path == "/token":
                status, granted = state.tokens.grant(raw)
                self.answer(status, granted)
                return
            if url.path == "/_fake/reset":
                with state.lock:
                    state.reset()
                self.answer(200, {})
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                parts = self.parts(url.path)
                if parts is None or parts[1:] != ["releases"]:
                    self.missing()
                    return
                site = parts[0]
                name = (parse_qs(url.query).get("versionName") or [""])[0]
                if not name.startswith(f"sites/{site}/versions/"):
                    self.answer(400, _error(400, "INVALID_ARGUMENT", "Invalid versionName."))
                    return
                id = name.rsplit("/", 1)[-1]
                version = next((v for v in state.versions[site] if v["name"] == name), None)
                if version is None:
                    self.missing()
                    return
                if version["status"] != "FINALIZED":
                    self.answer(
                        400, _error(400, "FAILED_PRECONDITION", "Version is not finalized.")
                    )
                    return
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    self.answer(400, _error(400, "INVALID_ARGUMENT", "Invalid JSON payload."))
                    return
                message = str(body.get("message", "")) if isinstance(body, dict) else ""
                if len(message) > 512:
                    self.answer(400, _error(400, "INVALID_ARGUMENT", "Message is too long."))
                    return
                self.answer(200, state.release(site, id, message))

    return Handler


def make_server(host: str, port: int, keys: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9232)
    args = parser.parse_args()
    server = make_server(args.host, args.port, keys_from(os.environ.get("FAKE_TOKENS", "")))
    sys.stderr.write(f"fake hosting releases at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
