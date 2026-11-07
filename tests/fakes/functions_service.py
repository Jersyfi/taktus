#!/usr/bin/env python3
"""A fake of the Cloud Functions API v2: the part the functions connector uses, in memory.

The connector under `connectors/taktus_connectors/cloudfunctions/` asks, under
`/v2/projects/example/locations/europe-west1/functions/`
(https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions):

- `GET <function>` (`functions.get`): the `Function`, 404 for one the location does not hold;
- `PATCH <function>?updateMask=` (`functions.patch`) with a `Function` body: the fields the
  mask names — `buildConfig.source` and `labels` here; the API updates every field where no mask
  is given — taken from the body. The answer is a long-running `Operation`
  (`projects/example/locations/europe-west1/operations/<id>`, `done: false`). A mask naming
  another field is 400 `INVALID_ARGUMENT`: the fake holds no other. The reference pages do not
  state how a patch over a deployment in progress is answered, so the fake does not answer it
  differently; the connector reads the state first and does not send one.

And `POST /token`, the OAuth token endpoint (`google_oauth.py`): every other request needs a token
it issued. Errors are Google's body, `{"error": {"code", "message", "status"}}`.

**A deployment.** A patch puts the function in state `DEPLOYING`, its `buildConfig.source` the
archive given. The next reading completes it: the state `ACTIVE`, `sourceProvenance` the archive
built, and `serviceConfig.revision` a new revision. `POST /_fake/rollout` with
`{"stalled": true}` holds it in `DEPLOYING`, as a build that does not finish.

It holds the function `web`, built from `example-sources/web/1.0.0.tar.gz` generation
`1730000000000001`; the bucket also holds `web/1.1.0.tar.gz` generation `1730000000000002`.
Test-only: `GET /_fake/state` names, per function, its state, the archive it serves, its labels
and the archives deployed in order; `POST /_fake/reset` restores the start. Runnable as
`python3 tests/fakes/functions_service.py --port 9284`.
"""

from __future__ import annotations

import argparse
import copy
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

LOCATION = "projects/example/locations/europe-west1"
PARENT = f"{LOCATION}/functions"
BUCKET = "example-sources"
FIRST = {"bucket": BUCKET, "object": "web/1.0.0.tar.gz", "generation": "1730000000000001"}
FIELDS = {"buildConfig.source", "labels"}


def _version(source: Json) -> str:
    return f"{source['bucket']}/{source['object']}#{source['generation']}"


