#!/usr/bin/env python3
"""A fake business-intelligence API: Power BI's Execute Queries and the Microsoft identity
platform's client credentials token, in memory.

The business-intelligence connector under `connectors/taktus_connectors/powerbi/` asks
`POST /<tenant>/oauth2/v2.0/token` for an access token, then
`POST /v1.0/myorg/datasets/<dataset>/executeQueries` or
`POST /v1.0/myorg/groups/<group>/datasets/<dataset>/executeQueries`. This fake answers all
three in the shapes and statuses the documentation states (the connector's README names the
pages), over one semantic model it holds in memory. It exists so that the connector can be
exercised in CI without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **The token.** The form needs `grant_type=client_credentials`, the scope
  `https://analysis.windows.net/powerbi/api/.default`, and a pair `client_id:client_secret`
  the fake was started with (`FAKE_TOKENS`, comma separated). Only the tenant `example`
  exists. An unknown tenant or a wrong scope is 400, an unknown client 401, each with `error`
  and `error_description`; otherwise 200 with `token_type`, `expires_in` and `access_token`.
- **The query.** It needs `Authorization: Bearer <token>` with a token the fake issued
  (otherwise 401) and a body with exactly one entry in `queries` (otherwise 400). The model is
  `cfafbeb1-8037-4d0c-896e-a46fb27ff229`, in the identity's own workspace and in the workspace
  `f089354e-8366-4e18-aea3-4cb4a3a50b48`; any other model or workspace is 404.
- **DAX.** It evaluates two queries over the table `Sales` (`Year`, `Quarter`, `Amount`):
  `EVALUATE VALUES(Sales)` (or `EVALUATE Sales`) answers every row, its columns fully
  qualified; `EVALUATE ROW("<name>", SUM(Sales[Amount]))` one row with the column `[<name>]`.
  Comments are skipped. Any other query is 400, `DAX query failure`. Without
  `serializerSettings.includeNulls` a blank `Quarter` is left out of its row, as the API leaves
  it out.
- **Limits.** More rows than `FAKE_ROW_LIMIT` (default 100000) are answered 200 with the
  first ones and an `error` on the result, as the API answers.

The rows: `FAKE_ROWS` of them (default 3), the last one's `Quarter` blank. Test-only:
`GET /_fake/state` counts the requests and names the client secrets and bearer tokens seen.
Standard library only; runnable as `python3 tests/fakes/business_intelligence_service.py
--port 9257`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

TENANT = "example"
SCOPE = "https://analysis.windows.net/powerbi/api/.default"
DATASET = "cfafbeb1-8037-4d0c-896e-a46fb27ff229"
GROUP = "f089354e-8366-4e18-aea3-4cb4a3a50b48"
TOKEN = re.compile(r"^/([^/]+)/oauth2/v2\.0/token$")
OWN = re.compile(r"^/v1\.0/myorg/datasets/([^/]+)/executeQueries$")
IN_GROUP = re.compile(r"^/v1\.0/myorg/groups/([^/]+)/datasets/([^/]+)/executeQueries$")
VALUES = re.compile(r"^EVALUATE\s+(?:VALUES\s*\(\s*Sales\s*\)|Sales)$", re.IGNORECASE)
COMMENTS = re.compile(r"/\*.*?\*/|(?://|--)[^\n]*", re.DOTALL)
SUM = re.compile(
    r'^EVALUATE\s+ROW\s*\(\s*"([A-Za-z][A-Za-z0-9 ]{0,63})"\s*,'
    r"\s*SUM\s*\(\s*Sales\[Amount\]\s*\)\s*\)$",
    re.IGNORECASE,
)


def sales(count: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(count):
        quarter = None if n == count - 1 else f"Q{n % 4 + 1}"
        out.append({"Year": 2026 + n // 4, "Quarter": quarter, "Amount": 1000 + 250 * n})
    return out


class State:
    def __init__(self, pairs: set[str], rows: int, row_limit: int) -> None:
        self.pairs = pairs
        self.sales = sales(rows)
        self.row_limit = row_limit
        self.issued: set[str] = set()
        self.requests = 0
        self.seen_tokens: list[str] = []
        self.lock = threading.Lock()


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

        def body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def do_GET(self) -> None:
            if urlparse(self.path).path == "/_fake/state":
                with state.lock:
                    body = {"requests": state.requests, "seen_tokens": list(state.seen_tokens)}
                self.answer(200, body)
                return
            self.answer(404, {"error": {"message": "Not Found"}})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            with state.lock:
                state.requests += 1
            token = TOKEN.match(path)
            if token is not None:
                self._token(token.group(1), parse_qs(self.body().decode()))
                return
            self._query(path)

        def _refuse_token(self, status: int, error: str, description: str) -> None:
            self.answer(
                status,
                {
                    "error": error,
                    "error_description": description,
                    "error_codes": [],
                    "timestamp": "2026-11-07 08:00:00Z",
                    "trace_id": secrets.token_hex(16),
                    "correlation_id": secrets.token_hex(16),
                },
            )

        def _token(self, tenant: str, form: dict[str, list[str]]) -> None:
            client_id = form.get("client_id", [""])[0]
            secret = form.get("client_secret", [""])[0]
            with state.lock:
                state.seen_tokens.append(secret)
            if tenant != TENANT:
                self._refuse_token(400, "invalid_request", "Tenant not found.")
                return
            if form.get("grant_type") != ["client_credentials"]:
                self._refuse_token(
                    400, "unsupported_grant_type", "The grant type is not supported."
                )
                return
            if form.get("scope") != [SCOPE]:
                self._refuse_token(400, "invalid_scope", "The provided scope is not valid.")
                return
            if f"{client_id}:{secret}" not in state.pairs:
                self._refuse_token(401, "invalid_client", "Invalid client secret provided.")
                return
            issued = "eyJ0eXAi." + secrets.token_hex(16)
            with state.lock:
                state.issued.add(issued)
            self.answer(200, {"token_type": "Bearer", "expires_in": 3599, "access_token": issued})

        def _query(self, path: str) -> None:
            raw = self.body()
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            with state.lock:
                state.seen_tokens.append(given)
                admitted = given in state.issued
            if not admitted:
                self.answer(401, {"error": {"message": "Unauthorized"}})
                return
            own, grouped = OWN.match(path), IN_GROUP.match(path)
            if own is not None:
                dataset = own.group(1)
            elif grouped is not None and grouped.group(1) == GROUP:
                dataset = grouped.group(2)
            else:
                self.answer(404, {"error": {"message": "Not Found"}})
                return
            if dataset != DATASET:
                self.answer(404, {"error": {"message": "Not Found"}})
                return
            try:
                body = json.loads(raw)
                (entry,) = body["queries"]
                query = entry["query"]
                assert isinstance(query, str)
            except (ValueError, KeyError, TypeError, AssertionError):
                self.answer(400, {"error": {"message": "The request body is not valid."}})
                return
            settings = body.get("serializerSettings") or {}
            nulls = bool(settings.get("includeNulls")) if isinstance(settings, dict) else False
            text = COMMENTS.sub(" ", query).strip()
            total = SUM.match(text)
            if VALUES.match(text):
                rows = [
                    {f"Sales[{k}]": v for k, v in r.items() if v is not None or nulls}
                    for r in state.sales
                ]
            elif total is not None:
                rows = [{f"[{total.group(1)}]": sum(r["Amount"] for r in state.sales)}]
            else:
                self.answer(400, {"error": {"message": "DAX query failure"}})
                return
            result: dict[str, Any] = {"tables": [{"rows": rows[: state.row_limit]}]}
            if len(rows) > state.row_limit:
                result["error"] = {"message": f"More than {state.row_limit} rows in a query result"}
            self.answer(200, {"results": [result]})

    return Handler


def make_server(
    host: str, port: int, pairs: set[str], rows: int = 3, row_limit: int = 100_000
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(pairs, rows, row_limit)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9257)
    args = parser.parse_args()
    pairs = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    rows = int(os.environ.get("FAKE_ROWS", "3"))
    row_limit = int(os.environ.get("FAKE_ROW_LIMIT", "100000"))
    server = make_server(args.host, args.port, pairs, rows, row_limit)
    sys.stderr.write(f"fake business intelligence at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
