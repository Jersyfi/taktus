#!/usr/bin/env python3
"""A fake of the chat service the chat connector talks to.

The connector under `src/taktus/adapters/driven/connectors/slack/` speaks the web interface of
that service. This fake answers the four methods the connector uses — `chat.postMessage`,
`conversations.replies`, `conversations.history`, `users.list` — in the same shapes, with the
same error codes for the same faults, and keeps everything in memory. It exists so that the
connector can be exercised in CI without a network, an account or a secret: the conformance
gate starts it as a process, the adapter tests start it in a thread.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_CHAT_TOKENS`, `value:scope,...`; scope `read` or `write`). No value:
  `not_authed`; an unknown one: `invalid_auth`. A `read` scope posting: `missing_scope`. As the
  service does, every such answer is status 200 with `{"ok": false, "error": …}`.
- **Conversations that exist.** `C0000000001` and `D0000000001` exist from the start, each with
  one message, `1700000000.000100`, that a thread can hang from. Any other conversation is
  `channel_not_found` until `POST /_fake/conversations` with `{"id": …}` makes it; a thread
  whose first message does not exist is `thread_not_found`.
- **Metadata.** A posted message keeps the `metadata` it was posted with, and a read returns it
  only when asked with `include_all_metadata=true`, as the service does.
- **Paging.** `conversations.replies` and `conversations.history` page by `limit` and `cursor`,
  with `has_more` and `response_metadata.next_cursor`; `users.list` by the same two, with
  `response_metadata.next_cursor` alone, as the service does.
- **The member list and its two permissions.** `users.list` needs the app's `users:read`; without
  it the answer is `missing_scope`. A member's `profile.email` is there only with
  `users:read.email`, and `is_email_confirmed` says whether the service confirmed it. Four members
  exist from the start: a person with a confirmed address, a person whose address is not
  confirmed, a deactivated person, and the app's own bot user.

Test-only endpoints under `/_fake/`: `GET /_fake/state` counts the messages of every
conversation, `GET /_fake/messages?channel=…` lists them with their thread, `POST /_fake/reset`
empties the store back to its seed, `POST /_fake/conversations` adds one, `POST /_fake/members`
with a member object adds a member, `POST /_fake/scopes` with `{"users:read": …,
"users:read.email": …}` grants or withdraws either permission, `POST /_fake/messages`
with `{"channel": …, "ts": …, "user": …, "text": …}` (and `thread_ts` for a reply) puts in a
message a person wrote, `POST /_fake/outage`
with `{"on": true}` makes every other request answer 503 until switched off. Standard library
only; runnable as `python3 tests/fakes/chat_service.py --port 9201`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

TOKENS_VARIABLE = "FAKE_CHAT_TOKENS"
SEEDED = ("C0000000001", "D0000000001")
SEED_TS = "1700000000.000100"
SEED_USER = "U0000000001"
BOT_USER = "U0000000BOT"
BOT_ID = "B0000000BOT"
APP_ID = "A0000000APP"
MAX_LIMIT = 1000
MEMBER_SCOPES = ("users:read", "users:read.email")


def seed_members() -> list[Json]:
    """The workspace's members at the start, in the shape the service answers them."""

    def person(account: str, name: str, email: str, *, confirmed: bool, deleted: bool) -> Json:
        return {
            "id": account,
            "team_id": "T0000000001",
            "name": name.lower(),
            "deleted": deleted,
            "is_bot": False,
            "is_email_confirmed": confirmed,
            "profile": {"real_name": name, "display_name": name, "email": email},
        }

    return [
        person(SEED_USER, "Ada", "ada@example.org", confirmed=True, deleted=False),
        person("U0000000002", "Ben", "ben@example.org", confirmed=False, deleted=False),
        person("U0000000003", "Cleo", "cleo@example.org", confirmed=True, deleted=True),
        {
            "id": BOT_USER,
            "team_id": "T0000000001",
            "name": "taktus",
            "deleted": False,
            "is_bot": True,
            "profile": {"real_name": "Taktus", "display_name": "Taktus", "bot_id": BOT_ID},
        },
    ]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Store:
    tokens: dict[str, str]  # value -> scope
    conversations: dict[str, list[Json]] = field(default_factory=dict)
    members: list[Json] = field(default_factory=list)
    granted: set[str] = field(default_factory=set)
    sequence: int = 1
    outage: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.conversations = {}
        self.members = seed_members()
        self.granted = set(MEMBER_SCOPES)
        self.sequence = 1
        for conversation in SEEDED:
            self.conversations[conversation] = [
                {"type": "message", "user": SEED_USER, "text": "The first message.", "ts": SEED_TS}
            ]

    def next_ts(self) -> str:
        self.sequence += 1
        return f"1700000001.{self.sequence:06d}"

    def state(self) -> Json:
        return {name: len(messages) for name, messages in self.conversations.items()}


