#!/usr/bin/env python3
"""A fake public package index: GetVersion of the deps.dev API v3, in memory.

The package licence connector under `connectors/taktus_connectors/depsdev/` asks
`GET /v3/systems/{system}/packages/{name}/versions/{version}`. This fake answers it in the shape
the API's documentation states (`https://docs.deps.dev/api/v3/`): `versionKey`, `publishedAt`,
`isDefault`, `isDeprecated`, `licenses` as SPDX expressions, `advisoryKeys`, `links`. It exists so
that the connector can be exercised without a network.

What it enforces, because the connector's checks depend on it:

- **The system.** One of `GO`, `RUBYGEMS`, `NPM`, `CARGO`, `MAVEN`, `PYPI`, `NUGET`, in either
  case; otherwise 400.
- **The encoding.** The name and the version are one path segment each, percent-encoded: a
  scoped npm name arrives as `%40scope%2Fname`.
- **An unknown version.** 404, with the gateway's error body `{code, message}`.

The versions: four npm packages and two PyPI packages, one of them under a copyleft licence and
one whose licence the index does not know, unless a test replaced them with
`POST /_fake/versions`, a JSON list of `{system, name, version, licenses}`. Test-only:
`GET /_fake/state` counts the requests. Standard library only; runnable as
`python3 tests/fakes/package_index_service.py --port 9271`.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

SYSTEMS = {"GO", "RUBYGEMS", "NPM", "CARGO", "MAVEN", "PYPI", "NUGET"}


def default_versions() -> list[dict[str, Any]]:
    return [
        {"system": "NPM", "name": "left-pad", "version": "1.3.0", "licenses": ["WTFPL"]},
        {"system": "NPM", "name": "react", "version": "18.3.1", "licenses": ["MIT"]},
        {"system": "NPM", "name": "@colors/colors", "version": "1.5.0", "licenses": ["MIT"]},
        {"system": "NPM", "name": "copyleft-lib", "version": "2.0.0", "licenses": ["GPL-3.0"]},
        {"system": "PYPI", "name": "httpx", "version": "0.28.1", "licenses": ["BSD-3-Clause"]},
        {"system": "PYPI", "name": "mystery", "version": "0.1.0", "licenses": []},
    ]


class State:
    def __init__(self) -> None:
        self.versions = default_versions()
        self.requests = 0
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

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/_fake/versions":
                self.answer(404, {"code": 5, "message": "not found"})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.versions = json.loads(body)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            raw = urlparse(self.path).path
            if raw == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests})
                return
            with state.lock:
                state.requests += 1
            parts = raw.split("/")
            # ['', 'v3', 'systems', S, 'packages', N, 'versions', V]
            if len(parts) != 8 or parts[1:3] != ["v3", "systems"] or parts[4] != "packages":
                self.answer(404, {"code": 5, "message": "not found"})
                return
            if parts[6] != "versions":
                self.answer(404, {"code": 5, "message": "not found"})
                return
            system, name, version = parts[3].upper(), unquote(parts[5]), unquote(parts[7])
            if system not in SYSTEMS:
                self.answer(400, {"code": 3, "message": "invalid system"})
                return
            with state.lock:
                found = [
                    v
                    for v in state.versions
                    if (v["system"], v["name"], v["version"]) == (system, name, version)
                ]
            if not found:
                self.answer(404, {"code": 5, "message": "version not found"})
                return
            self.answer(
                200,
                {
                    "versionKey": {"system": system, "name": name, "version": version},
                    "publishedAt": "2024-04-26T16:42:27Z",
                    "isDefault": True,
                    "isDeprecated": False,
                    "licenses": found[0]["licenses"],
                    "advisoryKeys": [],
                    "links": [],
                    "slsaProvenances": [],
                    "registries": [],
                    "relatedProjects": [],
                },
            )

    return Handler


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State()))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9271)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    sys.stderr.write(f"fake package index at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
