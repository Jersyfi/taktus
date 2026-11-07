#!/usr/bin/env python3
"""A fake app store of the second kind: the reviews of the Google Play Developer API and its
token endpoint, in memory.

The store reviews connector under `connectors/taktus_connectors/googleplay/` exchanges a
service account's signed statement at `POST /token` and asks
`GET /androidpublisher/v3/applications/{packageName}/reviews`, `GET …/reviews/{reviewId}` and
`POST …/reviews/{reviewId}:reply`. This fake answers all four in the shapes the documentation
states — `reviews`, `tokenPagination.nextPageToken`, `comments` with a `userComment` and a
`developerComment`, `result.replyText` — with the API's statuses and its `error` object, so
that the connector can be exercised in CI without a network, an account or a key.

What it enforces, because the connector's checks depend on it:

- **The token endpoint.** A form with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`
  and an `assertion` signed RS256 by a key the fake was started with: `kid` the key's
  identifier, `iss` its account's address, `scope` the publishing scope, `aud` ending in
  `/token`, and `exp` at most an hour after `iat`. It answers `access_token`, `expires_in` and
  `token_type`; otherwise 400 `invalid_grant`. The keys are service account key files, JSON
  (`FAKE_TOKENS`, one file's text); `credential()` makes one.
- **The API.** Every request needs `Authorization: Bearer <access token>` the endpoint issued;
  otherwise 401 `UNAUTHENTICATED`. An unknown package or review is 404 `NOT_FOUND`. A reply
  without `replyText`, or one of more than 350 characters, is 400 `INVALID_ARGUMENT`. A second
  reply replaces the first, as the API does.
- **The list.** `maxResults` is a positive number; a next page is `tokenPagination
  .nextPageToken`, passed back as `token`. Only reviews with a text are served, as the API
  serves only those.

The reviews: the package `com.example.app` holds four, `gp:1` to `gp:4`, rated 1, 2, 5 and 1,
the third with a developer reply; each carries the author's name and a device, so that a test
can show the connector copies neither. Test-only: `POST /_fake/reviews` replaces them with a
JSON list of `{reviewId, rating, text, version, reply}`; `GET /_fake/state` counts the
requests, the tokens issued, and lists the replies written. Runnable as
`python tests/fakes/review_replies_service.py --port 9247`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PACKAGE = "com.example.app"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
PREFIX = f"/androidpublisher/v3/applications/{PACKAGE}/reviews"


def credential(email: str = "reviews@project.iam.gserviceaccount.com") -> str:
    """A fresh service account key file, in the shape the console hands it out."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "project",
            "private_key_id": secrets.token_hex(20),
            "private_key": pem,
            "client_email": email,
            "client_id": "1" + "0" * 20,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


def review(number: int, rating: int, reply: str | None = None) -> dict[str, Any]:
    return {
        "reviewId": f"gp:{number}",
        "rating": rating,
        "text": f"The export crashes after the update ({number}).",
        "version": f"2.{number}.0",
        "reply": reply,
    }


def default_reviews() -> list[dict[str, Any]]:
    return [review(1, 1), review(2, 2), review(3, 5, "Thank you!"), review(4, 1)]


