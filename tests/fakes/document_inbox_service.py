#!/usr/bin/env python3
"""A fake document inbox: one folder served over WebDAV (RFC 4918), in memory.

The documents connector under `connectors/taktus_connectors/einvoice/` asks `PROPFIND` on the
folder with `Depth: 1` and `GET` on a document in it. This fake answers both, with WebDAV's
statuses for its errors, over documents it holds in memory. It exists so that the connector can
be exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request to the folder needs `Authorization: Bearer <value>` with a
  value the fake was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **The folder.** The folder is the root, `/`, so that the fake's address is the folder's. A
  `PROPFIND` needs `Depth: 1`, anything else is 400; it answers `207 Multi-Status` with the
  folder and each document. A `GET` of a document the folder does not hold is 404, and a path
  outside the folder is 403.

The documents: the files under `tests/fakes/documents/`, unless a test added one with
`POST /_fake/documents?name=<name>` and the bytes as the body. Test-only: `GET /_fake/state`
counts the requests and names the bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/document_inbox_service.py --port 9213`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from xml.sax.saxutils import escape

FOLDER = "/"
DOCUMENTS = Path(__file__).resolve().parent / "documents"


def default_documents() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(DOCUMENTS.glob("*.xml"))}


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.documents = default_documents()
        self.modified = {name: 1_790_000_000 + i for i, name in enumerate(self.documents)}
        self.requests = 0
        self.seen: set[str] = set()
        self.lock = threading.Lock()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: bytes, kind: str = "application/xml") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def admitted(self) -> bool:
            header = self.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else None
            with state.lock:
                state.requests += 1
                if token:
                    state.seen.add(token)
            if token is None or token not in state.tokens:
                self.answer(401, b"", "text/plain")
                return False
            return True

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path != "/_fake/documents":
                self.answer(404, b"", "text/plain")
                return
            name = parse_qs(url.query).get("name", [""])[0]
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with state.lock:
                state.documents[name] = body
                state.modified[name] = 1_790_000_000 + len(state.modified)
            self.answer(204, b"", "text/plain")

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    body = {"requests": state.requests, "tokens": sorted(state.seen)}
                self.answer(200, json.dumps(body).encode(), "application/json")
                return
            if not self.admitted():
                return
            path = unquote(url.path)
            if not path.startswith(FOLDER) or "/" in path[len(FOLDER) :]:
                self.answer(403, b"", "text/plain")
                return
            content = state.documents.get(path[len(FOLDER) :])
            if content is None:
                self.answer(404, b"", "text/plain")
                return
            self.answer(200, content)

        def do_PROPFIND(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not self.admitted():
                return
            if unquote(urlparse(self.path).path) != FOLDER:
                self.answer(404, b"", "text/plain")
                return
            if self.headers.get("Depth") != "1":
                self.answer(400, b"", "text/plain")
                return
            with state.lock:
                documents = dict(state.documents)
                modified = dict(state.modified)
            parts = [
                "<d:response><d:href>/</d:href><d:propstat><d:prop>"
                "<d:resourcetype><d:collection/></d:resourcetype></d:prop>"
                "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
            ]
            for name, content in documents.items():
                etag = hashlib.sha256(content).hexdigest()[:16]
                parts.append(
                    f"<d:response><d:href>{escape(FOLDER + quote(name))}</d:href><d:propstat>"
                    f"<d:prop><d:getcontentlength>{len(content)}</d:getcontentlength>"
                    f"<d:getlastmodified>{formatdate(modified[name], usegmt=True)}"
                    f'</d:getlastmodified><d:getetag>"{etag}"</d:getetag><d:resourcetype/>'
                    "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                )
            body = (
                '<?xml version="1.0" encoding="utf-8"?><d:multistatus xmlns:d="DAV:">'
                + "".join(parts)
                + "</d:multistatus>"
            )
            self.answer(207, body.encode("utf-8"))

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9213)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake document inbox at http://{args.host}:{args.port}{FOLDER}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
