#!/usr/bin/env python3
"""A fake of the Cloud Run Admin API v2: the part the serverless connector uses, in memory.

The connector under `connectors/taktus_connectors/cloudrun/` asks, under
`/v2/projects/example/locations/europe-west1/services/`
(https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services):

- `GET <name>`: the service, 404 for one the location does not hold;
- `PATCH <name>` with a `Service` body: `annotations`, `template` and `traffic` taken from the
  body. A body whose `etag` is not the current one is 409 `ABORTED`, as Google's APIs refuse a
  stale write. A template that differs from the current one makes a new revision. The answer is
  a long-running `Operation`, not done;
- `GET <name>/revisions?pageSize=&pageToken=`: the revisions, oldest first, each with the
  annotations and containers of its template, `createTime` and a `Ready` condition; at most
  `pageSize` per page with `nextPageToken`.

And `POST /token`, the OAuth token endpoint (`google_oauth.py`): every other request needs a token
it issued. A rollout completes at once — the new revision ready, `latestReadyRevision` on it, not
reconciling — unless `POST /_fake/rollout` with `{"stalled": true}` holds it, as a revision that
never becomes ready: the old one keeps serving.

It holds the services `web` (container `app`, image `registry.example/app:1.0.0`, one revision
`web-00001-abc`) and `web-canary` (the same, `web-canary-00001-abc`). Test-only:
`GET /_fake/state` names, per service, the images of the revision serving all traffic, the
revisions oldest first and the one serving; `POST /_fake/reset` restores the start. Runnable as
`python3 tests/fakes/serverless_service.py --port 9231`.
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

PARENT = "projects/example/locations/europe-west1/services"
IMAGE = "registry.example/app:1.0.0"
LATEST = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
REVISION = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"


def _revision(service: str, number: int, template: Json, ready: bool, at: int) -> Json:
    name = f"{service}-{number:05d}-{'abc' if number == 1 else secrets.token_hex(2)[:3]}"
    return {
        "name": f"{PARENT}/{service}/revisions/{name}",
        "service": f"{PARENT}/{service}",
        "generation": "1",
        "createTime": f"2026-11-01T10:{at:02d}:00Z",
        "annotations": dict(template.get("annotations") or {}),
        "containers": copy.deepcopy(template.get("containers") or []),
        "reconciling": not ready,
        "conditions": [
            {"type": "Ready", "state": "CONDITION_SUCCEEDED" if ready else "CONDITION_PENDING"}
        ],
    }


class State:
    def __init__(self, keys: set[str]) -> None:
        self.tokens = Tokens(keys)
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.stalled = False
        self.requests = 0
        self.clock = 0
        self.services: dict[str, Json] = {}
        self.revisions: dict[str, list[Json]] = {}
        for name in ("web", "web-canary"):
            template = {"containers": [{"name": "app", "image": IMAGE}]}
            first = _revision(name, 1, template, True, self.tick())
            self.revisions[name] = [first]
            self.services[name] = {
                "name": f"{PARENT}/{name}",
                "uid": secrets.token_hex(8),
                "generation": "1",
                "observedGeneration": "1",
                "etag": secrets.token_hex(8),
                "annotations": {},
                "template": template,
                "traffic": [{"type": LATEST, "percent": 100}],
                "latestReadyRevision": first["name"],
                "latestCreatedRevision": first["name"],
                "reconciling": False,
                "terminalCondition": {"type": "Ready", "state": "CONDITION_SUCCEEDED"},
            }

    def tick(self) -> int:
        self.clock += 1
        return self.clock

    def patch(self, name: str, body: Json) -> Json:
        service = self.services[name]
        service["annotations"] = dict(body.get("annotations") or {})
        if isinstance(body.get("traffic"), list):
            service["traffic"] = copy.deepcopy(body["traffic"])
        template = body.get("template")
        generation = int(service["generation"]) + 1
        service["generation"] = str(generation)
        if isinstance(template, dict) and _template(template) != _template(service["template"]):
            service["template"] = copy.deepcopy(template)
            ready = not self.stalled
            made = _revision(name, len(self.revisions[name]) + 1, template, ready, self.tick())
            self.revisions[name].append(made)
            service["latestCreatedRevision"] = made["name"]
            if ready:
                service["latestReadyRevision"] = made["name"]
            service["reconciling"] = not ready
            service["terminalCondition"] = {
                "type": "Ready",
                "state": "CONDITION_SUCCEEDED" if ready else "CONDITION_RECONCILING",
            }
        service["observedGeneration"] = (
            service["generation"] if not self.stalled else str(generation - 1)
        )
        service["etag"] = secrets.token_hex(8)
        return {
            "name": f"projects/example/locations/europe-west1/operations/{secrets.token_hex(8)}",
            "metadata": {"@type": "type.googleapis.com/google.cloud.run.v2.Service"},
            "done": False,
        }

    def serving(self, name: str) -> str | None:
        service = self.services[name]
        traffic = [t for t in service["traffic"] if int(t.get("percent", 0)) > 0]
        if len(traffic) == 1 and traffic[0].get("type") == REVISION:
            return str(traffic[0]["revision"]).rsplit("/", 1)[-1]
        return str(service["latestReadyRevision"]).rsplit("/", 1)[-1]

    def snapshot(self) -> Json:
        found: Json = {}
        for name in self.services:
            serving = self.serving(name)
            revision = next(
                (r for r in self.revisions[name] if r["name"].endswith(f"/{serving}")), None
            )
            found[name] = {
                "images": [c["image"] for c in (revision or {}).get("containers", [])],
                "revisions": [r["name"].rsplit("/", 1)[-1] for r in self.revisions[name]],
                "serving": serving,
            }
        return {"services": found, "requests": self.requests, "grants": self.tokens.grants}


def _template(template: Json) -> Json:
    return {
        "annotations": dict(template.get("annotations") or {}),
        "containers": template.get("containers") or [],
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

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def admitted(self) -> bool:
            if state.tokens.admits(self.headers.get("Authorization")):
                return True
            self.answer(401, _error(401, "UNAUTHENTICATED", "Request had invalid credentials."))
            return False

        def service(self, path: str) -> tuple[str, str] | None:
            prefix = f"/v2/{PARENT}/"
            if not path.startswith(prefix):
                return None
            rest = path[len(prefix) :].split("/")
            if len(rest) == 1:
                return rest[0], ""
            if len(rest) == 2 and rest[1] == "revisions":
                return rest[0], "revisions"
            return None

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.snapshot())
                return
            if not self.admitted():
                return
            found = self.service(url.path)
            with state.lock:
                state.requests += 1
                if found is None or found[0] not in state.services:
                    self.answer(404, _error(404, "NOT_FOUND", "Resource not found."))
                    return
                name, part = found
                if part == "":
                    self.answer(200, state.services[name])
                    return
                query = parse_qs(url.query)
                size = int((query.get("pageSize") or ["100"])[0])
                start = int((query.get("pageToken") or ["0"])[0])
                items = state.revisions[name][start : start + size]
                page: Json = {"revisions": items}
                if start + size < len(state.revisions[name]):
                    page["nextPageToken"] = str(start + size)
                self.answer(200, page)

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
            found = self.service(url.path)
            with state.lock:
                state.requests += 1
                if found is None or found[1] or found[0] not in state.services:
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
                service = state.services[found[0]]
                given = body.get("etag")
                if given is not None and given != service["etag"]:
                    self.answer(409, _error(409, "ABORTED", "The etag does not match."))
                    return
                self.answer(200, state.patch(found[0], body))

    return Handler


def make_server(host: str, port: int, keys: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9231)
    args = parser.parse_args()
    server = make_server(args.host, args.port, keys_from(os.environ.get("FAKE_TOKENS", "")))
    sys.stderr.write(f"fake serverless service at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
