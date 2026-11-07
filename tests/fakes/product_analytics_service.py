#!/usr/bin/env python3
"""A fake of the Mixpanel Query API: the aggregate event counts the product analytics connector
asks for, in memory.

The connector under `connectors/taktus_connectors/mixpanel/` asks `GET /api/query/events`
(*Aggregate Event Counts*, https://docs.mixpanel.com/reference/list-recent-events) with
`project_id`, optionally `workspace_id`, `event` (a JSON array of event names), `type`
(`general`, `unique` or `average`), `unit` (`minute`, `hour`, `day`, `week` or `month`),
`from_date` and `to_date` (yyyy-mm-dd, both inclusive), authenticated with a service account
as HTTP Basic (https://docs.mixpanel.com/reference/service-accounts). The answer is the
documented `{"data": {"series": [...], "values": {event: {unit key: number}}}, "legend_size":
n}`: `series` every unit of the range, `values` the events that have data, `legend_size` how
many they are.

The fake answers from a seeded project, `1234567`: for each of the 70 days up to and including
today and each of the events `sign up`, `page view` and `purchase`, a set of users who did the
event that day, and a number of events. `general` sums the events of a unit, `unique` counts
the users of the unit once, `average` divides the one by the other. A day is keyed `YYYY-MM-DD`
as the reference shows; the reference shows no week or month key, and the fake keys a week by
its Monday and a month by its first day. `unit=hour` with `type=unique` is refused, as the
reference says hourly uniques cannot be had. An event the project does not hold has no entry in
`values`.

The reference documents no error answer except 429 (its rate limits page); the fake answers 400
for a parameter missing or malformed, 401 for a service account it does not admit, 403 for
another project, each with a short text body the connector does not read. Test-only:
`GET /_fake/state` counts the queries and lists their parameters; `POST /_fake/fail` with
`{"status": 429}` makes the next query answer that status; `POST /_fake/reset` restores the
start. Standard library only; runnable as
`python3 tests/fakes/product_analytics_service.py --port 9282`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

PROJECT = "1234567"
EVENTS = ("sign up", "page view", "purchase")
DAYS = 70
TYPES = ("general", "unique", "average")
UNITS = ("minute", "hour", "day", "week", "month")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> date:
    return datetime.now(UTC).date()


def users(day: date, n: int) -> set[int]:
    """The users who did event `n` on `day`: overlapping from one day to the next."""
    start = (day.toordinal() * 3) % 40
    return set(range(start, start + 30 // (n + 1) + day.toordinal() % 5))


def events(day: date, n: int) -> int:
    return len(users(day, n)) * (3 - n)


def key(day: date, unit: str) -> str:
    if unit == "week":
        return (day - timedelta(days=day.weekday())).isoformat()
    if unit == "month":
        return day.replace(day=1).isoformat()
    return day.isoformat()


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.asked: list[Json] = []
        self.fail: int | None = None

    def counts(self, query: Json) -> tuple[int, Any]:
        project = query.get("project_id")
        if not project:
            return 400, "project_id is required when authenticating with a service account"
        if project != PROJECT:
            return 403, "the service account has no access to this project"
        try:
            names = json.loads(query.get("event", ""))
        except ValueError:
            return 400, "event must be a JSON array"
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            return 400, "event must be a JSON array of event names"
        kind, unit = query.get("type"), query.get("unit")
        if kind not in TYPES or unit not in UNITS:
            return 400, "type and unit are required"
        if unit in ("minute", "hour") and kind == "unique":
            return 400, "hourly uniques are not available"
        start, end = query.get("from_date", ""), query.get("to_date", "")
        if not DATE.match(start) or not DATE.match(end):
            return 400, "from_date and to_date must be yyyy-mm-dd"
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last:
            return 400, "from_date lies after to_date"
        now = today()
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        series = sorted({key(d, unit) for d in days})
        values: Json = {}
        for name in names:
            if name not in EVENTS:
                continue
            n = EVENTS.index(name)
            buckets: dict[str, tuple[set[int], int]] = {}
            for day in days:
                if not now - timedelta(days=DAYS - 1) <= day <= now:
                    continue
                seen, total = buckets.setdefault(key(day, unit), (set(), 0))
                buckets[key(day, unit)] = (seen | users(day, n), total + events(day, n))
            counted: Json = {}
            for k, (seen, total) in buckets.items():
                if kind == "general":
                    counted[k] = total
                elif kind == "unique":
                    counted[k] = len(seen)
                else:
                    counted[k] = round(total / len(seen), 2) if seen else 0
            if counted:
                values[name] = counted
        return 200, {"data": {"series": series, "values": values}, "legend_size": len(values)}


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def answer(self, status: int, body: Any) -> None:
            if isinstance(body, str):
                data, kind = body.encode("utf-8"), "text/plain"
            else:
                data, kind = json.dumps(body).encode("utf-8"), "application/json"
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def admitted(self) -> bool:
            given = self.headers.get("Authorization", "")
            if not given.startswith("Basic "):
                return False
            try:
                return base64.b64decode(given[6:]).decode("utf-8") in state.tokens
            except ValueError:
                return False

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"queries": len(state.asked), "asked": list(state.asked)})
                return
            if url.path != "/api/query/events":
                self.answer(404, "not found")
                return
            if not self.admitted():
                self.answer(401, "invalid service account credentials")
                return
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            with state.lock:
                state.asked.append(query)
                fail, state.fail = state.fail, None
            if fail is not None:
                self.answer(fail, "query failed")
                return
            self.answer(*state.counts(query))

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/_fake/reset":
                with state.lock:
                    state.reset()
                self.answer(200, {"reset": True})
                return
            if path == "/_fake/fail":
                with state.lock:
                    state.fail = int(json.loads(raw or b"{}").get("status", 500))
                self.answer(200, {})
                return
            self.answer(404, "not found")

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9282)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake product analytics service at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
