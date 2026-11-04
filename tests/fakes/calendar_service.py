#!/usr/bin/env python3
"""A fake calendar server: one calendar of deadlines, as an iCalendar file and over CalDAV.

The calendar connector under `connectors/taktus_connectors/calendar/` asks `GET <path>` for an
iCalendar file (RFC 5545) or `REPORT <path>` with a `calendar-query` (RFC 4791). This fake
answers both over one calendar held in memory. It exists so that the connector can be exercised
in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>`, or basic
  authentication whose `user:password` is such a value, from the values the fake was started
  with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **Paths.** `GET /calendars/deadlines.ics` answers the whole calendar; `REPORT
  /calendars/deadlines/` with `Depth: 1` answers a `multistatus` with one `calendar-data` per
  calendar object holding a component of the kind the query's inner `comp-filter` names.
  `GET /calendars/upcoming.ics` answers a second calendar counted from the day of the request,
  for a test that reads from now: an insurance renewal in 10 days, the notice of a supplier
  contract as a to-do due in 20 days at noon UTC, and a licence renewal in 60 days. Every other
  path is 404; a `REPORT` whose body names no such filter is 400.

The calendar: an advance VAT return on the 10th of every month (`EXDATE` 2026-12-10, and the
November one moved to the 12th by a `RECURRENCE-ID`); the yearly VAT return on 2027-01-10; the
notice period of an office lease as a to-do due 2026-11-30 18:00 in Europe/Berlin; a hosting
contract renewing every 15 December at 09:00 UTC; and a payroll on the last Friday of each
month, whose rule has a `BYDAY` part. Test-only: `GET /_fake/state` counts the requests and
names the credentials seen. Standard library only; runnable as
`python3 tests/fakes/calendar_service.py --port 9216`.
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
from urllib.parse import urlparse

OBJECTS: dict[str, str] = {
    "vat-monthly": (
        "BEGIN:VEVENT\r\nUID:vat-monthly@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "DTSTART;VALUE=DATE:20260110\r\nRRULE:FREQ=MONTHLY\r\nEXDATE;VALUE=DATE:20261210\r\n"
        "SUMMARY:Advance VAT return\r\nCATEGORIES:tax\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:vat-monthly@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "RECURRENCE-ID;VALUE=DATE:20261110\r\nDTSTART;VALUE=DATE:20261112\r\n"
        "SUMMARY:Advance VAT return (moved)\r\nCATEGORIES:tax\r\nEND:VEVENT\r\n"
    ),
    "vat-yearly": (
        "BEGIN:VEVENT\r\nUID:vat-yearly@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "DTSTART;VALUE=DATE:20270110\r\nSUMMARY:VAT return for the year\r\n"
        "DESCRIPTION:Filed with the tax office\\, signed by the managing director.\r\n"
        "CATEGORIES:tax\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-P14D\r\n"
        "SUMMARY:not an entry\r\nEND:VALARM\r\nEND:VEVENT\r\n"
    ),
    "office-notice": (
        "BEGIN:VTODO\r\nUID:office-notice@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "DUE;TZID=Europe/Berlin:20261130T180000\r\nSUMMARY:Notice period of the office lea\r\n"
        " se ends\r\nCATEGORIES:contract,notice\r\nEND:VTODO\r\n"
    ),
    "hosting-renewal": (
        "BEGIN:VEVENT\r\nUID:hosting-renewal@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "DTSTART:20251215T090000Z\r\nDTEND:20251215T093000Z\r\nRRULE:FREQ=YEARLY\r\n"
        "SUMMARY:Hosting contract renews\r\nCATEGORIES:renewal\r\nEND:VEVENT\r\n"
    ),
    "payroll": (
        "BEGIN:VEVENT\r\nUID:payroll@deadlines.example\r\nDTSTAMP:20260101T000000Z\r\n"
        "DTSTART;VALUE=DATE:20260130\r\nRRULE:FREQ=MONTHLY;BYDAY=-1FR\r\n"
        "SUMMARY:Payroll\r\nEND:VEVENT\r\n"
    ),
}
HEAD = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//fake//deadlines//EN\r\n"
TAIL = "END:VCALENDAR\r\n"
KIND = re.compile(rb'comp-filter\s+name="(VEVENT|VTODO)"')


def upcoming(today: date) -> str:
    """The second calendar, counted from `today`."""

    def day(n: int) -> str:
        return (today + timedelta(days=n)).strftime("%Y%m%d")

    return (
        HEAD + "BEGIN:VEVENT\r\nUID:insurance@upcoming.example\r\nDTSTAMP:20260101T000000Z\r\n"
        f"DTSTART;VALUE=DATE:{day(10)}\r\nSUMMARY:Insurance renews\r\n"
        "CATEGORIES:renewal\r\nEND:VEVENT\r\n"
        "BEGIN:VTODO\r\nUID:supplier-notice@upcoming.example\r\nDTSTAMP:20260101T000000Z\r\n"
        f"DUE:{day(20)}T120000Z\r\nSUMMARY:Notice to the supplier\r\n"
        "CATEGORIES:contract,notice\r\nEND:VTODO\r\n"
        "BEGIN:VEVENT\r\nUID:licence@upcoming.example\r\nDTSTAMP:20260101T000000Z\r\n"
        f"DTSTART;VALUE=DATE:{day(60)}\r\nSUMMARY:Licence renews\r\nEND:VEVENT\r\n" + TAIL
    )


def calendar(*names: str) -> str:
    return HEAD + "".join(OBJECTS[n] for n in (names or OBJECTS)) + TAIL


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.requests = 0
        self.seen: list[str] = []
        self.lock = threading.Lock()


def _credential(header: str) -> str:
    if header.startswith("Bearer "):
        return header[7:]
    if header.startswith("Basic "):
        try:
            return base64.b64decode(header[6:]).decode("utf-8")
        except ValueError:
            return ""
    return ""


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def admitted(self) -> bool:
            credential = _credential(self.headers.get("Authorization", ""))
            with state.lock:
                state.requests += 1
                state.seen.append(credential)
            if credential in state.tokens:
                return True
            self.answer(401, b"Unauthorized", "text/plain")
            return False

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/_fake/state":
                with state.lock:
                    body = {"requests": state.requests, "seen_tokens": list(state.seen)}
                self.answer(200, json.dumps(body).encode(), "application/json")
                return
            if not self.admitted():
                return
            if path == "/calendars/deadlines.ics":
                self.answer(200, calendar().encode(), "text/calendar; charset=utf-8")
            elif path == "/calendars/upcoming.ics":
                text = upcoming(datetime.now(UTC).date())
                self.answer(200, text.encode(), "text/calendar; charset=utf-8")
            else:
                self.answer(404, b"not here", "text/plain")

        def do_REPORT(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
            if not self.admitted():
                return
            if urlparse(self.path).path.rstrip("/") != "/calendars/deadlines":
                self.answer(404, b"not here", "text/plain")
                return
            match = KIND.search(body)
            if match is None or self.headers.get("Depth") != "1":
                self.answer(400, b"a calendar-query with Depth 1", "text/plain")
                return
            kind = match.group(1).decode()
            responses = "".join(
                f"<D:response><D:href>/calendars/deadlines/{name}.ics</D:href><D:propstat>"
                f"<D:prop><C:calendar-data>{_escaped(calendar(name))}</C:calendar-data>"
                "</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>"
                for name, text in OBJECTS.items()
                if f"BEGIN:{kind}" in text
            )
            xml = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
                f"{responses}</D:multistatus>"
            )
            self.answer(207, xml.encode(), "application/xml; charset=utf-8")

    return Handler


def _escaped(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), handler(State(tokens)))
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9216)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake calendar at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
