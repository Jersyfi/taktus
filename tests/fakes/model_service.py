#!/usr/bin/env python3
"""A fake of a chat-completions endpoint, for the model adapter and the gate.

It answers `POST /chat/completions` in the shape the adapter reads — the first choice's
message, the usage, the finish reason — and nothing a real endpoint would not. What it answers
with is scripted: `FAKE_MODEL_ANSWER` (or the `answer` given to `make_server`) is the text of
every completion, with `{prompt}` replaced by the user message, so that a test can see the
prompt came through. Tokens are counted as words. `FAKE_MODEL_TOKEN`, when set, is the one
bearer value accepted; anything else is 401. `POST /_fake/answer` changes the answer and the
finish reason for the calls that follow. Standard library only; runnable as
`python3 tests/fakes/model_service.py --port 9300`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

type Json = dict[str, Any]

DEFAULT_ANSWER = "## Acceptance criteria\n\n- [ ] the fake answered: {prompt}\n"


@dataclass
class Script:
    answer: str = DEFAULT_ANSWER
    finish: str = "stop"
    token: str | None = None
    status: int = 200
    requests: list[Json] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Handler(BaseHTTPRequestHandler):
    script: Script
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"fake-model {format % args}\n")

    def _send(self, status: int, body: Json) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> Json:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        parsed = json.loads(raw) if raw else {}
        return parsed if isinstance(parsed, dict) else {}

    def do_POST(self) -> None:
        body = self._body()
        if self.path == "/_fake/answer":
            with self.script.lock:
                self.script.answer = str(body.get("answer", self.script.answer))
                self.script.finish = str(body.get("finish", self.script.finish))
                self.script.status = int(body.get("status", 200))
            self._send(200, {"ok": True})
            return
        if self.path != "/chat/completions":
            self._send(404, {"error": {"message": "Not Found"}})
            return
        if self.script.token is not None:
            given = self.headers.get("Authorization") or ""
            if given != f"Bearer {self.script.token}":
                self._send(401, {"error": {"message": "Incorrect API key provided"}})
                return
        with self.script.lock:
            self.script.requests.append(body)
            if self.script.status != 200:
                self._send(self.script.status, {"error": {"message": "scripted failure"}})
                return
            messages = body.get("messages") or []
            user = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
            )
            text = self.script.answer.replace("{prompt}", str(user))
            finish = self.script.finish
        prompt_tokens = sum(len(str(m.get("content", "")).split()) for m in messages)
        self._send(
            200,
            {
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "model": str(body.get("model") or "fake-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": finish,
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": len(text.split()),
                    "total_tokens": prompt_tokens + len(text.split()),
                },
            },
        )


def make_server(
    host: str, port: int, *, answer: str = DEFAULT_ANSWER, token: str | None = None
) -> tuple[ThreadingHTTPServer, Script]:
    script = Script(answer=answer, token=token)

    class Bound(Handler):
        pass

    Bound.script = script
    return ThreadingHTTPServer((host, port), Bound), script


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake chat-completions endpoint.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9300)
    args = parser.parse_args(argv)
    server, _ = make_server(
        args.host,
        args.port,
        answer=os.environ.get("FAKE_MODEL_ANSWER", DEFAULT_ANSWER),
        token=os.environ.get("FAKE_MODEL_TOKEN") or None,
    )
    sys.stderr.write(f"fake-model listening on {server.server_address}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
