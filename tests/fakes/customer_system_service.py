#!/usr/bin/env python3
"""A fake customer system: the contacts and notes of the HubSpot CRM API v3, in memory.

The customer system connector under `connectors/taktus_connectors/hubspot/` posts to
`/crm/v3/objects/contacts/search`, `/crm/v3/objects/contacts`, `/crm/v3/objects/notes/search`
and `/crm/v3/objects/notes`. This fake answers them in the API's shapes as its guides state them
(https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/guide,
https://developers.hubspot.com/docs/api-reference/search/guide,
https://developers.hubspot.com/docs/api-reference/crm-notes-v3/guide): a search body of
`filterGroups` (OR-ed, each a list of `filters` AND-ed), `properties`, one `sorts` rule,
`limit` up to 200 and `after`; an answer of `total`, `results` — each `id`, `properties`,
`createdAt`, `updatedAt`, `archived` — and `paging.next.after` only while more follow; an
object created as `{properties, associations}` and answered 201. Values in filters compare
without regard to case; `CONTAINS_TOKEN` finds a token of a `;`-separated list; the
pseudo-property `associations.contact` finds the notes associated with a contact.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: Bearer <token>` with a token of `FAKE_TOKENS` (comma
  separated). Otherwise 401.
- **A search.** An operator it does not know, more than one sort, or a `limit` outside 1 to
  200 is 400 `VALIDATION_ERROR`.
- **A note.** Without `hs_timestamp`, which the notes guide marks required, 400.

The contacts: `101` with `person1@customer.example`, `102` with `person2@customer.example`,
and `103` with another address and `person2@customer.example` as an additional one — a
duplicate of `102`. Each has a first name and a phone number, answered only when asked, so that
a test shows the connector never asks. Test-only: `GET /_fake/state` counts the requests and
lists the contacts and notes.
Standard library only; runnable as `python3 tests/fakes/customer_system_service.py --port 9256`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

OPERATORS = {
    "EQ",
    "NEQ",
    "CONTAINS_TOKEN",
    "NOT_CONTAINS_TOKEN",
    "HAS_PROPERTY",
    "NOT_HAS_PROPERTY",
}
"""The operators the fake evaluates; the guide lists more, which the connector never sends."""
KNOWN = OPERATORS | {"LT", "LTE", "GT", "GTE", "BETWEEN", "IN", "NOT_IN"}


def _contact(number: int, email: str, additional: str = "") -> dict[str, Any]:
    moment = f"2026-0{number - 100}-01T09:00:00.000Z"
    return {
        "id": str(number),
        "properties": {
            "email": email,
            "hs_additional_emails": additional,
            "createdate": moment,
            "lastmodifieddate": moment,
            "lifecyclestage": "customer",
            "firstname": f"Person {number}",
            "phone": f"+49 30 {number}",
        },
        "createdAt": moment,
        "updatedAt": moment,
        "archived": False,
    }


def default_contacts() -> list[dict[str, Any]]:
    return [
        _contact(101, "person1@customer.example"),
        _contact(102, "person2@customer.example"),
        _contact(103, "other@customer.example", "person2@customer.example"),
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.contacts = default_contacts()
        self.notes: list[dict[str, Any]] = []
        self.requests = 0
        self.next_id = 500
        self.lock = threading.Lock()


def _holds(record: dict[str, Any], test: dict[str, Any], associations: list[str]) -> bool:
    name, operator = test.get("propertyName"), test.get("operator")
    wanted = str(test.get("value", "")).lower()
    if name == "associations.contact":
        return operator == "EQ" and wanted in associations
    value = record["properties"].get(name)
    text = str(value).lower() if value is not None else None
    tokens = [t.strip() for t in (text or "").split(";") if t.strip()]
    return {
        "EQ": text == wanted,
        "NEQ": text != wanted,
        "CONTAINS_TOKEN": wanted in tokens,
        "NOT_CONTAINS_TOKEN": wanted not in tokens,
        "HAS_PROPERTY": bool(text),
        "NOT_HAS_PROPERTY": not text,
    }[str(operator)]


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

        def refuse(self, status: int, category: str) -> None:
            self.answer(status, {"status": "error", "message": f"refused by the fake: {category}",
                                 "correlationId": "fake", "category": category})  # fmt: skip

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/_fake/state":
                self.refuse(404, "OBJECT_NOT_FOUND")
                return
            with state.lock:
                self.answer(200, {"requests": state.requests, "contacts": state.contacts,
                                  "notes": state.notes})  # fmt: skip

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            with state.lock:
                state.requests += 1
            auth = self.headers.get("Authorization") or ""
            if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ") not in state.tokens:
                self.refuse(401, "INVALID_AUTHENTICATION")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            except ValueError:
                self.refuse(400, "VALIDATION_ERROR")
                return
            with state.lock:
                if path == "/crm/v3/objects/contacts/search":
                    self._search(body, state.contacts, "contact")
                elif path == "/crm/v3/objects/notes/search":
                    self._search(body, state.notes, "note")
                elif path == "/crm/v3/objects/contacts":
                    self._create(body, state.contacts, None)
                elif path == "/crm/v3/objects/notes":
                    self._create(body, state.notes, "hs_timestamp")
                else:
                    self.refuse(404, "OBJECT_NOT_FOUND")

        def _search(self, body: Any, records: list[dict[str, Any]], kind: str) -> None:
            groups = body.get("filterGroups") or []
            limit = body.get("limit", 10)
            tests = [t for g in groups for t in g.get("filters") or []]
            if (
                not isinstance(limit, int)
                or not 1 <= limit <= 200
                or len(body.get("sorts") or []) > 1
                or any(t.get("operator") not in KNOWN for t in tests)
            ):
                self.refuse(400, "VALIDATION_ERROR")
                return
            if any(t.get("operator") not in OPERATORS for t in tests):
                self.refuse(400, "VALIDATION_ERROR")
                return
            chosen = [
                r
                for r in records
                if not groups
                or any(
                    all(_holds(r, t, r.get("associated", [])) for t in g.get("filters") or [])
                    for g in groups
                )
            ]
            for sort in body.get("sorts") or []:
                chosen.sort(
                    key=lambda r: str(r["properties"].get(sort["propertyName"]) or ""),
                    reverse=sort.get("direction") == "DESCENDING",
                )
            start = int(body.get("after") or 0)
            page = chosen[start : start + limit]
            wanted = body.get("properties") or ["createdate", "lastmodifieddate"]
            answer: dict[str, Any] = {
                "total": len(chosen),
                "results": [
                    {
                        "id": r["id"],
                        "properties": {k: v for k, v in r["properties"].items() if k in wanted},
                        "createdAt": r["createdAt"],
                        "updatedAt": r["updatedAt"],
                        "archived": False,
                    }
                    for r in page
                ],
            }
            if start + limit < len(chosen):
                answer["paging"] = {"next": {"after": str(start + limit)}}
            self.answer(200, answer)

        def _create(self, body: Any, records: list[dict[str, Any]], required: str | None) -> None:
            properties = body.get("properties") if isinstance(body, dict) else None
            if not isinstance(properties, dict) or (required and not properties.get(required)):
                self.refuse(400, "VALIDATION_ERROR")
                return
            associated = [
                str((a.get("to") or {}).get("id"))
                for a in body.get("associations") or []
                if any(t.get("associationTypeId") == 202 for t in a.get("types") or [])
            ]
            state.next_id += 1
            moment = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            record = {
                "id": str(state.next_id),
                "properties": {"createdate": moment, "lastmodifieddate": moment, **properties},
                "createdAt": moment,
                "updatedAt": moment,
                "archived": False,
                "associated": associated,
            }
            records.append(record)
            self.answer(201, {k: v for k, v in record.items() if k != "associated"})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9256)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake customer system at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
