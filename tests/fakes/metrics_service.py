#!/usr/bin/env python3
"""A fake metrics store that answers the query API, and a fake service to check.

The metrics connector under `connectors/taktus_connectors/prometheus/` asks
`GET /api/v1/query` and `GET /api/v1/query_range`. This fake answers both in the API's shapes,
with the API's statuses for its faults, over a fixed set of series held in memory. It exists so
that the connector can be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request to the API needs `Authorization: Bearer <value>` with a
  value the fake was started with (`FAKE_METRICS_TOKENS`, comma separated). Otherwise 401.
- **Queries.** A number, a metric name, or a metric name with label matchers `l="v"` and
  `l!="v"` joined by commas. Anything else is refused with 400 and `errorType: bad_data`, as
  the store refuses a query it cannot parse. A time that is not a number is 400 too.
- **Series.** `up` for two instances of the job `service`, `1` and `0`;
  `http_requests_total` for one, `1027`; `queue_depth` with the value `NaN`. A range repeats each
  value at every step from `start` to `end`, at most 11000 points.

The same process serves the check connector's target under `/service/`: `/service/health`
answers 200 with `ready`, `/service/slow` answers after `FAKE_CHECK_SLOW_SECONDS` (default 1.5),
`/service/missing` 404, and every other path 404. Test-only: `GET /_fake/state` counts the
requests to the API and to the service, and names the bearer tokens the service saw.
Standard library only; runnable as `python3 tests/fakes/metrics_service.py --port 9204`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

TOKENS_VARIABLE = "FAKE_METRICS_TOKENS"
SERIES: list[tuple[dict[str, str], str]] = [
    ({"__name__": "up", "job": "service", "instance": "a"}, "1"),
    ({"__name__": "up", "job": "service", "instance": "b"}, "0"),
    ({"__name__": "http_requests_total", "job": "service", "instance": "a"}, "1027"),
    ({"__name__": "queue_depth", "job": "service"}, "NaN"),
]
NAME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
MATCHER = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(!?=)\s*"([^"]*)"\s*$')
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class BadQuery(Exception):
    pass


def select(query: str) -> list[tuple[dict[str, str], str]] | str:
    """The series a query selects, or the number it is."""
    query = query.strip()
    if NUMBER.match(query):
        return query
    name, _, rest = query.partition("{")
    if NAME.match(name) is None:
        raise BadQuery("parse error")
    matchers: list[tuple[str, str, str]] = []
    if rest:
        if not rest.endswith("}"):
            raise BadQuery("unclosed {")
        inner = rest[:-1].strip()
        for part in [p for p in inner.split(",") if p.strip()]:
            match = MATCHER.match(part)
            if match is None:
                raise BadQuery("bad matcher")
            matchers.append(match.groups())  # type: ignore[arg-type]
    out = []
    for labels, value in SERIES:
        if labels["__name__"] != name:
            continue
        if all((labels.get(k) == v) == (op == "=") for k, op, v in matchers):
            out.append((labels, value))
    return out


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.api_requests = 0
        self.service_requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    slow = float(os.environ.get("FAKE_CHECK_SLOW_SECONDS", "1.5"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any, kind: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "api_requests": state.api_requests,
                            "service_requests": state.service_requests,
                            "seen_tokens": list(state.seen_tokens),
                        },
                    )
                return
            if url.path.startswith("/service/"):
                self.service(url.path)
                return
            with state.lock:
                state.api_requests += 1
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] not in state.tokens:
                self.answer(401, b"Unauthorized", "text/plain")
                return
            params = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/api/v1/query":
                self.query(params)
            elif url.path == "/api/v1/query_range":
                self.range(params)
            else:
                self.answer(404, b"404 page not found", "text/plain")

        def bad(self, detail: str) -> None:
            self.answer(400, {"status": "error", "errorType": "bad_data", "error": detail})

        def query(self, params: dict[str, str]) -> None:
            moment = params.get("time", str(time.time()))
            if NUMBER.match(moment) is None and "T" not in moment:
                self.bad("cannot parse time")
                return
            at = float(moment) if NUMBER.match(moment) else 1760000000.0
            try:
                selected = select(params.get("query", ""))
            except BadQuery as error:
                self.bad(str(error))
                return
            if isinstance(selected, str):
                data: dict[str, Any] = {"resultType": "scalar", "result": [at, selected]}
            else:
                data = {
                    "resultType": "vector",
                    "result": [
                        {"metric": labels, "value": [at, value]} for labels, value in selected
                    ],
                }
            self.answer(200, {"status": "success", "data": data})

        def range(self, params: dict[str, str]) -> None:
            try:
                start, end, step = (float(params[k]) for k in ("start", "end", "step"))
                selected = select(params.get("query", ""))
            except (KeyError, ValueError):
                self.bad("start, end and step must be numbers")
                return
            except BadQuery as error:
                self.bad(str(error))
                return
            if step <= 0 or end < start or (end - start) / step > 11000:
                self.bad("exceeded maximum resolution of 11,000 points per timeseries")
                return
            moments = [start + i * step for i in range(int((end - start) // step) + 1)]
            series = [(None, selected)] if isinstance(selected, str) else selected
            result = [
                {"metric": labels or {}, "values": [[t, value] for t in moments]}
                for labels, value in series
            ]
            self.answer(
                200, {"status": "success", "data": {"resultType": "matrix", "result": result}}
            )

        def service(self, path: str) -> None:
            with state.lock:
                state.service_requests += 1
                auth = self.headers.get("Authorization", "")
                state.seen_tokens.append(auth[7:] if auth.startswith("Bearer ") else "")
            if path == "/service/health":
                self.answer(200, b"ready", "text/plain")
            elif path == "/service/slow":
                time.sleep(slow)
                self.answer(200, b"ready, slowly", "text/plain")
            else:
                self.answer(404, b"not here", "text/plain")

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), handler(State(tokens)))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake metrics store and service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9204)
    args = parser.parse_args(argv)
    tokens = {t for t in os.environ.get(TOKENS_VARIABLE, "").split(",") if t}
    if not tokens:
        sys.stderr.write(f"{TOKENS_VARIABLE} is empty: no request will authenticate\n")
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake-metrics listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