class State:
    def __init__(self, keys: set[str]) -> None:
        self.tokens = Tokens(keys)
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.stalled = False
        self.requests = 0
        self.deployed: dict[str, list[str]] = {"web": []}
        self.functions: dict[str, Json] = {
            "web": {
                "name": f"{PARENT}/web",
                "buildConfig": {
                    "build": f"{LOCATION}/builds/{secrets.token_hex(8)}",
                    "runtime": "python312",
                    "entryPoint": "main",
                    "source": {"storageSource": dict(FIRST)},
                    "sourceProvenance": {"resolvedStorageSource": dict(FIRST)},
                },
                "serviceConfig": {
                    "service": "projects/example/locations/europe-west1/services/web",
                    "revision": "web-00001-abc",
                    "uri": "https://web-example.a.run.app",
                    "allTrafficOnLatestRevision": True,
                },
                "state": "ACTIVE",
                "updateTime": "2026-11-01T10:00:00Z",
                "labels": {},
                "environment": "GEN_2",
                "url": "https://europe-west1-example.cloudfunctions.net/web",
            }
        }

    def patch(self, name: str, body: Json, mask: set[str]) -> Json:
        function = self.functions[name]
        if "buildConfig.source" in mask:
            function["buildConfig"]["source"] = copy.deepcopy(
                (body.get("buildConfig") or {}).get("source") or {}
            )
        if "labels" in mask:
            function["labels"] = dict(body.get("labels") or {})
        function["state"] = "DEPLOYING"
        return {
            "name": f"{LOCATION}/operations/operation-{secrets.token_hex(8)}",
            "metadata": {
                "@type": "type.googleapis.com/google.cloud.functions.v2.OperationMetadata",
                "target": function["name"],
                "verb": "update",
            },
            "done": False,
        }

    def settle(self, name: str) -> None:
        """A deployment in progress completes at the reading, unless the rollout is stalled."""
        function = self.functions[name]
        if function["state"] != "DEPLOYING" or self.stalled:
            return
        source = (function["buildConfig"].get("source") or {}).get("storageSource") or {}
        function["buildConfig"]["sourceProvenance"] = {"resolvedStorageSource": dict(source)}
        number = len(self.deployed[name]) + 2
        function["serviceConfig"]["revision"] = f"{name}-{number:05d}-{secrets.token_hex(2)[:3]}"
        function["state"] = "ACTIVE"
        self.deployed[name].append(_version(source))

    def snapshot(self) -> Json:
        found: Json = {}
        for name, function in self.functions.items():
            served = function["buildConfig"]["sourceProvenance"]["resolvedStorageSource"]
            found[name] = {
                "state": function["state"],
                "serving": _version(served),
                "labels": dict(function["labels"]),
                "deployed": list(self.deployed[name]),
            }
        return {"functions": found, "requests": self.requests, "grants": self.tokens.grants}


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

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def admitted(self) -> bool:
            if state.tokens.admits(self.headers.get("Authorization")):
                return True
            self.answer(401, _error(401, "UNAUTHENTICATED", "Request had invalid credentials."))
            return False

        def function(self, path: str) -> str | None:
            prefix = f"/v2/{PARENT}/"
            if not path.startswith(prefix):
                return None
            rest = path[len(prefix) :]
            return rest if rest and "/" not in rest else None

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.snapshot())
                return
            if not self.admitted():
                return
            name = self.function(url.path)
            with state.lock:
                state.requests += 1
                if name is None or name not in state.functions:
                    self.answer(404, _error(404, "NOT_FOUND", "Resource not found."))
                    return
                state.settle(name)
                self.answer(200, state.functions[name])

        def do_POST(self) -> None:
            url = urlparse(self.path)
            raw = self.body()
            if url.path == "/token":
                status, granted = state.tokens.grant(raw)
                self.answer(status, granted)
                return
            with state.lock:
                if url.path == "/_fake/reset":
                    state.reset()
                    self.answer(200, {})
                    return
                if url.path == "/_fake/rollout":
                    state.stalled = bool(json.loads(raw or b"{}").get("stalled"))
                    self.answer(200, {})
                    return
            self.answer(404, _error(404, "NOT_FOUND", "Resource not found."))

        def do_PATCH(self) -> None:
            url = urlparse(self.path)
            raw = self.body()
            if not self.admitted():
                return
            name = self.function(url.path)
            with state.lock:
                state.requests += 1
                if name is None or name not in state.functions:
                    self.answer(404, _error(404, "NOT_FOUND", "Resource not found."))
                    return
                try:
                    body = json.loads(raw)
                except ValueError:
                    self.answer(400, _error(400, "INVALID_ARGUMENT", "Invalid JSON payload."))
                    return
                if not isinstance(body, dict):
                    self.answer(400, _error(400, "INVALID_ARGUMENT", "Invalid JSON payload."))
                    return
                given = (parse_qs(url.query).get("updateMask") or [""])[0]
                mask = {f for f in given.split(",") if f} if given else set(FIELDS)
                if not mask <= FIELDS:
                    self.answer(
                        400, _error(400, "INVALID_ARGUMENT", f"Invalid field mask: {given}")
                    )
                    return
                self.answer(200, state.patch(name, body, mask))

    return Handler


def make_server(host: str, port: int, keys: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9284)
    args = parser.parse_args()
    server = make_server(args.host, args.port, keys_from(os.environ.get("FAKE_TOKENS", "")))
    sys.stderr.write(f"fake functions service at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
