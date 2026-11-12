#!/usr/bin/env python3
"""A fake mail API: the part of the Resend API the transactional mail connector uses, in
memory.

The connector under `connectors/taktus_connectors/resend/` asks:

- `POST /emails`: a message sent, `{"id": ...}`; `from` on the verified domain `example.org`,
  or 403 `validation_error`; `to` one to fifty addresses and a `subject`, or 422
  `missing_required_field`. The `Idempotency-Key` header is honoured as documented: the same key
  with the same body answers the original's identifier and sends nothing; with another body
  409 `invalid_idempotent_request`; a key longer than 256 characters 400
  `invalid_idempotency_key`. `tags` are kept and `headers` too;
- `GET /emails?limit=&after=`: the messages sent, newest first, `{"object": "list", "has_more",
  "data"}`, each with `id`, `message_id`, `to`, `from`, `created_at`, `subject`, `bcc`, `cc`,
  `reply_to`, `last_event`, `scheduled_at` — no tags, as the documentation lists it;
- `GET /emails/<id>`: one message sent, with `html`, `text` and `tags`;
- `GET /emails/receiving/<id>`: one message received, with `text`, `headers`, `message_id` and
  `attachments`;
- `POST /broadcasts`, `GET /broadcasts?limit=&after=`, `GET /broadcasts/<id>`,
  `POST /broadcasts/<id>/send`: a broadcast created as a `draft` to a `segment_id`, listed,
  read, sent; a send makes it `sent`. A segment the account does not hold is 404 `not_found`.
  What the API answers for the send of a broadcast that is not a draft the documentation does
  not say; the fake answers 400 `validation_error`, and the connector reads the status before
  it sends;
- `GET /contacts?segment_id=&limit=&after=`: a segment's contacts, each with `id`, `email`,
  `first_name`, `last_name`, `created_at`, `unsubscribed`.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: Bearer` and an API key the fake was started with
  (`FAKE_TOKENS`, comma separated). None is 401 `missing_api_key`; another is
  `validation_error`, 401 on `POST /emails` and 400 elsewhere, as the documentation's error
  table lists it. The error body is `statusCode`, `message`, `name`.
- **Identifiers.** A path identifier that is not a UUID is 422 `invalid_parameter`; one the
  account does not hold is 404 `not_found`.
- **Paging.** `limit` from 1 to 100, `after` an identifier the page starts after.

It starts with two messages received — a customer's `RECEIVED` and an automatic reply
`AUTOMATIC` — one message sent `SENT`, the segment `SEGMENT` of 250 contacts of which 10 are
unsubscribed, the segment `LARGE` of 5100, and one broadcast `BROADCAST`, sent to `SEGMENT`.
Test-only: `GET /_fake/state` names every message sent with its recipients, subject, tags and
headers, every broadcast with its status, name, subject and segment, the broadcasts sent in
order and the count of requests; `POST /_fake/reset` restores the start. Standard library only;
runnable as `python3 tests/fakes/mail_api_service.py --port 9281`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

DOMAIN = "example.org"
RECEIVED = "4ef9a417-02e9-4d39-ad75-9611e0fcc33c"
AUTOMATIC = "56761188-7520-42d8-8898-ff6fc54ce618"
SENT = "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"
SEGMENT = "78261eea-8f8b-4381-83c6-79fa7120f1cf"
LARGE = "b6d24b8e-af0b-4c3c-be0c-359bbd97381e"
BROADCAST = "559ac32e-9ef5-46fb-82a1-b76b840c0f7b"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ADDRESS = re.compile(r"[^@\s<>]+@([^@\s<>]+)")
CREATED = "2026-11-01 08:00:00.000000+00"


def _contacts(segment: str, count: int, unsubscribed: int) -> list[Json]:
    return [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{segment}/{n}")),
            "email": f"reader{n}@readers.example",
            "first_name": "",
            "last_name": "",
            "created_at": CREATED,
            "unsubscribed": n < unsubscribed,
        }
        for n in range(count)
    ]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.received: dict[str, Json] = {
            RECEIVED: {
                "object": "email",
                "id": RECEIVED,
                "to": ["support@example.org"],
                "from": "A customer <customer@mail.example>",
                "created_at": "2026-11-02T08:15:00.000Z",
                "subject": "The export stopped",
                "html": "<p>Since this morning the export answers with an error.</p>",
                "html_format": "data_uri",
                "text": "Since this morning the export answers with an error.",
                "headers": {
                    "from": "A customer <customer@mail.example>",
                    "mime-version": "1.0",
                },
                "bcc": [],
                "cc": [],
                "reply_to": [],
                "received_for": ["support@example.org"],
                "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
                "message_id": "<seed-1@mail.example>",
                "attachments": [
                    {
                        "id": "2a0c9ce0-3112-4728-976e-47ddcd16a318",
                        "filename": "error.png",
                        "content_type": "image/png",
                        "content_disposition": None,
                        "content_id": None,
                        "size": 4096,
                    }
                ],
            },
            AUTOMATIC: {
                "object": "email",
                "id": AUTOMATIC,
                "to": ["support@example.org"],
                "from": "robot@mail.example",
                "created_at": "2026-11-02T08:16:00.000Z",
                "subject": "Out of office",
                "html": None,
                "text": "I am away.",
                "headers": {"from": "robot@mail.example", "auto-submitted": "auto-replied"},
                "bcc": [],
                "cc": [],
                "reply_to": [],
                "message_id": "<auto-1@mail.example>",
                "attachments": [],
            },
        }
        self.sent: list[Json] = [
            {
                "object": "email",
                "id": SENT,
                "message_id": "<sent-1@example.org>",
                "to": ["customer@mail.example"],
                "from": "support@example.org",
                "created_at": CREATED,
                "subject": "Your export",
                "html": None,
                "text": "It works again.",
                "bcc": [],
                "cc": [],
                "reply_to": [],
                "last_event": "delivered",
                "scheduled_at": None,
                "tags": [],
                "headers": {},
            }
        ]
        self.keys: dict[str, tuple[str, str]] = {}
        self.segments: dict[str, list[Json]] = {
            SEGMENT: _contacts(SEGMENT, 250, 10),
            LARGE: _contacts(LARGE, 5100, 0),
        }
        self.broadcasts: dict[str, Json] = {
            BROADCAST: {
                "object": "broadcast",
                "id": BROADCAST,
                "name": "October",
                "audience_id": SEGMENT,
                "segment_id": SEGMENT,
                "from": "Example <news@example.org>",
                "subject": "October news",
                "reply_to": None,
                "preview_text": None,
                "html": "<p>October</p>",
                "text": "October",
                "status": "sent",
                "created_at": "2026-10-01 07:00:00.000+00",
                "scheduled_at": None,
                "sent_at": "2026-10-01 08:00:00.000+00",
                "topic_id": None,
            }
        }
        self.broadcasts_sent: list[str] = []
        self.requests = 0


SENT_LISTED = (
    "id message_id to from created_at subject bcc cc reply_to last_event scheduled_at".split()
)
BROADCAST_LISTED = "id name audience_id segment_id status created_at scheduled_at sent_at".split()


def page(items: list[Json], query: dict[str, str]) -> Json | None:
    """A page of `items` as the API pages: `limit` from 1 to 100, after the item `after`."""
    try:
        limit = int(query.get("limit", "20"))
    except ValueError:
        return None
    if not 1 <= limit <= 100:
        return None
    start = 0
    after = query.get("after")
    if after:
        found = [i for i, item in enumerate(items) if item["id"] == after]
        start = found[0] + 1 if found else len(items)
    chosen = items[start : start + limit]
    return {"object": "list", "has_more": start + limit < len(items), "data": chosen}


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, status: int, name: str, message: str) -> None:
            self.answer(status, {"statusCode": status, "message": message, "name": name})

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except ValueError:
                return None

        def admitted(self, sending: bool) -> bool:
            given = self.headers.get("Authorization", "")
            if not given:
                self.error(401, "missing_api_key", "Missing API key in the authorization header.")
                return False
            if given.startswith("Bearer ") and given[7:] in state.tokens:
                return True
            self.error(401 if sending else 400, "validation_error", "API key is invalid")
            return False

        def fake(self) -> bool:
            path = urlparse(self.path).path
            if path == "/_fake/state" and self.command == "GET":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "sent": [
                                {
                                    "id": e["id"],
                                    "to": e["to"],
                                    "subject": e["subject"],
                                    "tags": e["tags"],
                                    "headers": e["headers"],
                                }
                                for e in state.sent
                            ],
                            "broadcasts": {
                                b["id"]: {
                                    "status": b["status"],
                                    "name": b["name"],
                                    "subject": b["subject"],
                                    "segment": b["segment_id"],
                                    "from": b["from"],
                                }
                                for b in state.broadcasts.values()
                            },
                            "broadcasts_sent": list(state.broadcasts_sent),
                            "requests": state.requests,
                        },
                    )
                return True
            if path == "/_fake/reset" and self.command == "POST":
                with state.lock:
                    state.reset()
                self.answer(200, {"reset": True})
                return True
            return False

        def identifier(self, value: str) -> bool:
            if UUID.match(value) is None:
                self.error(422, "invalid_parameter", "The id must be a valid UUID.")
                return False
            return True

        def do_GET(self) -> None:
            if self.fake() or not self.admitted(sending=False):
                return
            url = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            parts = url.path.strip("/").split("/")
            with state.lock:
                state.requests += 1
                if parts == ["emails"]:
                    listed = [
                        {k: e.get(k) for k in SENT_LISTED} for e in reversed(state.sent)
                    ]  # fmt: skip
                    self.paged(listed, query)
                    return
                if len(parts) == 3 and parts[:2] == ["emails", "receiving"]:
                    if not self.identifier(parts[2]):
                        return
                    found = state.received.get(parts[2])
                    if found is None:
                        self.error(404, "not_found", "Email not found")
                        return
                    self.answer(200, found)
                    return
                if len(parts) == 2 and parts[0] == "emails":
                    if not self.identifier(parts[1]):
                        return
                    sent = [e for e in state.sent if e["id"] == parts[1]]
                    if not sent:
                        self.error(404, "not_found", "Email not found")
                        return
                    self.answer(200, {k: v for k, v in sent[0].items() if k != "headers"})
                    return
                if parts == ["broadcasts"]:
                    listed = [
                        {k: b.get(k) for k in BROADCAST_LISTED}
                        for b in reversed(list(state.broadcasts.values()))
                    ]
                    if "limit" not in query:
                        self.answer(200, {"object": "list", "has_more": False, "data": listed})
                        return
                    self.paged(listed, query)
                    return
                if len(parts) == 2 and parts[0] == "broadcasts":
                    if not self.identifier(parts[1]):
                        return
                    broadcast = state.broadcasts.get(parts[1])
                    if broadcast is None:
                        self.error(404, "not_found", "Broadcast not found")
                        return
                    self.answer(200, broadcast)
                    return
                if parts == ["contacts"]:
                    segment = query.get("segment_id", "")
                    contacts = state.segments.get(segment)
                    if contacts is None:
                        self.error(404, "not_found", "Segment not found")
                        return
                    self.paged(contacts, query)
                    return
            self.error(404, "not_found", "The requested endpoint does not exist.")

        def paged(self, items: list[Json], query: dict[str, str]) -> None:
            answered = page(items, query)
            if answered is None:
                self.error(422, "invalid_parameter", "limit must be between 1 and 100.")
                return
            self.answer(200, answered)

        def do_POST(self) -> None:
            if self.fake():
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            if not self.admitted(sending=parts == ["emails"]):
                return
            body = self.body()
            if not isinstance(body, dict):
                self.error(422, "validation_error", "The body is not JSON.")
                return
            with state.lock:
                state.requests += 1
                if parts == ["emails"]:
                    self.send_email(body)
                    return
                if parts == ["broadcasts"]:
                    self.create_broadcast(body)
                    return
                if len(parts) == 3 and parts[0] == "broadcasts" and parts[2] == "send":
                    if not self.identifier(parts[1]):
                        return
                    broadcast = state.broadcasts.get(parts[1])
                    if broadcast is None:
                        self.error(404, "not_found", "Broadcast not found")
                        return
                    if broadcast["status"] != "draft":
                        self.error(400, "validation_error", "The broadcast is not a draft.")
                        return
                    broadcast["status"] = "sent"
                    broadcast["sent_at"] = "2026-11-07 08:00:00.000+00"
                    state.broadcasts_sent.append(broadcast["id"])
                    self.answer(200, {"id": broadcast["id"]})
                    return
            self.error(404, "not_found", "The requested endpoint does not exist.")

        def verified(self, sender: Any) -> bool:
            found = ADDRESS.search(sender) if isinstance(sender, str) else None
            if found is None or found.group(1).lower() != DOMAIN:
                self.error(403, "validation_error", "The domain is not verified.")
                return False
            return True

        def send_email(self, body: Json) -> None:
            key = self.headers.get("Idempotency-Key")
            if key is not None and not 1 <= len(key) <= 256:
                self.error(400, "invalid_idempotency_key", "The key must be 1-256 characters.")
                return
            canonical = json.dumps(body, sort_keys=True)
            if key is not None and key in state.keys:
                original, digest = state.keys[key]
                if digest != canonical:
                    self.error(
                        409, "invalid_idempotent_request", "Same idempotency key used with a "
                        "different request payload.",
                    )  # fmt: skip
                    return
                self.answer(200, {"id": original})
                return
            to = body.get("to")
            to = [to] if isinstance(to, str) else to
            if not isinstance(to, list) or not 1 <= len(to) <= 50 or not body.get("subject"):
                self.error(422, "missing_required_field", "Missing `to` or `subject` field.")
                return
            if not self.verified(body.get("from")):
                return
            identifier = str(uuid.uuid4())
            state.sent.append(
                {
                    "object": "email",
                    "id": identifier,
                    "message_id": f"<{identifier}@{DOMAIN}>",
                    "to": list(to),
                    "from": body["from"],
                    "created_at": "2026-11-07 08:00:00.000000+00",
                    "subject": body["subject"],
                    "html": body.get("html"),
                    "text": body.get("text"),
                    "bcc": [],
                    "cc": [],
                    "reply_to": [],
                    "last_event": "sent",
                    "scheduled_at": None,
                    "tags": list(body.get("tags") or []),
                    "headers": dict(body.get("headers") or {}),
                }
            )
            if key is not None:
                state.keys[key] = (identifier, canonical)
            self.answer(200, {"id": identifier})

        def create_broadcast(self, body: Json) -> None:
            if not body.get("from") or not body.get("subject"):
                self.error(422, "missing_required_field", "Missing `from` or `subject` field.")
                return
            segment = body.get("segment_id")
            if segment not in state.segments:
                self.error(404, "not_found", "Segment not found")
                return
            if not self.verified(body.get("from")):
                return
            identifier = str(uuid.uuid4())
            state.broadcasts[identifier] = {
                "object": "broadcast",
                "id": identifier,
                "name": body.get("name"),
                "audience_id": segment,
                "segment_id": segment,
                "from": body["from"],
                "subject": body["subject"],
                "reply_to": body.get("reply_to"),
                "preview_text": body.get("preview_text"),
                "html": body.get("html"),
                "text": body.get("text"),
                "status": "draft",
                "created_at": "2026-11-07 07:00:00.000+00",
                "scheduled_at": None,
                "sent_at": None,
                "topic_id": body.get("topic_id"),
            }
            self.answer(200, {"object": "broadcast", "id": identifier})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9281)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake mail API at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
