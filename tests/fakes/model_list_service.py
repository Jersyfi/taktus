#!/usr/bin/env python3
"""A fake model provider's models list: the `GET /v1/models` of the Mistral AI API, in memory.

The model catalogue connector under `connectors/taktus_connectors/mistral/` asks it. This fake
answers in the API's shape, with the API's statuses, over models it holds in memory, so that
the connector can be exercised in CI without a network, an account or a secret. The provider
publishes no API for an organisation's costs, and this fake serves none.

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the
  fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The answer.** `{"object": "list", "data": [...]}` without pages, each model as the API
  documents a model card: `id`, `object`, `created` in Unix seconds, `owned_by`,
  `capabilities`, `name`, `description`, `max_context_length`, `aliases`, `deprecation` (a
  moment, or null), `deprecation_replacement_model`, `default_model_temperature` and `type`.

The models: `mistral-large-latest`, `mistral-small-latest` and, under an example identifier,
one with a deprecation set, unless a test replaced the list with `POST /_fake/models`, a JSON
list of model objects as the API gives them. Test-only: `GET /_fake/state` counts the requests
and names the bearer tokens seen. Standard library only; runnable as
`python3 tests/fakes/model_list_service.py --port 9213`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def _card(identifier: str, created: int, deprecation: str | None = None) -> dict[str, Any]:
    return {
        "id": identifier,
        "object": "model",
        "created": created,
        "owned_by": "mistralai",
        "capabilities": {"completion_chat": True, "function_calling": True},
        "name": identifier.removesuffix("-latest"),
        "description": "An example model.",
        "max_context_length": 131072,
        "aliases": [],
        "deprecation": deprecation,
        "deprecation_replacement_model": "mistral-small-latest" if deprecation else None,
        "default_model_temperature": 0.3,
        "type": "base",
    }


MODELS: list[dict[str, Any]] = [
    _card("mistral-small-latest", 1726704000),
    _card("mistral-large-latest", 1731024000),
    _card("example-deprecated", 1696118400, "2026-11-30T12:00:00Z"),
]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.models: list[dict[str, Any]] = [dict(m) for m in MODELS]
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
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            if self.path != "/_fake/models":
                self.answer(404, {"detail": "Not Found"})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                state.models = list(json.loads(body))
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests, "seen_tokens": state.seen_tokens})
                return
            if url.path != "/v1/models":
                self.answer(404, {"detail": "Not Found"})
                return
            given = self.headers.get("Authorization") or ""
            token = given.removeprefix("Bearer ") if given.startswith("Bearer ") else ""
            with state.lock:
                state.requests += 1
                if token:
                    state.seen_tokens.append(token)
            if token not in state.tokens:
                self.answer(401, {"message": "Unauthorized", "request_id": "req_fake"})
                return
            with state.lock:
                self.answer(200, {"object": "list", "data": list(state.models)})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9213)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake model list at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
