"""What the check does: one request, an expectation, an outcome and a duration.

The service is configured, never named by the call. A call names a path under the service's
base address, so that a process cannot make the connector reach any other host. The requesting
identity's credential travels as a bearer token to that service and nowhere else; a service
that admits anyone ignores it.

The expectation has three parts, each optional but the status, which defaults to 200:

- `status`: one status or a list of them; a redirect is not followed, so it is a status too;
- `body_contains`: a text the body must contain, read up to `BODY_LIMIT` bytes;
- `max_duration_ms`: the longest the answer may take, from sending the request to the end of
  the body.

The outcome is `passed` when every part holds and `failed` otherwise, with one entry per part
that failed. A service that does not answer in time, or cannot be reached, is a failed check:
observing that is what a check is for. Only a call the connector cannot make — a path that is
not one, an expectation that cannot hold — is an error, `invalid`, before any request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from taktus.adapters.driven.connectors.serving import Call, Outcome, invalid

type Json = dict[str, Any]

BODY_LIMIT = 1_048_576
"""The most bytes of a body that are read for `body_contains`."""
METHODS = frozenset({"GET", "HEAD"})


@dataclass(frozen=True)
class Config:
    target: str
    """The base address of the service the checks are made against."""
    timeout: float = 30.0
    """The longest a check waits for its answer, in seconds."""


def _path(input: Json) -> str:
    path = input.get("path", "/")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or any(ord(c) < 33 for c in path)
    ):
        raise invalid("path must be a path under the service's address, starting with one /")
    return path


def _expectation(input: Json) -> Json:
    expect = input.get("expect", {})
    if not isinstance(expect, dict) or set(expect) - {"status", "body_contains", "max_duration_ms"}:
        raise invalid("expect names status, body_contains and max_duration_ms, and nothing else")
    status = expect.get("status", 200)
    statuses = status if isinstance(status, list) else [status]
    if not statuses or not all(
        isinstance(s, int) and not isinstance(s, bool) and 100 <= s <= 599 for s in statuses
    ):
        raise invalid("expect.status must be a status from 100 to 599, or a list of them")
    out: Json = {"status": statuses}
    if "body_contains" in expect:
        text = expect["body_contains"]
        if not isinstance(text, str) or not text:
            raise invalid("expect.body_contains must be a text that is not empty")
        out["body_contains"] = text
    if "max_duration_ms" in expect:
        limit = expect["max_duration_ms"]
        if isinstance(limit, bool) or not isinstance(limit, int | float) or limit <= 0:
            raise invalid("expect.max_duration_ms must be a positive number")
        out["max_duration_ms"] = limit
    return out


async def run(config: Config, call: Call, input: Json) -> Outcome:
    path = _path(input)
    method = str(input.get("method", "GET")).upper()
    if method not in METHODS:
        raise invalid("method must be GET or HEAD: a check changes nothing")
    expect = _expectation(input)
    if method == "HEAD" and "body_contains" in expect:
        raise invalid("a HEAD request has no body to contain a text")
    url = config.target.rstrip("/") + path
    failures: list[Json] = []
    status: int | None = None
    call.count()
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout), follow_redirects=False
        ) as client:
            async with client.stream(
                method, url, headers={"Authorization": f"Bearer {call.token}"}
            ) as response:
                status = response.status_code
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= BODY_LIMIT:
                        break
        duration = (time.perf_counter() - started) * 1000
    except httpx.TimeoutException:
        duration = (time.perf_counter() - started) * 1000
        failures.append({"expected": "an answer", "observed": "no answer in time"})
        body = bytearray()
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        duration = (time.perf_counter() - started) * 1000
        failures.append({"expected": "an answer", "observed": type(error).__name__})
        body = bytearray()
    if status is not None:
        if status not in expect["status"]:
            failures.append({"expected": f"status {expect['status']}", "observed": status})
        if "body_contains" in expect and expect["body_contains"].encode() not in body:
            failures.append(
                {"expected": f"a body containing {expect['body_contains']!r}", "observed": None}
            )
        if "max_duration_ms" in expect and duration > expect["max_duration_ms"]:
            failures.append(
                {
                    "expected": f"at most {expect['max_duration_ms']} ms",
                    "observed": round(duration, 1),
                }
            )
    return Outcome(
        output={
            "outcome": "failed" if failures else "passed",
            "path": path,
            "method": method,
            "status": status,
            "duration_ms": round(duration, 1),
            "expectation": expect,
            "failures": failures,
        },
        effect={"kind": "read"},
    )


OPERATIONS = {"check.http.run": run}