def visible(message: Json, metadata: bool) -> Json:
    shown = {k: v for k, v in message.items() if k != "metadata"}
    if metadata and "metadata" in message:
        shown["metadata"] = message["metadata"]
    return shown


def page_of(items: list[Json], query: Json, key: str = "messages") -> Json:
    try:
        limit = max(1, min(int(query.get("limit", "100")), MAX_LIMIT))
        start = int(query.get("cursor") or "0")
    except ValueError:
        return {"ok": False, "error": "invalid_cursor"}
    chunk = items[start : start + limit]
    more = start + limit < len(items)
    return {
        "ok": True,
        key: chunk,
        "has_more": more,
        "response_metadata": {"next_cursor": str(start + limit) if more else ""},
    }


class Handler(BaseHTTPRequestHandler):
    store: Store
    server_version = "fake-chat/1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{now()} fake-chat {format % args}\n")

    def _send(self, status: int, body: Json) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _scope(self) -> tuple[str | None, str | None]:
        """The token's scope, or the error code the service answers with."""
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or not header[7:].strip():
            return None, "not_authed"
        scope = self.store.tokens.get(header[7:].strip())
        if scope is None:
            return None, "invalid_auth"
        return scope, None

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        store = self.store
        if url.path == "/_fake/state":
            with store.lock:
                self._send(200, store.state())
            return
        if url.path == "/_fake/messages":
            with store.lock:
                messages = store.conversations.get(query.get("channel", ""), [])
                self._send(200, {"messages": [dict(m) for m in messages]})
            return
        self._method(url.path.lstrip("/"), query)

    def do_POST(self) -> None:
        url = urlparse(self.path)
        body = self._body()
        store = self.store
        if url.path.startswith("/_fake/"):
            with store.lock:
                if url.path == "/_fake/reset":
                    store.reset()
                    store.outage = False
                elif url.path == "/_fake/outage":
                    store.outage = bool(body.get("on"))
                elif url.path == "/_fake/conversations":
                    store.conversations.setdefault(str(body.get("id", "")), [])
                elif url.path == "/_fake/members":
                    store.members.append(body)
                elif url.path == "/_fake/scopes":
                    for scope in MEMBER_SCOPES:
                        if scope in body:
                            if body[scope]:
                                store.granted.add(scope)
                            else:
                                store.granted.discard(scope)
                elif url.path == "/_fake/messages":
                    # A message a person wrote, as the service would hold it.
                    conversation = store.conversations.setdefault(str(body.pop("channel")), [])
                    conversation.append({"type": "message", **body})
                else:
                    self._send(404, {"ok": False, "error": "unknown_method"})
                    return
            self._send(200, {"ok": True})
            return
        self._method(url.path.lstrip("/"), body)

    def _method(self, method: str, args: Json) -> None:
        store = self.store
        if store.outage:
            self._send(503, {"ok": False, "error": "service_unavailable"})
            return
        scope, refusal = self._scope()
        if refusal is not None:
            self._send(200, {"ok": False, "error": refusal})
            return
        with store.lock:
            if method == "chat.postMessage":
                self._send(200, self._post(scope, args))
            elif method == "conversations.replies":
                self._send(200, self._replies(args))
            elif method == "conversations.history":
                self._send(200, self._history(args))
            elif method == "users.list":
                self._send(200, self._users(args))
            else:
                self._send(404, {"ok": False, "error": "unknown_method"})

    def _post(self, scope: str | None, args: Json) -> Json:
        store = self.store
        if scope != "write":
            return {"ok": False, "error": "missing_scope"}
        conversation = str(args.get("channel", ""))
        messages = store.conversations.get(conversation)
        if messages is None:
            return {"ok": False, "error": "channel_not_found"}
        text = args.get("text")
        if not isinstance(text, str) or not text:
            return {"ok": False, "error": "no_text"}
        message: Json = {
            "type": "message",
            "user": BOT_USER,
            "bot_id": BOT_ID,
            "app_id": APP_ID,
            "text": text,
            "ts": store.next_ts(),
        }
        thread = args.get("thread_ts")
        if thread is not None:
            if not any(m["ts"] == thread for m in messages):
                return {"ok": False, "error": "thread_not_found"}
            message["thread_ts"] = str(thread)
        metadata = args.get("metadata")
        if metadata is not None:
            if not isinstance(metadata, dict) or not metadata.get("event_type"):
                return {"ok": False, "error": "invalid_metadata_format"}
            message["metadata"] = metadata
        messages.append(message)
        return {
            "ok": True,
            "channel": conversation,
            "ts": message["ts"],
            "message": visible(message, False),
        }

    def _replies(self, args: Json) -> Json:
        conversation = str(args.get("channel", ""))
        messages = self.store.conversations.get(conversation)
        if messages is None:
            return {"ok": False, "error": "channel_not_found"}
        thread = str(args.get("ts", ""))
        parent = next((m for m in messages if m["ts"] == thread and "thread_ts" not in m), None)
        if parent is None:
            return {"ok": False, "error": "thread_not_found"}
        metadata = str(args.get("include_all_metadata", "")).lower() == "true"
        replies = [m for m in messages if m.get("thread_ts") == thread]
        ordered = [parent, *sorted(replies, key=lambda m: m["ts"])]
        return page_of([visible(m, metadata) for m in ordered], args)

    def _history(self, args: Json) -> Json:
        conversation = str(args.get("channel", ""))
        messages = self.store.conversations.get(conversation)
        if messages is None:
            return {"ok": False, "error": "channel_not_found"}
        metadata = str(args.get("include_all_metadata", "")).lower() == "true"
        top = sorted((m for m in messages if "thread_ts" not in m), key=lambda m: m["ts"])
        return page_of([visible(m, metadata) for m in reversed(top)], args)

    def _users(self, args: Json) -> Json:
        store = self.store
        if "users:read" not in store.granted:
            return {"ok": False, "error": "missing_scope", "needed": "users:read"}
        email = "users:read.email" in store.granted
        shown = []
        for member in store.members:
            copy = json.loads(json.dumps(member))
            if not email:
                copy.get("profile", {}).pop("email", None)
            shown.append(copy)
        page = page_of(shown, args, key="members")
        page.pop("has_more", None)
        return page


def tokens_from_environment() -> dict[str, str]:
    raw = os.environ.get(TOKENS_VARIABLE, "")
    tokens: dict[str, str] = {}
    for entry in filter(None, raw.split(",")):
        value, _, scope = entry.partition(":")
        tokens[value] = scope or "write"
    return tokens


def make_server(host: str, port: int, tokens: dict[str, str]) -> ThreadingHTTPServer:
    store = Store(tokens=tokens)

    class Bound(Handler):
        pass

    Bound.store = store
    return ThreadingHTTPServer((host, port), Bound)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake chat service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9201)
    args = parser.parse_args(argv)
    tokens = tokens_from_environment()
    if not tokens:
        sys.stderr.write(f"{TOKENS_VARIABLE} is empty: no request will authenticate\n")
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"{now()} fake-chat listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
