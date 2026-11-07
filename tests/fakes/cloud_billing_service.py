#!/usr/bin/env python3
"""A fake cloud API: the cost query of AWS Cost Explorer, the event filter of CloudWatch Logs
and the secret list of AWS Secrets Manager, in memory, on one port.

The cloud connector under `connectors/taktus_connectors/aws/` asks `POST /` with an
`X-Amz-Target` naming the action, signed with Signature Version 4. This fake answers three
actions in the APIs' published shapes, with their documented error types, over data it holds
in memory: `AWSInsightsIndexService.GetCostAndUsage` (service `ce`),
`Logs_20140328.FilterLogEvents` (service `logs`) and `secretsmanager.ListSecrets` (service
`secretsmanager`). Any other action, `GetSecretValue` among them, is 404
`UnknownOperationException`, and every action asked is recorded. It exists so that the
connector and the processes that read it can be exercised in CI without a network, an account
or a secret.

What it enforces, because the connector's checks depend on it:

- **The signature.** It recomputes Signature Version 4 from the request and the key pairs it
  was started with (`FAKE_TOKENS`, comma separated, each `<access key id>:<secret>`). An
  unknown key id is `UnrecognizedClientException`, a wrong signature or a scope of another
  service than the action's `InvalidSignatureException`, a missing one
  `MissingAuthenticationToken`; all 403.
- **The cost query.** `Granularity` is `DAILY`, one metric of `UnblendedCost`, `AmortizedCost`
  and `NetUnblendedCost`, one `GroupBy` of the dimension `SERVICE`, `LINKED_ACCOUNT` or
  `REGION`, and `Start` before `End`, both dates. A start before 2020-01-01 is refused as the
  API refuses a period it holds no data for. Anything else is 400 `ValidationException`. At
  most `FAKE_PAGE_DAYS` days (default 10) per answer, with a `NextPageToken`.
- **The event filter.** Exactly one of `logGroupName` and `logGroupIdentifier`; an unknown
  group is 400 `ResourceNotFoundException`. `limit` from 1 to 10000, `filterPattern` of at
  most 1024 characters, `startTime` not after `endTime`, and `startFromHead` false only with a
  `startTime` on or after 2024-01-01; otherwise 400 `InvalidParameterException`. Events from
  `startTime` to `endTime` (milliseconds), newest first where `startFromHead` is false. Of the
  filter pattern syntax the fake knows only terms, bare or quoted, that must all occur in the
  message (case-sensitive); a JSON, space-delimited or `?` pattern is refused as invalid by the
  fake, though the API would take it. At most `FAKE_LOG_PAGE` events (default 3) per page,
  with a `nextToken` while events remain.
- **The secret list.** `MaxResults` from 1 to 100, at most ten `Filters`, each of a documented
  key with one to ten values of the documented pattern; otherwise 400
  `InvalidParameterException`. Of the keys the fake applies only `name`, a case-sensitive
  prefix match that a leading `!` negates; another documented key is refused by the fake. A
  `NextToken` the fake did not give is 400 `InvalidNextTokenException`.
- **Empty pages.** Both APIs document that a page may be empty while it names a next token.
  Started with `empty_first`, the fake answers the first request of a list with an empty page
  and a token.

The costs: every day three services, `Compute` 12.00, `Storage` 0.4310 and `Functions` 1.20,
in USD, unless a test set other amounts for a day with `POST /_fake/costs`, a JSON object
`{date: {service: amount}}`. The last day of an answer is `Estimated`. By account or region
the day's amounts are one group each, `000000000000` or `eu-central-1`.

The logs: the log group `/taktus/app` holds six events of the streams `web-1` and `worker-1`,
one every two minutes before the fake started, the newest one minute before. The secrets:
three, `prod/db/password`, `prod/payments/api-key` and `staging/cache/token`, whose dates are
days before the fake started, with a description and tags (one naming a person) the connector
must never copy, and no value anywhere.

Test-only: `GET /_fake/state` counts the requests, names the key ids seen and the actions
asked. Standard library only; runnable as
`python3 tests/fakes/cloud_billing_service.py --port 9210`.
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
import time
from datetime import date, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ACTION = "AWSInsightsIndexService.GetCostAndUsage"
LOGS = "Logs_20140328.FilterLogEvents"
SECRETS = "secretsmanager.ListSecrets"
SERVICES = {ACTION: "ce", LOGS: "logs", SECRETS: "secretsmanager"}
DEFAULT = {"Compute": "12.00", "Storage": "0.4310", "Functions": "1.20"}
METRICS = {"UnblendedCost", "AmortizedCost", "NetUnblendedCost"}
DIMENSIONS = {"SERVICE", "LINKED_ACCOUNT", "REGION"}
AUTHORIZATION = re.compile(
    r"^AWS4-HMAC-SHA256 Credential=(?P<key>[^/]+)/(?P<scope>[^,]+), "
    r"SignedHeaders=(?P<signed>[^,]+), Signature=(?P<signature>[0-9a-f]{64})$"
)
GROUP = "/taktus/app"
NEWEST_FIRST_FROM = 1704067200000
"""2024-01-01T00:00:00Z in milliseconds: `startFromHead` false is refused before it."""
FILTER_KEYS = {
    "description",
    "name",
    "tag-key",
    "tag-value",
    "primary-region",
    "owning-service",
    "all",
}
FILTER_VALUE = re.compile(r"^\!?[a-zA-Z0-9 :_@/+=.\-!]*$")
TERMS = re.compile(r'"([^"]*)"|(\S+)')
DAY = 86400


def events(started: float) -> list[dict[str, Any]]:
    """Six events, one every two minutes before `started` (seconds), the newest first."""
    messages = [
        "INFO request served path=/orders status=200",
        "ERROR payment declined code=card_expired",
        "INFO request served path=/health status=200",
        "WARN slow query took=1840ms",
        "ERROR upstream timeout service=ledger",
        "INFO worker started",
    ]
    out = []
    for n, message in enumerate(messages):
        at = int((started - 60 - 120 * n) * 1000)
        out.append(
            {
                "logStreamName": "web-1" if n % 2 == 0 else "worker-1",
                "timestamp": at,
                "ingestionTime": at + 350,
                "message": message,
                "eventId": f"{at}{n:04d}3713262927494551977980532285720373558",
            }
        )
    return out


def stored_secrets(started: float) -> list[dict[str, Any]]:
    """Three secrets' list entries in the API's shape, dated days before `started`."""
    region = "eu-central-1"
    arn = f"arn:aws:secretsmanager:{region}:000000000000:secret:"
    midnight = started - started % DAY
    return [
        {
            "ARN": arn + "prod/payments/api-key-a1b2c3",
            "Name": "prod/payments/api-key",
            "Description": "The payment provider's key",
            "CreatedDate": started - 200 * DAY,
            "LastChangedDate": started - 10 * DAY,
            "LastRotatedDate": started - 10 * DAY,
            "LastAccessedDate": midnight - DAY,
            "NextRotationDate": started + 20 * DAY,
            "RotationEnabled": True,
            "RotationLambdaARN": f"arn:aws:lambda:{region}:000000000000:function:rotate",
            "RotationRules": {"AutomaticallyAfterDays": 30},
            "Tags": [{"Key": "owner", "Value": "jane.doe@example.com"}],
            "SecretVersionsToStages": {"EXAMPLE1-90ab-cdef-fedc-ba987EXAMPLE": ["AWSCURRENT"]},
            "PrimaryRegion": region,
        },
        {
            "ARN": arn + "prod/db/password-d4e5f6",
            "Name": "prod/db/password",
            "Description": "The database's password",
            "CreatedDate": started - 400 * DAY,
            "LastChangedDate": started - 90.5 * DAY,
            "LastAccessedDate": midnight,
            "Tags": [{"Key": "team", "Value": "platform"}],
            "SecretVersionsToStages": {"EXAMPLE2-90ab-cdef-fedc-ba987EXAMPLE": ["AWSCURRENT"]},
        },
        {
            "ARN": arn + "staging/cache/token-g7h8i9",
            "Name": "staging/cache/token",
            "CreatedDate": started - 5 * DAY,
            "RotationEnabled": False,
            "SecretVersionsToStages": {"EXAMPLE3-90ab-cdef-fedc-ba987EXAMPLE": ["AWSCURRENT"]},
        },
    ]


class State:
    def __init__(
        self, keys: dict[str, str], page_days: int, log_page: int, empty_first: bool
    ) -> None:
        self.keys = keys
        self.page_days = page_days
        self.log_page = log_page
        self.empty_first = empty_first
        started = time.time()
        self.groups: dict[str, list[dict[str, Any]]] = {GROUP: events(started)}
        self.secrets = stored_secrets(started)
        self.costs: dict[str, dict[str, str]] = {}
        self.requests = 0
        self.seen_keys: list[str] = []
        self.actions: list[str] = []
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
                self.answer(
                    200,
                    {
                        "requests": state.requests,
                        "seen_keys": state.seen_keys,
                        "actions": state.actions,
                    },
                )

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
            target = self.headers.get("X-Amz-Target") or ""
            with state.lock:
                state.requests += 1
                state.actions.append(target)
            if not self._signed(body, SERVICES.get(target)):
                return
            if target not in SERVICES:
                self.refuse(404, "UnknownOperationException")
                return
            try:
                request = json.loads(body)
            except ValueError:
                request = None
            if not isinstance(request, dict):
                self.refuse(400, "SerializationException")
                return
            if target == LOGS:
                self._events(request)
            elif target == SECRETS:
                self._secrets(request)
            else:
                self._costs(request)

        def _signed(self, body: bytes, service: str | None) -> bool:
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
            scoped = match["scope"].split("/")
            if len(scoped) != 4 or (service is not None and scoped[2] != service):
                self.refuse(403, "InvalidSignatureException")
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

        def _events(self, request: dict[str, Any]) -> None:
            named = [k for k in ("logGroupName", "logGroupIdentifier") if request.get(k)]
            limit = request.get("limit", 10000)
            pattern = request.get("filterPattern", "")
            start = request.get("startTime", 0)
            end = request.get("endTime", 2**62)
            head = request.get("startFromHead", True)
            token = request.get("nextToken")
            if (
                len(named) != 1
                or not isinstance(limit, int)
                or not 1 <= limit <= 10000
                or not isinstance(pattern, str)
                or len(pattern) > 1024
                or not isinstance(start, int)
                or not isinstance(end, int)
                or not 0 <= start <= end
                or (head is False and "startTime" in request and start < NEWEST_FIRST_FROM)
            ):
                self.refuse(400, "InvalidParameterException")
                return
            group = str(request[named[0]]).split(":log-group:")[-1].removesuffix(":*")
            with state.lock:
                held = list(state.groups.get(group) or []) if group in state.groups else None
            if held is None:
                self.refuse(400, "ResourceNotFoundException")
                return
            found = TERMS.findall(pattern)
            if pattern.lstrip().startswith(("{", "[")) or any(b.startswith("?") for _, b in found):
                self.refuse(400, "InvalidParameterException")  # a syntax the fake does not know
                return
            terms = [quoted or bare for quoted, bare in found]
            # The token names the direction of the first request and where the next page starts.
            if token is not None:
                direction, _, offset_text = str(token).partition(":")
                if direction not in ("f", "b") or not offset_text.isdigit():
                    self.refuse(400, "InvalidParameterException")
                    return
                offset = int(offset_text)
            else:
                direction, offset = ("f" if head is not False else "b"), 0
                if state.empty_first:
                    self.answer(200, {"events": [], "nextToken": f"{direction}:0"})
                    return
            matched = sorted(
                (
                    e
                    for e in held
                    if start <= e["timestamp"] <= end and all(t in e["message"] for t in terms)
                ),
                key=lambda e: e["timestamp"],
                reverse=direction == "b",
            )
            page = matched[offset : offset + min(limit, state.log_page)]
            answer: dict[str, Any] = {"events": page, "searchedLogStreams": []}
            if offset + len(page) < len(matched):
                answer["nextToken"] = f"{direction}:{offset + len(page)}"
            self.answer(200, answer)

        def _secrets(self, request: dict[str, Any]) -> None:
            size = request.get("MaxResults", 100)
            filters = request.get("Filters", [])
            token = request.get("NextToken")
            if (
                not isinstance(size, int)
                or not 1 <= size <= 100
                or not isinstance(filters, list)
                or len(filters) > 10
            ):
                self.refuse(400, "InvalidParameterException")
                return
            prefixes: list[str] = []
            for one in filters:
                values = one.get("Values") if isinstance(one, dict) else None
                if (
                    not isinstance(one, dict)
                    or one.get("Key") not in FILTER_KEYS
                    or not isinstance(values, list)
                    or not 1 <= len(values) <= 10
                    or not all(
                        isinstance(v, str) and len(v) <= 512 and FILTER_VALUE.match(v)
                        for v in values
                    )
                ):
                    self.refuse(400, "InvalidParameterException")
                    return
                if one["Key"] != "name":
                    self.refuse(400, "InvalidParameterException")  # a key the fake does not apply
                    return
                prefixes.extend(values)
            if token is not None:
                offset_text = str(token).removeprefix("o:")
                if not str(token).startswith("o:") or not offset_text.isdigit():
                    self.refuse(400, "InvalidNextTokenException")
                    return
                offset = int(offset_text)
            else:
                offset = 0
                if state.empty_first:
                    self.answer(200, {"SecretList": [], "NextToken": "o:0"})
                    return

            def kept(name: str) -> bool:
                for prefix in prefixes:
                    if prefix.startswith("!"):
                        if name.startswith(prefix[1:]):
                            return False
                    elif not name.startswith(prefix):
                        return False
                return True

            with state.lock:
                held = sorted(state.secrets, key=lambda s: s["CreatedDate"])
            matched = [s for s in held if kept(s["Name"])]
            page = matched[offset : offset + size]
            answer: dict[str, Any] = {"SecretList": page}
            if offset + len(page) < len(matched):
                answer["NextToken"] = f"o:{offset + len(page)}"
            self.answer(200, answer)

    return Handler


def keys_from(text: str) -> dict[str, str]:
    pairs = [part.split(":", 1) for part in text.split(",") if ":" in part]
    return {key: secret for key, secret in pairs}


def make_server(
    host: str,
    port: int,
    keys: dict[str, str],
    page_days: int = 10,
    *,
    log_page: int = 3,
    empty_first: bool = False,
) -> ThreadingHTTPServer:
    state = State(keys, page_days, log_page, empty_first)
    return ThreadingHTTPServer((host, port), handler(state))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9210)
    args = parser.parse_args()
    keys = keys_from(os.environ.get("FAKE_TOKENS", ""))
    page_days = int(os.environ.get("FAKE_PAGE_DAYS", "10"))
    log_page = int(os.environ.get("FAKE_LOG_PAGE", "3"))
    server = make_server(args.host, args.port, keys, page_days, log_page=log_page)
    sys.stderr.write(f"fake cloud API at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
