#!/usr/bin/env python3
"""A fake content lake: the part of the Sanity HTTP API the website connector uses, in memory.

The connector under `connectors/taktus_connectors/sanity/` asks, under `/<api version>/data/`,
where the version is `v1` or `v` and a date:

- `GET doc/<dataset>/<id>,<id>`: `{"documents": [...], "omitted": [{"id", "reason"}]}`, the
  documents of those identifiers, a draft (`drafts.<id>`) among them; an identifier the dataset
  does not hold is omitted with the reason `existence`;
- `POST mutate/<dataset>`: `{"mutations": [...]}` applied as one transaction, answered
  `{"transactionId", "results": [{"operation", "documentId"}]}`. It takes `createIfNotExists`,
  which leaves a document already there untouched, `createOrReplace`, `create` and `delete` by
  `id`; a `patch` or a `delete` by query is not served, 400;
- `POST actions/<dataset>`: `{"actions": [...]}`, of which it takes
  `sanity.action.document.publish` with `publishedId`, `versionId` (a `drafts.` identifier) and
  an optional `ifVersionRevisionId`: the published document replaced by the draft's content and
  the draft deleted, answered `{"transactionId"}`; 404 for a draft the dataset does not hold, 409
  for a revision that differs. Another action type is 400. Before `v2024-05-23` the endpoint
  answers 404, as the API does.

The documentation names the statuses (400, 401, 403, 404, 409) and no error body; the fake
answers `{"error": {"description": ...}}`, and the connector reads only the status.

What it enforces, because the connector's checks depend on it:

- **Authentication.** `Authorization: Bearer` and a token the fake was started with
  (`FAKE_TOKENS`, comma separated); otherwise 401. The dataset is private: a request without a
  token is 401 too.
- **The dataset.** Only `production` exists; another is 404.
- **Revisions.** Every document written gets a new `_rev` and `_updatedAt`, as the API stores
  them.

It starts with one published post, `post-1`, of the type `post`. Test-only: `GET /_fake/state`
names every document with its type, title and revision, and the publish actions taken, in
order; `POST /_fake/reset` restores the start. Standard library only; runnable as
`python3 tests/fakes/content_lake_service.py --port 9283`.
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
from urllib.parse import unquote, urlparse

type Json = dict[str, Any]

DATASET = "production"
DRAFTS = "drafts."
VERSION = re.compile(r"^v(1|(\d{4}-\d{2}-\d{2}))$")
ACTIONS_SINCE = "2024-05-23"


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.documents: dict[str, Json] = {
            "post-1": {
                "_id": "post-1",
                "_type": "post",
                "_rev": "rev-seeded",
                "_createdAt": "2026-10-01T08:00:00Z",
                "_updatedAt": "2026-10-01T08:00:00Z",
                "title": "Hello world",
                "slug": {"_type": "slug", "current": "hello-world"},
                "body": [
                    {
                        "_type": "block",
                        "_key": "b0",
                        "style": "normal",
                        "markDefs": [],
                        "children": [
                            {"_type": "span", "_key": "b0s0", "text": "Hello.", "marks": []}
                        ],
                    }
                ],
            }
        }
        self.published: list[str] = []
        self.clock = 0

    def stamp(self, document: Json) -> Json:
        self.clock += 1
        moment = f"2026-11-07T08:{self.clock // 60:02d}:{self.clock % 60:02d}Z"
        return {
            **document,
            "_rev": uuid.uuid4().hex[:22],
            "_createdAt": document.get("_createdAt", moment),
            "_updatedAt": moment,
        }


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

        def error(self, status: int, description: str) -> None:
            self.answer(status, {"error": {"description": description}})

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
            if given.startswith("Bearer ") and given[7:] in state.tokens:
                return True
            self.error(401, "Unauthorized - Session not found")
            return False

        def route(self) -> tuple[str, str, str] | None:
            """The API version's date, the endpoint and what follows the dataset; None after
            an answer was given."""
            parts = urlparse(self.path).path.strip("/").split("/")
            if len(parts) < 4 or parts[1] != "data" or VERSION.match(parts[0]) is None:
                self.error(404, "Not found")
                return None
            if parts[3] != DATASET:
                self.error(404, "Dataset not found")
                return None
            version = VERSION.match(parts[0])
            date = (version.group(2) if version else None) or "0000-00-00"
            return date, parts[2], "/".join(parts[4:])

        def fake(self) -> bool:
            path = urlparse(self.path).path
            if path == "/_fake/state" and self.command == "GET":
                with state.lock:
                    self.answer(
                        200,
                        {
                            "documents": {
                                k: {"type": d["_type"], "title": d.get("title"), "rev": d["_rev"]}
                                for k, d in state.documents.items()
                            },
                            "published": list(state.published),
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
            route = self.route()
            if route is None:
                return
            _, endpoint, rest = route
            if endpoint != "doc" or not rest:
                self.error(404, "Not found")
                return
            identifiers = [unquote(i) for i in rest.split(",") if i]
            with state.lock:
                documents = [state.documents[i] for i in identifiers if i in state.documents]
                omitted = [
                    {"id": i, "reason": "existence"}
                    for i in identifiers
                    if i not in state.documents
                ]
            self.answer(200, {"documents": documents, "omitted": omitted})

        def do_POST(self) -> None:
            if self.fake() or not self.admitted():
                return
            route = self.route()
            if route is None:
                return
            date, endpoint, rest = route
            body = self.body()
            if rest:
                self.error(404, "Not found")
            elif endpoint == "mutate":
                self.mutate(body)
            elif endpoint == "actions":
                if date < ACTIONS_SINCE:
                    self.error(404, "Not found")
                else:
                    self.act(body)
            else:
                self.error(404, "Not found")

        def mutate(self, body: Any) -> None:
            mutations = body.get("mutations") if isinstance(body, dict) else None
            if not isinstance(mutations, list) or not mutations:
                self.error(400, "The request body must hold a list of mutations")
                return
            with state.lock:
                documents = dict(state.documents)
                results: list[Json] = []
                for mutation in mutations:
                    if not isinstance(mutation, dict) or len(mutation) != 1:
                        self.error(400, "A mutation names exactly one operation")
                        return
                    ((operation, given),) = mutation.items()
                    if operation in ("create", "createIfNotExists", "createOrReplace"):
                        if not isinstance(given, dict) or not isinstance(given.get("_type"), str):
                            self.error(400, "A document must have a _type")
                            return
                        identifier = given.get("_id") or uuid.uuid4().hex
                        if identifier in documents:
                            if operation == "create":
                                self.error(409, f"Document by ID {identifier} already exists")
                                return
                            if operation == "createIfNotExists":
                                continue
                        documents[identifier] = state.stamp({**given, "_id": identifier})
                        results.append({"operation": "create", "documentId": identifier})
                    elif operation == "delete" and isinstance(given, dict) and "id" in given:
                        if documents.pop(str(given["id"]), None) is not None:
                            results.append({"operation": "delete", "documentId": given["id"]})
                    else:
                        self.error(400, f"The fake does not serve the mutation {operation!r}")
                        return
                state.documents = documents
            self.answer(200, {"transactionId": uuid.uuid4().hex, "results": results})

        def act(self, body: Any) -> None:
            actions = body.get("actions") if isinstance(body, dict) else None
            if not isinstance(actions, list) or not actions:
                self.error(400, "The request body must hold a list of actions")
                return
            with state.lock:
                documents = dict(state.documents)
                for action in actions:
                    if not isinstance(action, dict):
                        self.error(400, "An action is an object")
                        return
                    if action.get("actionType") != "sanity.action.document.publish":
                        self.error(400, "The fake serves only the publish action")
                        return
                    published, version = action.get("publishedId"), action.get("versionId")
                    if (
                        not isinstance(published, str)
                        or not isinstance(version, str)
                        or version != f"{DRAFTS}{published}"
                    ):
                        self.error(400, "publishedId and versionId must name one document")
                        return
                    draft = documents.get(version)
                    if draft is None:
                        self.error(404, f"Document {version} not found")
                        return
                    wanted = action.get("ifVersionRevisionId")
                    if wanted is not None and wanted != draft["_rev"]:
                        self.error(409, "Revision mismatch")
                        return
                    documents[published] = state.stamp({**draft, "_id": published})
                    del documents[version]
                    state.published.append(published)
                state.documents = documents
            self.answer(200, {"transactionId": uuid.uuid4().hex})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9283)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake content lake at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
