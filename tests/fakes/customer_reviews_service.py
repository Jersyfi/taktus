#!/usr/bin/env python3
"""A fake app store: the customer reviews of the App Store Connect API, in memory.

The app stores connector under `connectors/taktus_connectors/appstores/` asks, for its
`stores.reviews` on `ios`,
`GET /v1/apps/{id}/customerReviews`, `GET /v1/customerReviews/{id}` and
`POST /v1/customerReviewResponses`. This fake answers all three in the API's JSON:API shapes —
`data`, `included`, `links.next`, `meta.paging` — with the API's statuses and its `errors`
array, over reviews it holds in memory, so that the connector can be exercised in CI without a
network, an account or a key.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <JSON Web Token>`, signed
  ES256 with a key the fake was started with, carrying that key's identifier as `kid`, its
  issuer as `iss`, the audience `appstoreconnect-v1`, and an `exp` at most twenty minutes after
  `iat`. Otherwise 401 `NOT_AUTHORIZED`. The key is the connector's credential `STORES_KEY`,
  its `ios` member `{issuer_id, key_id, private_key}` (`FAKE_TOKENS`, one value);
  `credential()` makes one.
- **The list.** `limit` is 1 to 200; `sort` one of `rating`, `-rating`, `createdDate`,
  `-createdDate`; `filter[rating]` a comma-separated list of 1 to 5; `include` `response`.
  Anything else is 400 `PARAMETER_ERROR.INVALID`. A next page is `links.next`, a full URL with a
  `cursor`. An unknown app is 404 `NOT_FOUND`.
- **One review.** An unknown identifier is 404.
- **A response.** One per review; a POST creates it, or replaces it by overwriting, as the API
  does, in the state `PENDING_PUBLISH`. A body not in the request's shape is 409
  `ENTITY_ERROR`, a review it does not know 404.

The reviews: the app `1234567890` holds four, `rev-1` to `rev-4`, rated 1, 2, 5 and 1, the
third with a published response; every review carries a reviewer nickname, so that a test can
show the connector never copies it. Test-only: `POST /_fake/reviews` replaces them with a JSON
list of `{id, rating, title, body, territory, createdDate, response}`; `GET /_fake/state` counts
the requests and lists the responses written. Runnable as
`python tests/fakes/customer_reviews_service.py --port 9246`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

APP = "1234567890"
AUDIENCE = "appstoreconnect-v1"
SORTS = {"rating", "-rating", "createdDate", "-createdDate"}


def credential(issuer: str = "57246542-96fe-1a63-e053-0824d011072a", key_id: str = "") -> str:
    """A fresh key in the connector's form: `STORES_KEY` with the key as its `ios` member."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_id = key_id or base64.b32encode(os.urandom(5)).decode()
    member = {"issuer_id": issuer, "key_id": key_id, "private_key": pem.decode()}
    return json.dumps({"ios": member})


def review(number: int, rating: int, response: str | None = None) -> dict[str, Any]:
    return {
        "id": f"rev-{number}",
        "rating": rating,
        "title": f"Review {number}",
        "body": f"The export crashes after the update ({number}).",
        "reviewerNickname": f"nickname{number}",
        "territory": "DEU",
        "createdDate": f"2026-11-0{number}T08:00:00-07:00",
        "response": response,
    }


def default_reviews() -> list[dict[str, Any]]:
    return [review(1, 1), review(2, 2), review(3, 5, "Thank you!"), review(4, 1)]


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.keys: dict[str, tuple[str, Any]] = {}
        for value in tokens:
            member = json.loads(value)["ios"]
            private = serialization.load_pem_private_key(member["private_key"].encode(), None)
            self.keys[member["key_id"]] = (member["issuer_id"], private.public_key())
        self.reviews = default_reviews()
        self.requests = 0
        self.written: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def admits(self, header: str | None) -> bool:
        if not header or not header.startswith("Bearer "):
            return False
        signed = header.removeprefix("Bearer ")
        try:
            kid = jwt.get_unverified_header(signed).get("kid")
            if kid not in self.keys:
                return False
            issuer, public = self.keys[kid]
            claims = jwt.decode(
                signed,
                public,
                algorithms=["ES256"],
                audience=AUDIENCE,
                issuer=issuer,
                options={"require": ["iat", "exp", "aud", "iss"]},
            )
        except jwt.PyJWTError:
            return False
        return int(claims["exp"]) - int(claims["iat"]) <= 1200


def _resource(item: dict[str, Any]) -> dict[str, Any]:
    response = (
        {"data": {"type": "customerReviewResponses", "id": f"resp-{item['id']}"}}
        if item.get("response") is not None
        else {"data": None}
    )
    return {
        "type": "customerReviews",
        "id": item["id"],
        "attributes": {
            "rating": item["rating"],
            "title": item["title"],
            "body": item["body"],
            "reviewerNickname": item.get("reviewerNickname", "someone"),
            "createdDate": item["createdDate"],
            "territory": item["territory"],
        },
        "relationships": {"response": response},
        "links": {"self": f"/v1/customerReviews/{item['id']}"},
    }


