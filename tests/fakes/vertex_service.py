"""A stand-in for Vertex AI's `generateContent` and Google's OAuth 2.0 token endpoint, from their
published interfaces (`src/taktus/adapters/driven/models/README.md`).

`POST /token` takes the JWT bearer grant (RFC 7523): `grant_type` and `assertion`, an RS256 JWT
whose signature it verifies with the public key it was given, whose `aud` is this endpoint and
whose `scope` is `cloud-platform`; it answers `access_token`, `expires_in` and `token_type`.
`POST /v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent`
needs `Authorization: Bearer <that token>` and answers `candidates`, `usageMetadata` and
`modelVersion` in the shape of the service's discovery document. `answer`, `finish`, `cached`,
`thoughts` and `status` script it; `requests` keeps every body, `tokens` every token issued.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

import jwt

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
PATH = re.compile(
    r"^/v1/projects/[^/]+/locations/(?P<region>[^/]+)/publishers/google/models/"
    r"(?P<model>[^/:]+):generateContent$"
)


@dataclass
class Script:
    public_key: Any
    token_uri: str = ""
    answer: str = "Gern geschehen."
    finish: str = "STOP"
    cached: int = 0
    thoughts: int = 0
    status: int = 200
    requests: list[dict[str, Any]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class Handler(BaseHTTPRequestHandler):
    script: Script
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _raw(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:
        raw = self._raw()
        if self.path == "/token":
            form = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
            if form.get("grant_type") != "urn:ietf:params:oauth:grant-type:jwt-bearer":
                self._send(400, {"error": "unsupported_grant_type"})
                return
            try:
                claims = jwt.decode(
                    form.get("assertion", ""),
                    self.script.public_key,
                    algorithms=["RS256"],
                    audience=self.script.token_uri,
                )
            except jwt.PyJWTError:
                self._send(400, {"error": "invalid_grant"})
                return
            if claims.get("scope") != SCOPE:
                self._send(400, {"error": "invalid_scope"})
                return
            with self.script.lock:
                token = f"ya29.fake-{len(self.script.tokens) + 1}"
                self.script.tokens.append(token)
            self._send(200, {"access_token": token, "expires_in": 3599, "token_type": "Bearer"})
            return
        matched = PATH.match(self.path)
        if matched is None:
            self._send(404, {"error": {"code": 404, "message": "Not Found"}})
            return
        given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if given not in self.script.tokens:
            self._send(401, {"error": {"code": 401, "message": "Request had invalid credentials"}})
            return
        body = json.loads(raw or b"{}")
        with self.script.lock:
            self.script.requests.append(body)
            self.script.paths.append(self.path)
        if self.script.status != 200:
            self._send(self.script.status, {"error": {"code": self.script.status, "message": "x"}})
            return
        text = " ".join(p.get("text", "") for c in body.get("contents", []) for p in c["parts"])
        prompt = len(text.split()) + self.script.cached
        limit = body.get("generationConfig", {}).get("maxOutputTokens")
        words = self.script.answer.split()
        finish = self.script.finish
        if isinstance(limit, int) and len(words) > limit:
            words, finish = words[:limit], "MAX_TOKENS"
        usage: dict[str, Any] = {
            "promptTokenCount": prompt,
            "candidatesTokenCount": len(words),
            "totalTokenCount": prompt + len(words) + self.script.thoughts,
        }
        if self.script.cached:
            usage["cachedContentTokenCount"] = self.script.cached
        if self.script.thoughts:
            usage["thoughtsTokenCount"] = self.script.thoughts
        self._send(
            200,
            {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": " ".join(words)}]},
                        "finishReason": finish,
                    }
                ],
                "usageMetadata": usage,
                "modelVersion": matched["model"] + "-001",
                "responseId": "fake",
            },
        )


def make_server(public_key: Any) -> tuple[ThreadingHTTPServer, Script]:
    script = Script(public_key=public_key)
    handler = type("BoundHandler", (Handler,), {"script": script})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    script.token_uri = f"http://127.0.0.1:{server.server_address[1]}/token"
    return server, script
