#!/usr/bin/env python3
"""A fake log store: the range query of the Grafana Loki HTTP API, in memory.

The log store connector under `connectors/taktus_connectors/loki/` asks
`GET /loki/api/v1/query_range` with `query`, `start`, `end`, `limit` and `direction`. This
fake answers it in the API's shape, `{"status": "success", "data": {"resultType", "result",
"stats"}}`, over lines it holds in memory. It exists so that the connector can be exercised
in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: Bearer <value>`, or `Basic` over `<user>:<password>`,
  with a value the fake was started with (`FAKE_TOKENS`, comma separated: a bearer value, or
  the whole `<user>:<password>` text). Otherwise 401. The API itself has no authentication;
  a gateway in front of it, or the hosted service, answers 401 this way.
- **The tenant.** Started with a tenant (`FAKE_TENANT`), the fake answers 401 `no org id`
  unless `X-Scope-OrgID` names it, as a store with authentication enabled does.
- **Parameters.** `start` and `end` as nanoseconds since the epoch (the API also takes
  seconds and RFC 3339; the fake takes only what the connector sends), `start` before `end`,
  `limit` from 1 to 5000 (the store's default `max_entries_limit_per_query`), `direction`
  `forward` or `backward`. Otherwise 400 with a plain-text message.
- **The query.** Of LogQL the fake knows a stream selector of `=`, `!=`, `=~` and `!~`
  matchers, at least one of which must not match the empty value, and line filters `|=`,
  `!=`, `|~` and `!~`. A metric query, a range aggregation such as
  `count_over_time(<log query>[5m])`, answers `resultType` `matrix` with one series per stream
  and one point, the count of its lines in the window. Any other LogQL, a parser stage like
  `| json` among it, is 400 here, though the store would take it.
- **The window and the limit.** Lines from `start` (inclusive) to `end` (exclusive), at most
  `limit` of them across every stream, the newest where `direction` is `backward`.

The lines: eight, of four streams of the apps `shop` and `ledger`, one every thirty seconds
before the fake started, the newest thirty seconds before. One stream carries the label
`level`, one `detected_level`, one neither. Test-only: `GET /_fake/state` counts the requests,
names the authentication schemes and tenants seen, and the last query's parameters.
Standard library only; runnable as `python3 tests/fakes/log_store_service.py --port 9231`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

PATH = "/loki/api/v1/query_range"
MAX_LIMIT = 5000
MATCHER = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*"((?:[^"\\]|\\.)*)"\s*')
FILTER = re.compile(r'\s*(\|=|!=|\|~|!~)\s*"((?:[^"\\]|\\.)*)"')
METRIC = re.compile(r"^\s*([a-z_]+)\s*\((.*)\[(\d+[smhd])\]\s*\)\s*$", re.DOTALL)
RANGE_AGGREGATIONS = {"count_over_time", "rate", "bytes_over_time", "bytes_rate"}


def lines(started: float) -> list[tuple[dict[str, str], int, str]]:
    """Eight lines of four streams, one every thirty seconds before `started` (seconds)."""
    error = {"app": "shop", "env": "prod", "level": "error"}
    info = {"app": "shop", "env": "prod", "level": "info"}
    ledger = {"app": "ledger", "env": "prod", "detected_level": "warn"}
    staging = {"app": "shop", "env": "staging"}
    table = [
        (error, "order 1042 failed: card declined"),
        (info, "order 1043 placed"),
        (ledger, "balance check slow: 1840ms"),
        (staging, "order 17 placed"),
        (info, "health check ok"),
        (error, "order 1039 failed: upstream timeout"),
        (ledger, "journal entry 88 posted"),
        (info, "order 1038 placed"),
    ]
    out = []
    for n, (labels, line) in enumerate(table):
        nanos = int((started - 30 - 30 * n) * 1_000_000_000)
        out.append((labels, nanos, line))
    return out


class State:
    def __init__(self, tokens: set[str], tenant: str | None) -> None:
        self.tokens = tokens
        self.tenant = tenant
        self.lines = lines(time.time())
        self.requests = 0
        self.schemes: list[str] = []
        self.tenants: list[str | None] = []
        self.last: dict[str, str] = {}
        self.lock = threading.Lock()


class Refused(Exception):
    """The query is not one the fake knows: 400 with this message."""


def _unquote(text: str) -> str:
    return text.encode().decode("unicode_escape")


def parse_log_query(query: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """The matchers and the line filters of a log query; Refused where it is not one."""
    query = query.strip()
    if not query.startswith("{") or "}" not in query:
        raise Refused("parse error : queries require a stream selector")
    matchers: list[tuple[str, str, str]] = []
    position = 1
    while True:
        found = MATCHER.match(query, position)
        if found is None:
            raise Refused("parse error : a matcher is not one the fake knows")
        matchers.append((found[1], found[2], _unquote(found[3])))
        position = found.end()
        if query[position : position + 1] == ",":
            position += 1
            continue
        if query[position : position + 1] == "}":
            rest = query[position + 1 :]
            break
        raise Refused("parse error : the stream selector is not closed")
    if not any(
        (op == "=" and v) or (op == "=~" and not re.fullmatch(v, "")) for _, op, v in matchers
    ):
        raise Refused(
            "parse error : queries require at least one regexp or equality matcher that does "
            "not have an empty-compatible value"
        )
    filters: list[tuple[str, str]] = []
    position = 0
    while position < len(rest):
        if not rest[position:].strip():
            break
        found = FILTER.match(rest, position)
        if found is None:
            raise Refused("parse error : a pipeline stage the fake does not know")
        filters.append((found[1], _unquote(found[2])))
        position = found.end()
    return matchers, filters


def _selected(labels: dict[str, str], matchers: list[tuple[str, str, str]]) -> bool:
    for name, op, value in matchers:
        have = labels.get(name, "")
        if op == "=" and have != value:
            return False
        if op == "!=" and have == value:
            return False
        if op == "=~" and not re.fullmatch(value, have):
            return False
        if op == "!~" and re.fullmatch(value, have):
            return False
    return True


def _kept(line: str, filters: list[tuple[str, str]]) -> bool:
    for op, value in filters:
        if op == "|=" and value not in line:
            return False
        if op == "!=" and value in line:
            return False
        if op == "|~" and not re.search(value, line):
            return False
        if op == "!~" and re.search(value, line):
            return False
    return True


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def send(self, status: int, body: Any) -> None:
            text = isinstance(body, str)
            data = (body if text else json.dumps(body)).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain" if text else "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _admitted(self) -> bool:
            header = self.headers.get("Authorization") or ""
            scheme, _, value = header.partition(" ")
            if scheme == "Basic":
                try:
                    value = base64.b64decode(value, validate=True).decode()
                except (binascii.Error, UnicodeDecodeError):
                    value = ""
            with state.lock:
                state.schemes.append(scheme)
                state.tenants.append(self.headers.get("X-Scope-OrgID"))
            if scheme not in ("Bearer", "Basic") or value not in state.tokens:
                self.send(401, "unauthorized\n")
                return False
            if state.tenant is not None and self.headers.get("X-Scope-OrgID") != state.tenant:
                self.send(401, "no org id\n")
                return False
            return True

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.send(
                        200,
                        {
                            "requests": state.requests,
                            "schemes": state.schemes,
                            "tenants": state.tenants,
                            "last": state.last,
                        },
                    )
                return
            if url.path != PATH:
                self.send(404, "404 page not found\n")
                return
            with state.lock:
                state.requests += 1
            if not self._admitted():
                return
            params = {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
            with state.lock:
                state.last = params
            try:
                self.send(200, self._query(params))
            except Refused as refused:
                self.send(400, f"{refused}\n")

        def _query(self, params: dict[str, str]) -> dict[str, Any]:
            try:
                start = int(params["start"])
                end = int(params["end"])
                limit = int(params.get("limit", "100"))
            except (KeyError, ValueError) as error:
                raise Refused("invalid parameter: start, end and limit are integers") from error
            direction = params.get("direction", "backward")
            if (
                not start < end
                or not 1 <= limit <= MAX_LIMIT
                or direction
                not in (
                    "forward",
                    "backward",
                )
            ):
                raise Refused("invalid parameter: the window, limit or direction")
            query = params.get("query", "")
            metric = METRIC.match(query)
            if metric is not None:
                if metric[1] not in RANGE_AGGREGATIONS:
                    raise Refused("parse error : an aggregation the fake does not know")
                return self._matrix(*parse_log_query(metric[2]), start, end)
            matchers, filters = parse_log_query(query)
            with state.lock:
                held = list(state.lines)
            found = sorted(
                (
                    (labels, nanos, line)
                    for labels, nanos, line in held
                    if start <= nanos < end and _selected(labels, matchers) and _kept(line, filters)
                ),
                key=lambda item: item[1],
                reverse=direction == "backward",
            )[:limit]
            streams: dict[str, dict[str, Any]] = {}
            for labels, nanos, line in found:
                key = json.dumps(labels, sort_keys=True)
                stream = streams.setdefault(key, {"stream": labels, "values": []})
                stream["values"].append([str(nanos), line])
            return {
                "status": "success",
                "data": {"resultType": "streams", "result": list(streams.values()), "stats": {}},
            }

        def _matrix(
            self,
            matchers: list[tuple[str, str, str]],
            filters: list[tuple[str, str]],
            start: int,
            end: int,
        ) -> dict[str, Any]:
            counts: dict[str, tuple[dict[str, str], int]] = {}
            with state.lock:
                held = list(state.lines)
            for labels, nanos, line in held:
                if start <= nanos < end and _selected(labels, matchers) and _kept(line, filters):
                    key = json.dumps(labels, sort_keys=True)
                    counts[key] = (labels, counts.get(key, (labels, 0))[1] + 1)
            result = [
                {"metric": labels, "values": [[end // 1_000_000_000, str(n)]]}
                for labels, n in counts.values()
            ]
            return {
                "status": "success",
                "data": {"resultType": "matrix", "result": result, "stats": {}},
            }

    return Handler


def make_server(
    host: str, port: int, tokens: set[str], tenant: str | None = None
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens, tenant)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9231)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    tenant = os.environ.get("FAKE_TENANT") or None
    server = make_server(args.host, args.port, tokens, tenant)
    sys.stderr.write(f"fake log store at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
