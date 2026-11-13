#!/usr/bin/env python3
"""A fake evaluation platform: the part of Langfuse's public HTTP API the evaluation platform
connector calls, in memory (DEC-0226: a stand-in built from the product's published API).

The connector under `connectors/taktus_connectors/langfuse/` asks, under `/api/public/`:
`POST /datasets`, `POST /dataset-items`, `POST /dataset-run-items`, `GET`/`POST /scores`,
`GET /datasets/{dataset}/runs/{run}`, `GET /traces/{trace}`, `GET`/`POST /v2/prompts` and
`GET /v2/prompts/{name}?version=`. This fake answers them in the shapes and statuses the API
reference states. It exists so that the connector can be exercised in CI without a network, an
account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP basic, the pair `<public key>:<secret key>` one of those the fake was
  started with (`FAKE_TOKENS`, comma separated). None or another: 401.
- **Identifiers are kept as given.** A data set is one per name, created or kept by `POST
  /datasets`; an item and a score are kept under the `id` given, a second `POST` with the same
  `id` replacing it — the upsert the API states. An item names a data set that exists, and a
  run item an item that exists; otherwise 404.
- **Traces come from elsewhere.** A trace is what the platform received over OpenTelemetry; the
  fake holds `trace-seeded` (cost 0.0123 US dollars, 1.5 seconds) and whatever `POST
  /_fake/traces` adds. A trace's detail carries `totalCost`, `latency` and the scores on it. An
  unknown trace is 404; a score may name one, as the API accepts it.
- **A prompt's versions count from 1.** `POST /v2/prompts` makes the next version of the name,
  with its `config` kept as given; the listing names every version of it.

Test-only endpoints under `/_fake/`: `GET /_fake/state` counts the requests and every record,
and names the pairs seen; `GET /_fake/items` lists every item of every data set as it is held;
`POST /_fake/traces` with `{"id", "totalCost", "latency"}` adds a trace; `POST /_fake/reset`
empties the store back to its seed. Standard library only; runnable as
`python3 tests/fakes/evaluation_platform_service.py --port 9275`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

type Json = dict[str, Any]

SEEDED = {"id": "trace-seeded", "totalCost": 0.0123, "latency": 1.5}
RUN = re.compile(r"^/api/public/datasets/([^/]+)/runs/([^/]+)$")
TRACE = re.compile(r"^/api/public/traces/([^/]+)$")
SCORE = re.compile(r"^/api/public/scores/([^/]+)$")
PROMPT = re.compile(r"^/api/public/v2/prompts/([^/]+)$")


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.seen: set[str] = set()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.datasets: dict[str, Json] = {}
        self.items: dict[str, Json] = {}
        self.runs: dict[tuple[str, str], Json] = {}
        self.scores: dict[str, Json] = {}
        self.traces: dict[str, Json] = {SEEDED["id"]: dict(SEEDED)}
        self.prompts: dict[str, list[Json]] = {}

    def state(self) -> Json:
        return {
            "requests": self.requests,
            "datasets": len(self.datasets),
            "items": len(self.items),
            "run_items": sum(len(r["datasetRunItems"]) for r in self.runs.values()),
            "scores": len(self.scores),
            "prompts": {name: len(v) for name, v in self.prompts.items()},
            "seen_tokens": sorted(self.seen),
        }


class Handler(BaseHTTPRequestHandler):
    store: Store

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"fake-evaluation-platform {format % args}\n")

    def _send(self, status: int, body: Any) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _fault(self, status: int, message: str) -> None:
        self._send(status, {"message": message, "error": message})

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return {"__invalid__": True}
        return body if isinstance(body, dict) else {"__invalid__": True}

    def _admitted(self) -> bool:
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            pair = base64.b64decode(header[len("Basic ") :]).decode("utf-8")
        except ValueError:
            return False
        self.store.seen.add(pair)
        return pair in self.store.tokens

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/_fake/state":
            with self.store.lock:
                self._send(200, self.store.state())
            return
        if url.path == "/_fake/items":
            with self.store.lock:
                self._send(200, {"items": list(self.store.items.values())})
            return
        self._api("GET", url.path, parse_qs(url.query), {})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        body = self._body()
        if url.path.startswith("/_fake/"):
            with self.store.lock:
                if url.path == "/_fake/reset":
                    self.store.reset()
                elif url.path == "/_fake/traces":
                    self.store.traces[str(body["id"])] = {
                        "id": str(body["id"]),
                        "totalCost": body.get("totalCost"),
                        "latency": body.get("latency"),
                    }
                else:
                    self._fault(404, "unknown")
                    return
            self._send(200, {"ok": True})
            return
        self._api("POST", url.path, parse_qs(url.query), body)

    def _api(self, verb: str, path: str, query: dict[str, list[str]], body: Json) -> None:
        store = self.store
        with store.lock:
            store.requests += 1
            if not path.startswith("/api/public/"):
                self._fault(404, "not found")
                return
            if not self._admitted():
                self._fault(401, "Invalid credentials")
                return
            if body.get("__invalid__"):
                self._fault(400, "Invalid request data")
                return
            status, answer = self._route(verb, path, query, body)
            self._send(status, answer)

    def _route(
        self, verb: str, path: str, query: dict[str, list[str]], body: Json
    ) -> tuple[int, Any]:
        store = self.store
        if verb == "POST" and path == "/api/public/datasets":
            name = body.get("name")
            if not isinstance(name, str) or not name:
                return 400, {"message": "name is required"}
            dataset = store.datasets.setdefault(
                name, {"id": uuid.uuid4().hex, "name": name, "createdAt": now()}
            )
            if isinstance(body.get("description"), str):
                dataset["description"] = body["description"]
            return 200, dataset
        if verb == "POST" and path == "/api/public/dataset-items":
            name = body.get("datasetName")
            if not isinstance(name, str) or name not in store.datasets:
                return 404, {"message": "Dataset not found"}
            ident = body.get("id") if isinstance(body.get("id"), str) else uuid.uuid4().hex
            item = {
                "id": ident,
                "datasetId": store.datasets[name]["id"],
                "datasetName": name,
                "input": body.get("input"),
                "expectedOutput": body.get("expectedOutput"),
                "metadata": body.get("metadata"),
                "status": "ACTIVE",
            }
            store.items[ident] = item
            return 200, item
        if verb == "POST" and path == "/api/public/dataset-run-items":
            item = store.items.get(str(body.get("datasetItemId")))
            run_name = body.get("runName")
            trace = body.get("traceId")
            if item is None:
                return 404, {"message": "Dataset item not found"}
            if not isinstance(run_name, str) or not isinstance(trace, str):
                return 400, {"message": "runName and traceId are required"}
            run = store.runs.setdefault(
                (item["datasetName"], run_name),
                {
                    "id": uuid.uuid4().hex,
                    "name": run_name,
                    "datasetName": item["datasetName"],
                    "datasetRunItems": [],
                },
            )
            entry = {
                "id": uuid.uuid4().hex,
                "datasetRunId": run["id"],
                "datasetRunName": run_name,
                "datasetItemId": item["id"],
                "traceId": trace,
                "observationId": None,
            }
            run["datasetRunItems"].append(entry)
            return 200, entry
        if verb == "POST" and path == "/api/public/scores":
            value = body.get("value")
            if (
                not isinstance(body.get("traceId"), str)
                or not isinstance(body.get("name"), str)
                or isinstance(value, bool)
                or not isinstance(value, int | float)
            ):
                return 400, {"message": "traceId, name and a numeric value are required"}
            ident = body.get("id") if isinstance(body.get("id"), str) else uuid.uuid4().hex
            store.scores[ident] = {
                "id": ident,
                "traceId": body["traceId"],
                "name": body["name"],
                "value": value,
                "dataType": body.get("dataType", "NUMERIC"),
                "comment": body.get("comment"),
                "source": "API",
            }
            return 200, {"id": ident}
        if verb == "GET" and (found := SCORE.match(path)):
            score = store.scores.get(unquote(found.group(1)))
            return (200, score) if score else (404, {"message": "Score not found"})
        if verb == "GET" and (found := RUN.match(path)):
            run = store.runs.get((unquote(found.group(1)), unquote(found.group(2))))
            return (200, run) if run else (404, {"message": "Dataset run not found"})
        if verb == "GET" and (found := TRACE.match(path)):
            trace = store.traces.get(unquote(found.group(1)))
            if trace is None:
                return 404, {"message": "Trace not found"}
            scores = [s for s in store.scores.values() if s["traceId"] == trace["id"]]
            return 200, {**trace, "scores": scores, "observations": []}
        if path == "/api/public/v2/prompts":
            if verb == "GET":
                name = (query.get("name") or [""])[0]
                held = {n: v for n, v in store.prompts.items() if not name or n == name}
                data = [
                    {
                        "name": n,
                        "versions": [p["version"] for p in v],
                        "labels": [],
                        "tags": [],
                        "lastUpdatedAt": v[-1]["updatedAt"],
                    }
                    for n, v in held.items()
                ]
                meta = {"page": 1, "limit": 50, "totalItems": len(data), "totalPages": 1}
                return 200, {"data": data, "meta": meta}
            name, text = body.get("name"), body.get("prompt")
            if body.get("type", "text") != "text" or not isinstance(name, str) or not text:
                return 400, {"message": "a text prompt needs a name and a prompt"}
            versions = store.prompts.setdefault(name, [])
            made = {
                "name": name,
                "type": "text",
                "prompt": text,
                "version": len(versions) + 1,
                "config": body.get("config") or {},
                "labels": body.get("labels") or [],
                "tags": [],
                "commitMessage": body.get("commitMessage"),
                "updatedAt": now(),
            }
            versions.append(made)
            return 200, made
        if verb == "GET" and (found := PROMPT.match(path)):
            versions = store.prompts.get(unquote(found.group(1)), [])
            wanted = (query.get("version") or [""])[0]
            chosen = (
                versions[-1:]
                if not wanted
                else [p for p in versions if str(p["version"]) == wanted]
            )
            return (200, chosen[0]) if chosen else (404, {"message": "Prompt not found"})
        return 404, {"message": "not found"}


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    class Bound(Handler):
        pass

    Bound.store = Store(tokens)
    return ThreadingHTTPServer((host, port), Bound)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9275)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake evaluation platform at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
