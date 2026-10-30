#!/usr/bin/env python3
"""A fake model provider's costs API: the organisation costs of the OpenAI API, in memory.

The model costs connector under `connectors/taktus_connectors/openai/` asks
`GET /v1/organization/costs`. This fake answers it in the API's shapes, with the API's
statuses, over costs it holds in memory. It exists so that the connector can be exercised in
CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the
  fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The request.** `start_time` and `end_time` are whole seconds with the start before the
  end, `bucket_width` is `1d`, `group_by` is `line_item` or `project_id`, and `limit` is from
  1 to 180. A start before 2020-01-01 is refused as the API refuses a period it holds no data
  for. Anything else is 400 with an `invalid_request_error`.
- **Pages.** At most `FAKE_PAGE_DAYS` buckets (default 10) per answer, with `has_more` and a
  `next_page` that `page` carries back.

The costs: every day two line items, `Completions` 0.06 and `Embeddings` 0.0012, in `usd`,
under the project `proj_example`, unless a test set other amounts for a day with
`POST /_fake/costs`, a JSON object `{date: {line_item: amount}}`. Test-only: `GET /_fake/state`
counts the requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/model_costs_service.py --port 9211`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

DEFAULT = {"Completions": "0.06", "Embeddings": "0.0012"}
PROJECT = "proj_example"
EARLIEST = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp())


class State:
    def __init__(self, tokens: set[str], page_days: int) -> None:
        self.tokens = tokens
        self.page_days = page_days
        self.costs: dict[str, dict[str, str]] = {}
        self.requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            # An amount marked `@@<text>@@` is written as a JSON number, digit for digit.
            data = json.dumps(body).replace('"@@', "").replace('@@"', "").encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, status: int, kind: str, message: str) -> None:
            self.answer(status, {"error": {"message": message, "type": kind}})

        def do_POST(self) -> None:
            if self.path != "/_fake/costs":
                self.refuse(404, "invalid_request_error", "not found")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                for day, items in json.loads(body).items():
                    state.costs[day] = dict(items)
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests, "seen_tokens": state.seen_tokens})
                return
            if url.path != "/v1/organization/costs":
                self.refuse(404, "invalid_request_error", "not found")
                return
            with state.lock:
                state.requests += 1
            given = self.headers.get("Authorization") or ""
            token = given.removeprefix("Bearer ") if given.startswith("Bearer ") else ""
            with state.lock:
                if token:
                    state.seen_tokens.append(token)
            if token not in state.tokens:
                self.refuse(401, "invalid_request_error", "Incorrect API key provided.")
                return
            self._costs({k: v[0] for k, v in parse_qs(url.query).items()})

        def _costs(self, query: dict[str, str]) -> None:
            try:
                start = int(query["start_time"])
                end = int(query["end_time"])
                limit = int(query.get("limit", "7"))
                offset = int(query.get("page", "0"))
            except (KeyError, ValueError):
                self.refuse(400, "invalid_request_error", "invalid parameters")
                return
            if (
                query.get("bucket_width", "1d") != "1d"
                or query.get("group_by") not in ("line_item", "project_id")
                or not 1 <= limit <= 180
                or not start < end
                or start < EARLIEST
            ):
                self.refuse(400, "invalid_request_error", "invalid parameters")
                return
            first = datetime.fromtimestamp(start, UTC).date() + timedelta(days=offset)
            last_day = datetime.fromtimestamp(end, UTC).date()
            size = min(limit, state.page_days)
            stop = min(last_day, first + timedelta(days=size))
            buckets = []
            day = first
            while day < stop:
                buckets.append(self._bucket(day, query["group_by"]))
                day += timedelta(days=1)
            answer: dict[str, Any] = {
                "object": "page",
                "data": buckets,
                "has_more": stop < last_day,
            }
            answer["next_page"] = str(offset + size) if stop < last_day else None
            self.answer(200, answer)

        def _bucket(self, day: date, group_by: str) -> dict[str, Any]:
            with state.lock:
                items = state.costs.get(day.isoformat(), DEFAULT)
            begin = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
            results = []
            for item, amount in items.items():
                results.append(
                    {
                        "object": "organization.costs.result",
                        "amount": {"value": "@@" + amount + "@@", "currency": "usd"},
                        "line_item": item if group_by == "line_item" else None,
                        "project_id": PROJECT if group_by == "project_id" else None,
                    }
                )
            return {
                "object": "bucket",
                "start_time": begin,
                "end_time": begin + 86400,
                "results": results,
            }

    return Handler


def make_server(host: str, port: int, tokens: set[str], page_days: int = 10) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens, page_days)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9211)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    page_days = int(os.environ.get("FAKE_PAGE_DAYS", "10"))
    server = make_server(args.host, args.port, tokens, page_days)
    sys.stderr.write(f"fake model costs at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
