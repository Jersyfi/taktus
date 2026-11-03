#!/usr/bin/env python3
"""A fake cloud billing API: the cost query of the AWS Cost Explorer API, in memory.

The cloud billing connector under `connectors/taktus_connectors/aws/` asks
`POST /` with `X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`, signed with Signature
Version 4. This fake answers it in the API's shapes, with the API's error types, over costs it
holds in memory. It exists so that the connector and the cost watcher can be exercised in CI
without a network, an account or a secret.

What it enforces, because the connector's checks depend on it:

- **The signature.** It recomputes Signature Version 4 for the service `ce` from the request
  and the key pairs it was started with (`FAKE_TOKENS`, comma separated, each
  `<access key id>:<secret>`). An unknown key id is `UnrecognizedClientException`, a wrong
  signature `InvalidSignatureException`, a missing one `MissingAuthenticationToken`; all 403.
- **The request.** `Granularity` is `DAILY`, one metric of `UnblendedCost`, `AmortizedCost`
  and `NetUnblendedCost`, one `GroupBy` of the dimension `SERVICE`, `LINKED_ACCOUNT` or
  `REGION`, and `Start` before `End`, both dates. A start before 2020-01-01 is refused as the
  API refuses a period it holds no data for. Anything else is 400 `ValidationException`.
- **Pages.** At most `FAKE_PAGE_DAYS` days (default 10) per answer, with a `NextPageToken`.

The costs: every day three services, `Compute` 12.00, `Storage` 0.4310 and `Functions` 1.20,
in USD, unless a test set other amounts for a day with `POST /_fake/costs`, a JSON object
`{date: {service: amount}}`. The last day of an answer is `Estimated`. By account or region
the day's amounts are one group each, `000000000000` or `eu-central-1`. Test-only:
`GET /_fake/state` counts the requests and names the key ids seen.
Standard library only; runnable as `python3 tests/fakes/cloud_billing_service.py --port 9210`.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import threading
from datetime import date, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ACTION = "AWSInsightsIndexService.GetCostAndUsage"
DEFAULT = {"Compute": "12.00", "Storage": "0.4310", "Functions": "1.20"}
METRICS = {"UnblendedCost", "AmortizedCost", "NetUnblendedCost"}
DIMENSIONS = {"SERVICE", "LINKED_ACCOUNT", "REGION"}
AUTHORIZATION = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=(?P<key>[^/]+)/(?P<scope>[^,]+), "
    r"SignedHeaders=(?P<signed>[^,]+), Signature=(?P<signature>[0-9a-f]{64})$"
)


class State:
    def __init__(self, keys: dict[str, str], page_days: int) -> None:
        self.keys = keys
        self.page_days = page_days
        self.costs: dict[str, dict[str, str]] = {}
        self.requests = 0
        self.seen_keys: list[str] = []
        self.lock = threading.Lock()


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def signature(secret: str, scope: str, stamp: str, canonical: str) -> str:
    day, region, service, _ = scope.split("/")
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret}".encode(), day), region), service), "aws4_request")
    return hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/x-amz-json-1.1")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def refuse(self, status: int, kind: str) -> None:
            self.answer(status, {"__type": f"com.amazonaws.fake#{kind}", "message": kind})

        def do_GET(self) -> None:
            if self.path != "/_fake/state":
                self.answer(404, {"message": "not found"})
                return
            with state.lock:
                self.answer(200, {"requests": state.requests, "seen_keys": state.seen_keys})

        def _body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def do_POST(self) -> None:
            body = self._body()
            if self.path == "/_fake/costs":
                with state.lock:
                    for day, services in json.loads(body).items():
                        state.costs[day] = {**DEFAULT, **services}
                self.answer(200, {"ok": True})
                return
            with state.lock:
                state.requests += 1
            if not self._signed(body):
                return
            if self.headers.get("X-Amz-Target") != ACTION:
                self.refuse(400, "UnknownOperationException")
                return
            try:
                request = json.loads(body)
            except ValueError:
                self.refuse(400, "SerializationException")
                return
            self._costs(request)

        def _signed(self, body: bytes) -> bool:
            match = AUTHORIZATION.match(self.headers.get("Authorization") or "")
            stamp = self.headers.get("X-Amz-Date") or ""
            if match is None or not stamp:
                self.refuse(403, "MissingAuthenticationToken")
                return False
            key = match["key"]
            with state.lock:
                state.seen_keys.append(key)
            secret = state.keys.get(key)
            if secret is None:
                self.refuse(403, "UnrecognizedClientException")
                return False
            names = match["signed"].split(";")
            if "host" not in names or "x-amz-date" not in names:
                self.refuse(403, "IncompleteSignature")
                return False
            headers = "".join(
                f"{name}:{' '.join((self.headers.get(name) or '').split())}\n" for name in names
            )
            canonical = "\n".join(
                [
                    "POST",
                    self.path.split("?")[0] or "/",
                    "",
                    headers,
                    match["signed"],
                    hashlib.sha256(body).hexdigest(),
                ]
            )
            expected = signature(secret, match["scope"], stamp, canonical)
            if not hmac.compare_digest(expected, match["signature"]):
                self.refuse(403, "InvalidSignatureException")
                return False
            return True

        def _costs(self, request: dict[str, Any]) -> None:
            try:
                period = request["TimePeriod"]
                start = date.fromisoformat(period["Start"])
                end = date.fromisoformat(period["End"])
                (metric,) = request["Metrics"]
                (group,) = request["GroupBy"]
            except (KeyError, TypeError, ValueError):
                self.refuse(400, "ValidationException")
                return
            if (
                request.get("Granularity") != "DAILY"
                or metric not in METRICS
                or group.get("Type") != "DIMENSION"
                or group.get("Key") not in DIMENSIONS
                or not start < end
                or start < date(2020, 1, 1)
            ):
                self.refuse(400, "ValidationException")
                return
            offset = int(request.get("NextPageToken") or 0)
            first = start + timedelta(days=offset)
            last = min(end, first + timedelta(days=state.page_days))
            results = []
            day = first
            while day < last:
                with state.lock:
                    amounts = state.costs.get(day.isoformat(), DEFAULT)
                if group["Key"] == "SERVICE":
                    groups = amounts
                else:
                    name = "000000000000" if group["Key"] == "LINKED_ACCOUNT" else "eu-central-1"
                    groups = {name: format(sum(Decimal(a) for a in amounts.values()), "f")}
                results.append(
                    {
                        "TimePeriod": {
                            "Start": day.isoformat(),
                            "End": (day + timedelta(days=1)).isoformat(),
                        },
                        "Total": {},
                        "Groups": [
                            {"Keys": [name], "Metrics": {metric: {"Amount": a, "Unit": "USD"}}}
                            for name, a in groups.items()
                        ],
                        "Estimated": day + timedelta(days=1) == end,
                    }
                )
                day += timedelta(days=1)
            answer: dict[str, Any] = {"ResultsByTime": results, "GroupDefinitions": [group]}
            if last < end:
                answer["NextPageToken"] = str(offset + state.page_days)
            self.answer(200, answer)

    return Handler


def keys_from(text: str) -> dict[str, str]:
    pairs = [part.split(":", 1) for part in text.split(",") if ":" in part]
    return {key: secret for key, secret in pairs}


def make_server(
    host: str, port: int, keys: dict[str, str], page_days: int = 10
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(keys, page_days)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9210)
    args = parser.parse_args()
    keys = keys_from(os.environ.get("FAKE_TOKENS", ""))
    page_days = int(os.environ.get("FAKE_PAGE_DAYS", "10"))
    server = make_server(args.host, args.port, keys, page_days)
    sys.stderr.write(f"fake cloud billing at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