def _resource(item: dict[str, Any]) -> dict[str, Any]:
    comments: list[dict[str, Any]] = [
        {
            "userComment": {
                "text": item["text"],
                "lastModified": {"seconds": "1793000000", "nanos": 0},
                "starRating": item["rating"],
                "reviewerLanguage": "de",
                "device": "device-1",
                "androidOsVersion": 34,
                "appVersionCode": 200,
                "appVersionName": item["version"],
                "thumbsUpCount": 0,
                "thumbsDownCount": 0,
                "deviceMetadata": {"productName": "phone", "manufacturer": "maker"},
            }
        }
    ]
    if item.get("reply") is not None:
        comments.append(
            {
                "developerComment": {
                    "text": item["reply"],
                    "lastModified": {"seconds": "1793000100", "nanos": 0},
                }
            }
        )
    return {"reviewId": item["reviewId"], "authorName": "A Person", "comments": comments}


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.keys: dict[str, tuple[str, Any]] = {}
        for value in tokens:
            key = json.loads(value)
            private = serialization.load_pem_private_key(key["private_key"].encode(), None)
            self.keys[key["private_key_id"]] = (key["client_email"], private.public_key())
        self.reviews = default_reviews()
        self.issued: set[str] = set()
        self.requests = 0
        self.written: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def grant(self, assertion: str) -> str | None:
        try:
            kid = jwt.get_unverified_header(assertion).get("kid")
            if kid not in self.keys:
                return None
            email, public = self.keys[kid]
            claims = jwt.decode(
                assertion,
                public,
                algorithms=["RS256"],
                issuer=email,
                options={"verify_aud": False, "require": ["iat", "exp", "aud", "iss", "scope"]},
            )
        except jwt.PyJWTError:
            return None
        if not str(claims["aud"]).endswith("/token") or SCOPE not in str(claims["scope"]).split():
            return None
        if int(claims["exp"]) - int(claims["iat"]) > 3600:
            return None
        issued = "ya29." + secrets.token_urlsafe(24)
        with self.lock:
            self.issued.add(issued)
        return issued


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

        def refuse(self, status: int, token: str) -> None:
            message = f"refused by the fake: {token}"
            self.answer(status, {"error": {"code": status, "message": message, "status": token}})

        def _admitted(self) -> bool:
            with state.lock:
                state.requests += 1
                issued = set(state.issued)
            auth = self.headers.get("Authorization") or ""
            if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ") not in issued:
                self.refuse(401, "UNAUTHENTICATED")
                return False
            return True

        def _found(self, wanted: str) -> dict[str, Any] | None:
            with state.lock:
                found = [r for r in state.reviews if r["reviewId"] == wanted]
            return found[0] if found else None

        def do_POST(self) -> None:
            url = urlparse(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if url.path == "/_fake/reviews":
                with state.lock:
                    state.reviews = json.loads(body)
                self.answer(200, {"ok": True})
                return
            if url.path == "/token":
                form = parse_qs(body.decode())
                assertion = form.get("assertion", [""])[0]
                issued = (
                    state.grant(assertion) if form.get("grant_type", [""])[0] == GRANT else None
                )
                if issued is None:
                    self.answer(
                        400,
                        {"error": "invalid_grant", "error_description": "refused by the fake"},
                    )
                    return
                self.answer(
                    200, {"access_token": issued, "expires_in": 3599, "token_type": "Bearer"}
                )
                return
            if not self._admitted():
                return
            if not (url.path.startswith(PREFIX + "/") and url.path.endswith(":reply")):
                self.refuse(404, "NOT_FOUND")
                return
            found = self._found(url.path.removeprefix(PREFIX + "/").removesuffix(":reply"))
            if found is None:
                self.refuse(404, "NOT_FOUND")
                return
            try:
                text = json.loads(body)["replyText"]
                assert isinstance(text, str) and text and len(text) <= 350
            except (ValueError, KeyError, TypeError, AssertionError):
                self.refuse(400, "INVALID_ARGUMENT")
                return
            with state.lock:
                found["reply"] = text
                state.written.append({"review": found["reviewId"], "text": text})
            self.answer(
                200,
                {
                    "result": {
                        "replyText": text,
                        "lastEdited": {"seconds": "1793000200", "nanos": 0},
                    }
                },
            )

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "requests": state.requests,
                            "tokens": len(state.issued),
                            "written": state.written,
                        },
                    )
                return
            if not self._admitted():
                return
            if url.path == PREFIX:
                self._list(parse_qs(url.query))
            elif url.path.startswith(PREFIX + "/"):
                found = self._found(url.path.removeprefix(PREFIX + "/"))
                if found is None:
                    self.refuse(404, "NOT_FOUND")
                else:
                    self.answer(200, _resource(found))
            else:
                self.refuse(404, "NOT_FOUND")

        def _list(self, query: dict[str, list[str]]) -> None:
            try:
                size = int(query.get("maxResults", ["10"])[0])
                offset = int(query.get("token", ["0"])[0])
            except ValueError:
                size, offset = 0, -1
            if size < 1 or offset < 0:
                self.refuse(400, "INVALID_ARGUMENT")
                return
            with state.lock:
                every = [r for r in state.reviews if r.get("text")]
            page = every[offset : offset + size]
            document: dict[str, Any] = {
                "reviews": [_resource(r) for r in page],
                "pageInfo": {
                    "totalResults": len(every),
                    "resultPerPage": size,
                    "startIndex": offset,
                },
            }
            if offset + size < len(every):
                document["tokenPagination"] = {"nextPageToken": str(offset + size)}
            self.answer(200, document)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9247)
    args = parser.parse_args()
    given = os.environ.get("FAKE_TOKENS", "")
    server = make_server(args.host, args.port, {given} if given else set())
    sys.stderr.write(f"fake app store at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
