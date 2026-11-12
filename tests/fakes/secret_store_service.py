#!/usr/bin/env python3
"""A fake secret store: the metadata endpoints of HashiCorp Vault's KV version 2, in memory.

The secret store connector under `connectors/taktus_connectors/vault/` lists
`/v1/<mount>/metadata/<folder>` (the verb `LIST`, or `GET` with `list=true`; the API documents
both) and reads `GET /v1/<mount>/metadata/<name>`. This fake answers both in the API's shapes
and statuses. It exists so that the connector can be exercised in CI without a network, a
store or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `X-Vault-Token` with a value the fake was started
  with (`FAKE_TOKENS`, comma separated). Otherwise 403 `{"errors": ["permission denied"]}`,
  as the API answers a token it does not admit.
- **The mount.** Only `secret` exists; another is 404 with a message, as an unknown route is.
- **Empty lists.** A folder without keys is 404 `{"errors": []}`, as the API documents.
- **Metadata.** A secret's metadata has `created_time`, `updated_time`, `current_version`,
  `versions` (each with `created_time`, `deletion_time`, `destroyed` and a `created_by` that
  names a writer, which the connector must never copy), `custom_metadata`,
  `delete_version_after`, `max_versions`, `oldest_version` and `cas_required`.

It also holds each secret's value and answers `GET /v1/<mount>/data/<name>` as the API does,
so that a connector that asked for a value would get one: `GET /_fake/state` counts those
requests as `value_reads`, which must stay 0. It also counts every request and names the
namespaces seen.

The secrets, each version a number of days before the fake started: `app/db` (versions 400,
200 and 90 days old), `app/api-key` (30), `ci/deploy/token` (700 and 365) and `root-key` (10).
Standard library only; runnable as `python3 tests/fakes/secret_store_service.py --port 9224`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

MOUNT = "secret"
AGES: dict[str, list[int]] = {
    "app/db": [400, 200, 90],
    "app/api-key": [30],
    "ci/deploy/token": [700, 365],
    "root-key": [10],
}
"""Each secret's versions, as days before the fake started, oldest first."""


def _stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


def secrets(now: datetime) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, ages in AGES.items():
        versions = {
            str(n + 1): {
                "created_time": _stamp(now - timedelta(days=age)),
                "created_by": {
                    "actor": "userpass-a.person",
                    "operation": "create" if n == 0 else "update",
                    "entity_id": "00000000-0000-0000-0000-000000000001",
                    "client_id": "00000000-0000-0000-0000-000000000001",
                },
                "deletion_time": "",
                "destroyed": False,
            }
            for n, age in enumerate(ages)
        }
        newest = versions[str(len(ages))]["created_time"]
        out[name] = {
            "metadata": {
                "cas_required": False,
                "created_time": versions["1"]["created_time"],
                "current_version": len(ages),
                "delete_version_after": "0s",
                "max_versions": 0,
                "oldest_version": 0,
                "updated_time": newest,
                "custom_metadata": None,
                "versions": versions,
            },
            "value": {"password": f"value-of-{name}"},
        }
    return out


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.secrets = secrets(datetime.now(UTC))
        self.requests = 0
        self.value_reads = 0
        self.namespaces: list[str] = []
        self.lock = threading.Lock()


def keys(names: list[str], folder: str) -> list[str]:
    """The keys directly in a folder: a name, or the next folder ending in `/`."""
    found: set[str] = set()
    for name in names:
        if not name.startswith(folder):
            continue
        rest = name[len(folder) :]
        head, slash, _ = rest.partition("/")
        found.add(head + slash)
    return sorted(found)


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

        def do_LIST(self) -> None:
            self._serve(listing=True)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {
                        "requests": state.requests,
                        "value_reads": state.value_reads,
                        "namespaces": list(state.namespaces),
                    }
                self.answer(200, body)
                return
            listing = parse_qs(url.query).get("list", [""])[0] == "true"
            self._serve(listing=listing)

        def _serve(self, listing: bool) -> None:
            url = urlparse(self.path)
            with state.lock:
                state.requests += 1
                namespace = self.headers.get("X-Vault-Namespace")
                if namespace:
                    state.namespaces.append(namespace)
            if self.headers.get("X-Vault-Token") not in state.tokens:
                self.answer(403, {"errors": ["permission denied"]})
                return
            parts = url.path.removeprefix("/v1/").split("/", 2)
            if len(parts) < 2 or parts[0] != MOUNT or parts[1] not in {"metadata", "data"}:
                self.answer(404, {"errors": [f"no handler for route {url.path!r}"]})
                return
            rest = parts[2] if len(parts) == 3 else ""
            if parts[1] == "data":
                with state.lock:
                    state.value_reads += 1
                held = state.secrets.get(rest)
                if held is None or listing:
                    self.answer(404, {"errors": []})
                    return
                self.answer(200, {"data": {"data": held["value"], "metadata": {}}})
                return
            if listing:
                folder = rest if not rest or rest.endswith("/") else rest + "/"
                found = keys(list(state.secrets), folder)
                if not found:
                    self.answer(404, {"errors": []})
                    return
                self.answer(200, {"data": {"keys": found}})
                return
            held = state.secrets.get(rest)
            if held is None:
                self.answer(404, {"errors": []})
                return
            self.answer(200, {"data": held["metadata"]})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9224)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake secret store at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
