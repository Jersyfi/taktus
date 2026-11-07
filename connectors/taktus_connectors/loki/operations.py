"""How the log lines are asked and their answer read.

The API answers a range query at `GET /loki/api/v1/query_range` with `query` (the call's
`filter`, a LogQL query passed verbatim), `start` and `end` in nanoseconds since the epoch,
`limit` and `direction=backward`, so that the newest lines come first. A log query answers
`resultType` `streams`: each stream names its labels and holds `[nanoseconds, line]` pairs. A
metric query answers `matrix` or `vector`, numbers rather than lines, and is `invalid` here.

The answer names no page token. `complete` is therefore true only when fewer than `limit`
lines came back: with exactly `limit`, more may exist in the window.

Each line becomes one entry. `severity` is the stream's label `level`, else its label
`detected_level`, else null. `source` is the stream's labels as `k="v"`, sorted by key and
joined by commas. `id` is null: a line has no identifier of its own.

The credential is sent as Basic authentication where its value is `<user>:<token>`, as the
hosted service expects, and as a bearer token otherwise. `X-Scope-OrgID` names the configured
tenant where there is one.

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: the query or a parameter is refused | `invalid` |
| 404: no such API at the address | `invalid` |
| a metric query's answer | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The API's own error text stays out of `detail`: it can quote the query.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

PATH = "/loki/api/v1/query_range"
SINCE = 15
MAX_SINCE = 44640
LIMIT = 100
MAX_LIMIT = 1000
MAX_FILTER = 2000
MAX_MESSAGE = 2000
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Config:
    target: str = ""
    """The API's address: a self-hosted store, a tenant's cloud address, or a fake's."""
    tenant: str | None = None
    """The tenant of a multi-tenant store, sent as `X-Scope-OrgID`; None sends none."""
    timeout: float = 30.0


def _whole(input: Json, name: str, default: int, top: int) -> int:
    value = input.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
        raise invalid(f"{name} must be a whole number from 1 to {top}")
    return value


def _moment(input: Json, name: str) -> datetime | None:
    value = input.get(name)
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise invalid(f"{name} must be an RFC 3339 timestamp") from error
    if moment.tzinfo is None:
        raise invalid(f"{name} must be an RFC 3339 timestamp with its offset")
    return moment.astimezone(UTC)


def _nanos(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(microseconds=1) * 1000


def rfc3339(nanos: int) -> str:
    """Nanoseconds since the epoch as RFC 3339 in UTC with `Z`, the fraction of a second to
    the nanosecond and only where there is one."""
    seconds, fraction = divmod(nanos, 1_000_000_000)
    text = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    digits = f"{fraction:09d}".rstrip("0")
    return f"{text}.{digits}Z" if digits else f"{text}Z"


def _authorization(value: str) -> str:
    if ":" in value:
        return "Basic " + base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"Bearer {value}"


async def _get(config: Config, call: Call, params: Json) -> httpx.Response:
    if not config.target:
        raise invalid("the connector names no address of the log store")
    headers = {"Authorization": _authorization(call.token)}
    if config.tenant:
        headers["X-Scope-OrgID"] = config.tenant
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers=headers,
        ) as client:
            response = await client.get(PATH, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the store did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        return response
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the store does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read these logs")
    if status == 400:
        raise invalid("the store refused the query")
    if status == 404:
        raise invalid("the address serves no range query of the store")
    if status == 429 or status >= 500:
        raise unavailable(f"the store answered {status}")
    raise TargetError("unexpected", "none", False, f"the store answered {status}")


def _source(labels: dict[str, Any]) -> str | None:
    if not labels:
        return None
    return ",".join(f'{key}="{labels[key]}"' for key in sorted(labels))


def _severity(labels: dict[str, Any]) -> str | None:
    for name in ("level", "detected_level"):
        value = labels.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _lines(body: Any) -> list[tuple[int, Json]]:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or body.get("status") != "success":
        raise TargetError("unexpected", "none", False, "the answer is not the store's")
    if data.get("resultType") != "streams":
        raise invalid("the query is a metric query; only a log query answers lines")
    result = data.get("result")
    if not isinstance(result, list):
        raise TargetError("unexpected", "none", False, "the answer's result is not a list")
    out: list[tuple[int, Json]] = []
    for stream in result:
        labels = stream.get("stream") if isinstance(stream, dict) else None
        values = stream.get("values") if isinstance(stream, dict) else None
        if not isinstance(labels, dict) or not isinstance(values, list):
            raise TargetError("unexpected", "none", False, "a stream has no labels or values")
        source, severity = _source(labels), _severity(labels)
        for value in values:
            if not isinstance(value, list) or len(value) < 2:
                raise TargetError("unexpected", "none", False, "a line is not a pair")
            try:
                nanos = int(str(value[0]))
            except ValueError as error:
                raise TargetError("unexpected", "none", False, "a line has no timestamp") from error
            entry = {
                "timestamp": rfc3339(nanos),
                "severity": severity,
                "message": str(value[1])[:MAX_MESSAGE],
                "source": source,
                "id": None,
            }
            out.append((nanos, entry))
    return out


async def entries(config: Config, call: Call, input: Json) -> Outcome:
    query = input.get("filter")
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_FILTER:
        raise invalid(f"filter must be a text of 1 to {MAX_FILTER} characters")
    if input.get("source") is not None:
        raise invalid("the store has no scope apart from the query: name the stream in `filter`")
    limit = _whole(input, "limit", LIMIT, MAX_LIMIT)
    since = _whole(input, "since_minutes", SINCE, MAX_SINCE)
    end = _moment(input, "end") or datetime.now(UTC)
    start = _moment(input, "start") or end - timedelta(minutes=since)
    if not start < end:
        raise invalid("start must be before end")
    params: Json = {
        "query": query,
        "start": str(_nanos(start)),
        "end": str(_nanos(end)),
        "limit": str(limit),
        "direction": "backward",
    }
    response = await _get(config, call, params)
    try:
        body = response.json()
    except ValueError:
        body = None
    read = _lines(body)
    read.sort(key=lambda pair: pair[0], reverse=True)
    found = [entry for _, entry in read[:limit]]
    output: Json = {
        "entries": found,
        "count": len(found),
        "complete": len(read) < limit,
        "start": rfc3339(_nanos(start)),
        "end": rfc3339(_nanos(end)),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"logs.query.entries": entries}
