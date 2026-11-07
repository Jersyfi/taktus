#!/usr/bin/env python3
"""A fake of the Google Analytics Data API v1beta: the report the analytics connector asks for,
in memory.

The connector under `connectors/taktus_connectors/googleanalytics/` asks
`POST /v1beta/properties/123456789:runReport`
(https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport)
with `dimensions`, `metrics`, one `dateRanges` entry, `limit` and `orderBys`. The fake answers
from a seeded table: for each of the 56 days up to and including today, and each of the events
`page_view`, `sign_up` and `purchase`, the metrics `activeUsers`, `newUsers`, `eventCount` and
`sessions`. It groups by the dimensions asked — `date` (YYYYMMDD, as the API writes it),
`eventName` and `isoYearIsoWeek` — and sums the metrics; it orders, cuts at `limit`, and counts
every group in `rowCount`. Values are text, as the API gives them. A dimension or metric it does
not know is 400 `INVALID_ARGUMENT` in Google's error shape; another property is 403
`PERMISSION_DENIED`. Dates are YYYY-MM-DD, `today`, `yesterday` or `NdaysAgo`.

And `POST /token`, the OAuth token endpoint (`google_oauth.py`): every other request needs a
token it issued. Test-only: `GET /_fake/state` counts the reports answered;
`POST /_fake/metadata` with `{"subjectToThresholding": true}` or `{"dataLossFromOtherRow": true}`
sets the metadata of every later report; `POST /_fake/reset` restores the start. Runnable as
`python3 tests/fakes/analytics_service.py --port 9237`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

try:
    from fakes.google_oauth import Tokens, keys_from
except ImportError:  # run as a script from its own directory
    from google_oauth import Tokens, keys_from  # type: ignore[import-not-found,no-redef]

type Json = dict[str, Any]

PROPERTY = "123456789"
EVENTS = ("page_view", "sign_up", "purchase")
DIMENSIONS = ("date", "eventName", "isoYearIsoWeek")
METRICS = ("activeUsers", "newUsers", "eventCount", "sessions")
DAYS = 56
RELATIVE = re.compile(r"^(\d+)daysAgo$")


def table(today: date) -> list[Json]:
    """Eight weeks of daily figures per event, the same every time the fake starts."""
    rows = []
    for back in range(DAYS):
        day = today - timedelta(days=back)
        base = 100 + (day.toordinal() % 7) * 10
        for n, event in enumerate(EVENTS):
            iso = day.isocalendar()
            rows.append(
                {
                    "day": day,
                    "date": day.strftime("%Y%m%d"),
                    "eventName": event,
                    "isoYearIsoWeek": f"{iso.year}{iso.week:02d}",
                    "activeUsers": base // (n + 1),
                    "newUsers": base // (4 * (n + 1)),
                    "eventCount": base * (3 - n),
                    "sessions": base // (n + 1) + 5,
                }
            )
    return rows


def resolve(word: str, today: date) -> date | None:
    if word == "today":
        return today
    if word == "yesterday":
        return today - timedelta(days=1)
    relative = RELATIVE.match(word)
    if relative:
        return today - timedelta(days=int(relative.group(1)))
    try:
        return date.fromisoformat(word)
    except ValueError:
        return None


def error(code: int, status: str, message: str) -> Json:
    return {"error": {"code": code, "message": message, "status": status}}


class State:
    def __init__(self, keys: set[str]) -> None:
        self.tokens = Tokens(keys)
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.reports = 0
        self.metadata: Json = {}

    def report(self, body: Json) -> tuple[int, Json]:
        dims = [d.get("name") for d in body.get("dimensions") or []]
        mets = [m.get("name") for m in body.get("metrics") or []]
        for name in dims:
            if name not in DIMENSIONS:
                return 400, error(
                    400, "INVALID_ARGUMENT", f"Field {name} is not a valid dimension."
                )
        for name in mets:
            if name not in METRICS:
                return 400, error(400, "INVALID_ARGUMENT", f"Field {name} is not a valid metric.")
        if not mets:
            return 400, error(400, "INVALID_ARGUMENT", "At least one metric is required.")
        today = date.today()
        (ranges,) = body.get("dateRanges") or [{}]
        start = resolve(str(ranges.get("startDate", "")), today)
        end = resolve(str(ranges.get("endDate", "")), today)
        if start is None or end is None or start > end:
            return 400, error(400, "INVALID_ARGUMENT", "Invalid date range.")
        groups: dict[tuple[str, ...], Json] = {}
        for row in table(today):
            if not start <= row["day"] <= end:
                continue
            key = tuple(str(row[d]) for d in dims)
            sums = groups.setdefault(key, dict.fromkeys(mets, 0))
            for m in mets:
                sums[m] += row[m]
        items = sorted(groups.items())
        for order in reversed(body.get("orderBys") or []):
            desc = bool(order.get("desc"))
            if "metric" in order:
                name = order["metric"]["metricName"]
                items.sort(key=lambda kv, n=name: kv[1][n], reverse=desc)
            elif "dimension" in order:
                index = dims.index(order["dimension"]["dimensionName"])
                items.sort(key=lambda kv, i=index: kv[0][i], reverse=desc)
        limit = int(body.get("limit") or 10000)
        rows = [
            {
                "dimensionValues": [{"value": v} for v in key],
                "metricValues": [{"value": str(sums[m])} for m in mets],
            }
            for key, sums in items[:limit]
        ]
        with self.lock:
            self.reports += 1
        answer: Json = {
            "dimensionHeaders": [{"name": d} for d in dims],
            "metricHeaders": [{"name": m, "type": "TYPE_INTEGER"} for m in mets],
            "rows": rows,
            "rowCount": len(items),
            "metadata": {"currencyCode": "EUR", "timeZone": "Europe/Berlin", **self.metadata},
            "kind": "analyticsData#runReport",
        }
        if not rows:
            del answer["rows"]
        return 200, answer


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Json) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/_fake/state":
                self.answer(200, {"reports": state.reports})
                return
            self.answer(404, error(404, "NOT_FOUND", "Not found."))

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            raw = self.body()
            if path == "/token":
                self.answer(*state.tokens.grant(raw))
                return
            if path == "/_fake/reset":
                state.reset()
                self.answer(200, {})
                return
            if path == "/_fake/metadata":
                state.metadata.update(json.loads(raw or b"{}"))
                self.answer(200, {})
                return
            if not state.tokens.admits(self.headers.get("Authorization")):
                self.answer(401, error(401, "UNAUTHENTICATED", "Request had invalid credentials."))
                return
            found = re.fullmatch(r"/v1beta/properties/([^/:]+):runReport", path)
            if found is None:
                self.answer(404, error(404, "NOT_FOUND", "Not found."))
                return
            if found.group(1) != PROPERTY:
                self.answer(
                    403,
                    error(403, "PERMISSION_DENIED", "User does not have sufficient permissions."),
                )
                return
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                self.answer(400, error(400, "INVALID_ARGUMENT", "Invalid JSON payload."))
                return
            self.answer(*state.report(body))

    return Handler


def make_server(host: str, port: int, keys: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9237)
    args = parser.parse_args()
    server = make_server(args.host, args.port, keys_from(os.environ.get("FAKE_TOKENS", "")))
    sys.stderr.write(f"fake analytics API at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
