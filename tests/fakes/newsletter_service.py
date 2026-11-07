#!/usr/bin/env python3
"""A fake newsletter service: the part of the Mailchimp Marketing API 3.0 the newsletter
connector uses, in memory.

The connector under `connectors/taktus_connectors/mailchimp/` asks, under `/3.0/`:

- `GET campaigns?list_id=&count=&offset=&fields=`: `{"campaigns": [...], "total_items": n}`,
  the account's campaigns, filtered by audience, a page of `count` from `offset`;
- `GET campaigns/<id>`: one campaign, 404 for one the account does not hold;
- `POST campaigns`: a campaign created with `type`, `recipients.list_id` and `settings`, status
  `save`, 200; 400 for a type other than `regular` or an audience the account does not hold;
- `PUT campaigns/<id>/content`: `html` and `plain_text` set, 200;
- `POST campaigns/<id>/actions/send`: 204, and the campaign's status becomes `sent`; 400 with
  the title `Bad Request` for a campaign without content, a reply address or a subject, as the
  API answers a campaign not ready to send; 405 for one that is not a draft.

What it enforces, because the connector's checks depend on it:

- **Authentication.** HTTP Basic, any user name, the API key as the password, a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401 with the API's error body
  (`type`, `title`, `status`, `detail`, `instance`).
- **The audience.** `list-1` holds 1200 members; a campaign to it reports that number as
  `recipients.recipient_count`. No member's address is served anywhere.

It starts with one campaign, `c-seeded`, already sent to `list-1`. Test-only: `GET /_fake/state`
names every campaign with its status, title, subject and audience, and the campaigns sent, in
order; `POST /_fake/reset` restores the start. Standard library only; runnable as
`python3 tests/fakes/newsletter_service.py --port 9235`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

LISTS = {"list-1": 1200}


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.campaigns: dict[str, Json] = {
            "c-seeded": {
                "id": "c-seeded",
                "web_id": 1,
                "type": "regular",
                "status": "sent",
                "emails_sent": 1200,
                "send_time": "2026-10-01T08:00:00+00:00",
                "recipients": {"list_id": "list-1", "recipient_count": 1200},
                "settings": {
                    "subject_line": "October news",
                    "title": "October",
                    "from_name": "Example",
                    "reply_to": "news@example.org",
                },
                "content": {"html": "<p>October</p>", "plain_text": "October"},
            }
        }
        self.sent: list[str] = []
        self.requests = 0


def public(campaign: Json) -> Json:
    return {k: v for k, v in campaign.items() if k != "content"}


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def answer(self, status: int, body: Any = None) -> None:
            data = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, status: int, title: str, detail: str) -> None:
            self.answer(
                status,
                {
                    "type": "https://mailchimp.com/developer/marketing/docs/errors/",
                    "title": title,
                    "status": status,
                    "detail": detail,
                    "instance": str(uuid.uuid4()),
                },
            )

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            try:
                return json.loads(self.rfile.read(length))
            except ValueError:
                return None

        def admitted(self) -> bool:
            given = self.headers.get("Authorization", "")
            if given.startswith("Basic "):
                try:
                    _, _, key = base64.b64decode(given[6:]).decode().partition(":")
                except ValueError:
                    key = ""
                if key in state.tokens:
                    return True
            self.error(401, "API Key Invalid", "Your API key may be invalid, or you've attempted "
                       "to access the wrong datacenter.")  # fmt: skip
            return False

        def fake(self) -> bool:
            path = urlparse(self.path).path
            if path == "/_fake/state" and self.command == "GET":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "campaigns": {
                                c["id"]: {
                                    "status": c["status"],
                                    "title": c["settings"].get("title"),
                                    "subject": c["settings"].get("subject_line"),
                                    "list": c["recipients"]["list_id"],
                                }
                                for c in state.campaigns.values()
                            },
                            "sent": list(state.sent),
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

        def do_GET(self) -> None:
            if self.fake() or not self.admitted():
                return
            url = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(url.query).items()}
            parts = url.path.strip("/").split("/")
            with state.lock:
                state.requests += 1
                if parts == ["3.0", "campaigns"]:
                    count = min(int(query.get("count", "10")), 1000)
                    offset = int(query.get("offset", "0"))
                    found = [
                        public(c)
                        for c in state.campaigns.values()
                        if "list_id" not in query or c["recipients"]["list_id"] == query["list_id"]
                    ]
                    self.answer(
                        200,
                        {"campaigns": found[offset : offset + count], "total_items": len(found)},
                    )
                    return
                if len(parts) == 3 and parts[:2] == ["3.0", "campaigns"]:
                    campaign = state.campaigns.get(parts[2])
                    if campaign is None:
                        self.error(404, "Resource Not Found", "The requested resource could "
                                   "not be found.")  # fmt: skip
                        return
                    self.answer(200, public(campaign))
                    return
            self.error(404, "Resource Not Found", "The requested resource could not be found.")

        def do_PUT(self) -> None:
            if self.fake() or not self.admitted():
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            body = self.body()
            with state.lock:
                state.requests += 1
                if len(parts) == 4 and parts[:2] == ["3.0", "campaigns"] and parts[3] == "content":
                    campaign = state.campaigns.get(parts[2])
                    if campaign is None:
                        self.error(404, "Resource Not Found", "No such campaign.")
                        return
                    if not isinstance(body, dict):
                        self.error(400, "JSON Parse Exception", "The body is not JSON.")
                        return
                    campaign["content"] = {
                        "html": body.get("html"),
                        "plain_text": body.get("plain_text"),
                    }
                    self.answer(200, campaign["content"])
                    return
            self.error(404, "Resource Not Found", "The requested resource could not be found.")

        def do_POST(self) -> None:
            if self.fake() or not self.admitted():
                return
            parts = urlparse(self.path).path.strip("/").split("/")
            body = self.body()
            with state.lock:
                state.requests += 1
                if parts == ["3.0", "campaigns"]:
                    if not isinstance(body, dict) or body.get("type") != "regular":
                        self.error(400, "Invalid Resource", "The resource submitted could not "
                                   "be validated.")  # fmt: skip
                        return
                    audience = (body.get("recipients") or {}).get("list_id")
                    if audience not in LISTS:
                        self.error(400, "Invalid Resource", "Invalid list ID.")
                        return
                    identifier = uuid.uuid4().hex[:10]
                    campaign = {
                        "id": identifier,
                        "web_id": len(state.campaigns) + 1,
                        "type": "regular",
                        "status": "save",
                        "emails_sent": 0,
                        "send_time": "",
                        "recipients": {"list_id": audience, "recipient_count": LISTS[audience]},
                        "settings": dict(body.get("settings") or {}),
                        "content": {},
                    }
                    state.campaigns[identifier] = campaign
                    self.answer(200, public(campaign))
                    return
                if (
                    len(parts) == 5
                    and parts[:2] == ["3.0", "campaigns"]
                    and parts[3:] == ["actions", "send"]
                ):
                    campaign = state.campaigns.get(parts[2])
                    if campaign is None:
                        self.error(404, "Resource Not Found", "No such campaign.")
                        return
                    if campaign["status"] != "save":
                        self.error(405, "Method Not Allowed", "The campaign is not a draft.")
                        return
                    settings = campaign["settings"]
                    if not (
                        campaign["content"].get("html")
                        and settings.get("subject_line")
                        and settings.get("reply_to")
                    ):
                        self.error(400, "Bad Request", "Your Campaign is not ready to send.")
                        return
                    campaign["status"] = "sent"
                    campaign["emails_sent"] = campaign["recipients"]["recipient_count"]
                    campaign["send_time"] = "2026-11-07T08:00:00+00:00"
                    state.sent.append(campaign["id"])
                    self.answer(204)
                    return
            self.error(404, "Resource Not Found", "The requested resource could not be found.")

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9235)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake newsletter service at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
