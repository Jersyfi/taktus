#!/usr/bin/env python3
"""A fake model provider's cost report: the cost report of the Anthropic Admin API, in memory.

The model costs connector under `connectors/taktus_connectors/anthropic/` asks
`GET /v1/organizations/cost_report`. This fake answers it in the API's shapes, with the API's
statuses, over costs it holds in memory. It exists so that the connector and the model cost
watcher can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `x-api-key` with a value the fake was started with
  (`FAKE_TOKENS`, comma separated), and `anthropic-version`. Otherwise 401, or 400 without the
  version.
- **The request.** `starting_at` and `ending_at` are moments at midnight UTC with the start
  before the end, `bucket_width` is `1d`, `group_by[]` is `description` or `workspace_id`, and
  `limit` is from 1 to 31. A start before 2020-01-01 is refused as the API refuses a period it
  holds no data for. Anything else is 400 with an `invalid_request_error`.
- **Pages.** At most `FAKE_PAGE_DAYS` buckets (default 10, never above `limit`) per answer, with
  `has_more` and a `next_page` that `page` carries back.

The costs: every day two descriptions, `Claude Sonnet input tokens` 412.5 cents and
`Claude Sonnet output tokens` 1250 cents, in `USD`, in the default workspace (`null`), unless a
test set other amounts for a day with `POST /_fake/costs`, a JSON object
`{date: {description: cents}}`. Amounts are decimal text in cents, as the report gives them.
Test-only: `GET /_fake/state` counts the requests and names the keys seen.
Standard library only; runnable as `python3 tests/fakes/cost_report_service.py --port 9212`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

DEFAULT = {"Claude Sonnet input tokens": "412.5", "Claude Sonnet output tokens": "1250"}
GROUPS = {"description", "workspace_id"}


class State:
    def __init__(self, keys: set[str], page_days: int) -> None:
        self.keys = keys
        self.page_days = page_days
        self.costs: dict[str, dict[str, str]] = {}
        self.requests = 0
        self.seen_keys: list[str] = []
        self.lock = threading.Lock()


def _day(text: str) -> date:
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if (moment.hour, moment.minute, moment.second) != (0, 0, 0):
        raise ValueError("not midnight")
    return moment.date()


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

        def refuse(self, status: int, kind: str) -> None:
            self.answer(status, {"type": "error", "error": {"type": kind, "message": kind}})

        def do_POST(self) -> None:
            if self.path != "/_fake/costs":
                self.refuse(404, "not_found_error")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with state.lock:
                for day, amounts in json.loads(body).items():
                    state.costs[day] = {**DEFAULT, **amounts}
            self.answer(200, {"ok": True})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests, "seen_keys": state.seen_keys})
                return
            if url.path != "/v1/organizations/cost_report":
                self.refuse(404, "not_found_error")
                return
            with state.lock:
                state.requests += 1
            key = self.headers.get("x-api-key") or ""
            with state.lock:
                state.seen_keys.append(key)
            if key not in state.keys:
                self.refuse(401, "authentication_error")
                return
            if not self.headers.get("anthropic-version"):
                self.refuse(400, "invalid_request_error")
                return
            self._report({k: v[-1] for k, v in parse_qs(url.query).items()})

        def _report(self, query: dict[str, str]) -> None:
            try:
                start = _day(query["starting_at"])
                end = _day(query["ending_at"])
                limit = int(query.get("limit", "7"))
            except (KeyError, ValueError):
                self.refuse(400, "invalid_request_error")
                return
            group = query.get("group_by[]", "")
            if (
                query.get("bucket_width") != "1d"
                or group not in GROUPS
                or not 1 <= limit <= 31
                or not start < end
                or start < date(2020, 1, 1)
            ):
                self.refuse(400, "invalid_request_error")
                return
            first = start + timedelta(days=int(query.get("page") or 0))
            size = min(limit, state.page_days)
            last = min(end, first + timedelta(days=size))
            data = []
            day = first
            while day < last:
                with state.lock:
                    amounts = state.costs.get(day.isoformat(), DEFAULT)
                results = [
                    {
                        "currency": "USD",
                        "amount": cents,
                        "workspace_id": None,
                        "description": name if group == "description" else None,
                    }
                    for name, cents in amounts.items()
                ]
                data.append(
                    {
                        "starting_at": f"{day.isoformat()}T00:00:00Z",
                        "ending_at": f"{(day + timedelta(days=1)).isoformat()}T00:00:00Z",
                        "results": results,
                    }
                )
                day += timedelta(days=1)
            more = last < end
            offset = (last - start).days
            self.answer(
                200,
                {"data": data, "has_more": more, "next_page": str(offset) if more else None},
            )

    return Handler


def make_server(host: str, port: int, keys: set[str], page_days: int = 10) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys, page_days)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9212)
    args = parser.parse_args()
    keys = {k for k in os.environ.get("FAKE_TOKENS", "").split(",") if k}
    page_days = int(os.environ.get("FAKE_PAGE_DAYS", "10"))
    server = make_server(args.host, args.port, keys, page_days)
    sys.stderr.write(f"fake cost report at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