def _response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "customerReviewResponses",
        "id": f"resp-{item['id']}",
        "attributes": {
            "responseBody": item["response"],
            "lastModifiedDate": "2026-11-07T10:00:00-08:00",
            "state": item.get("state", "PUBLISHED"),
        },
        "relationships": {"review": {"data": {"type": "customerReviews", "id": item["id"]}}},
    }


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

        def refuse(self, status: int, code: str, title: str) -> None:
            error = {
                "id": "fake-error",
                "status": str(status),
                "code": code,
                "title": title,
                "detail": f"refused by the fake: {title}",
            }
            self.answer(status, {"errors": [error]})

        def _admitted(self) -> bool:
            with state.lock:
                state.requests += 1
            if not state.admits(self.headers.get("Authorization")):
                self.refuse(401, "NOT_AUTHORIZED", "Authentication credentials are missing")
                return False
            return True

        def _base(self) -> str:
            host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
            return f"http://{host}"

        def do_POST(self) -> None:
            url = urlparse(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if url.path == "/_fake/reviews":
                with state.lock:
                    state.reviews = json.loads(body)
                self.answer(200, {"ok": True})
                return
            if not self._admitted():
                return
            if url.path != "/v1/customerReviewResponses":
                self.refuse(404, "NOT_FOUND", "The specified resource does not exist")
                return
            try:
                data = json.loads(body)["data"]
                assert data["type"] == "customerReviewResponses"
                text = data["attributes"]["responseBody"]
                related = data["relationships"]["review"]["data"]
                assert related["type"] == "customerReviews" and isinstance(text, str)
                wanted = related["id"]
            except (ValueError, KeyError, TypeError, AssertionError):
                self.refuse(409, "ENTITY_ERROR", "The provided entity is invalid")
                return
            with state.lock:
                found = [r for r in state.reviews if r["id"] == wanted]
                if found:
                    found[0]["response"] = text
                    found[0]["state"] = "PENDING_PUBLISH"
                    state.written.append({"review": wanted, "text": text})
            if not found:
                self.refuse(404, "NOT_FOUND", "The specified resource does not exist")
                return
            self.answer(
                201,
                {"data": _response(found[0]), "links": {"self": f"{self._base()}{url.path}"}},
            )

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, {"requests": state.requests, "written": state.written})
                return
            if not self._admitted():
                return
            query = parse_qs(url.query)
            parts = url.path.strip("/").split("/")
            if parts[:2] == ["v1", "apps"] and len(parts) == 4 and parts[3] == "customerReviews":
                self._list(parts[2], query)
            elif parts[:2] == ["v1", "customerReviews"] and len(parts) == 3:
                with state.lock:
                    found = [r for r in state.reviews if r["id"] == parts[2]]
                if not found:
                    self.refuse(404, "NOT_FOUND", "The specified resource does not exist")
                    return
                document: dict[str, Any] = {
                    "data": _resource(found[0]),
                    "links": {"self": f"{self._base()}{url.path}"},
                }
                if "response" in query.get("include", [""])[0].split(",") and found[0].get(
                    "response"
                ):
                    document["included"] = [_response(found[0])]
                self.answer(200, document)
            else:
                self.refuse(404, "NOT_FOUND", "The specified resource does not exist")

        def _list(self, app: str, query: dict[str, list[str]]) -> None:
            if app != APP:
                self.refuse(404, "NOT_FOUND", "The specified resource does not exist")
                return
            try:
                limit = int(query.get("limit", ["50"])[0])
                offset = int(query.get("cursor", ["0"])[0])
                ratings = {int(r) for r in query.get("filter[rating]", ["1,2,3,4,5"])[0].split(",")}
            except ValueError:
                limit, offset, ratings = 0, 0, set()
            sort = query.get("sort", ["-createdDate"])[0]
            include = query.get("include", [""])[0]
            if (
                not 1 <= limit <= 200
                or offset < 0
                or not ratings <= {1, 2, 3, 4, 5}
                or not ratings
                or sort not in SORTS
                or include not in ("", "response")
            ):
                self.refuse(400, "PARAMETER_ERROR.INVALID", "A parameter has an invalid value")
                return
            with state.lock:
                every = [r for r in state.reviews if r["rating"] in ratings]
            field = sort.lstrip("-")
            every.sort(key=lambda r: r[field], reverse=sort.startswith("-"))
            page = every[offset : offset + limit]
            base = f"{self._base()}/v1/apps/{app}/customerReviews"
            given = {k: v[0] for k, v in query.items() if k != "cursor"}
            links: dict[str, str] = {"self": f"{base}?{urlencode(given)}"}
            if offset + limit < len(every):
                links["next"] = f"{base}?{urlencode({**given, 'cursor': offset + limit})}"
            document: dict[str, Any] = {
                "data": [_resource(r) for r in page],
                "links": links,
                "meta": {"paging": {"total": len(every), "limit": limit}},
            }
            if include == "response":
                document["included"] = [_response(r) for r in page if r.get("response")]
            self.answer(200, document)

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9246)
    args = parser.parse_args()
    given = os.environ.get("FAKE_TOKENS", "")
    tokens = {given} if given else set()
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake app store at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
