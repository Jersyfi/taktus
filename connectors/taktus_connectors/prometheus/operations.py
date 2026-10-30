"""How a query is asked and its answer read.

The query API answers `GET /api/v1/query` for one moment and `GET /api/v1/query_range` for a
range, with a JSON body `{"status": "success", "data": {"resultType": …, "result": […]}}` or
`{"status": "error", "errorType": …, "error": …}`. The requesting identity's token is sent as a
bearer token; a store that admits anyone ignores it.

Every value is reported twice: as the text the store gave, which keeps `NaN` and `+Inf`, and as
a number where it is a finite one, `null` otherwise. A step that measures a signal reads the
number (ADR-0109); the text is what the store said.

How the store's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: the query cannot be parsed or executed | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The store's own words stay out of `detail` beyond its error type: they can quote the query.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus.adapters.driven.connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

LIMIT = 1000
"""How many series an answer reports when the call names no `limit`."""
MAX_LIMIT = 10_000
MOMENT = re.compile(r"^(\d{1,12}(\.\d{1,9})?|\d{4}-\d\d-\d\dT[0-9:.]+(Z|[+-]\d\d:\d\d))$")


@dataclass(frozen=True)
class Config:
    target: str
    """The store's base address; the query API is under `/api/v1`."""
    timeout: float = 30.0


def _query(input: Json) -> str:
    query = input.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 20_000:
        raise invalid("query must be a text of at most 20000 characters")
    return query


def _moment(input: Json, name: str, *, required: bool) -> str | None:
    value = input.get(name)
    if value is None and not required:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or MOMENT.match(value) is None:
        raise invalid(f"{name} must be seconds since the epoch or an RFC 3339 moment")
    return value


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


def _number(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _point(pair: Any) -> Json:
    if not isinstance(pair, list) or len(pair) != 2:
        raise TargetError("unexpected", "none", False, "a sample is not [moment, value]")
    return {"at": pair[0], "value": _number(pair[1]), "text": str(pair[1])}


async def _ask(config: Config, call: Call, path: str, params: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.get(path, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the store did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the store does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read this store")
    if status == 429 or status >= 500:
        raise unavailable(f"the store answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.get("status") not in ("success", "error"):
        raise TargetError(
            "unexpected", "none", False, f"the store answered {status} with a body it does not use"
        )
    if status in (400, 422) or body.get("status") == "error":
        if status not in (200, 400, 422):
            raise TargetError("unexpected", "none", False, f"the store answered {status}")
        raise invalid(f"the store refused the query: {body.get('errorType', 'error')}")
    if status != 200:
        raise TargetError("unexpected", "none", False, f"the store answered {status}")
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("resultType"), str):
        raise TargetError("unexpected", "none", False, "the answer has no data")
    return data


def _series(data: Json, limit: int) -> Json:
    kind = data["resultType"]
    result = data.get("result")
    series: list[Json] = []
    if kind in ("scalar", "string"):
        series.append({"labels": {}, "values": [_point(result)]})
    elif kind in ("vector", "matrix") and isinstance(result, list):
        for item in result[:limit]:
            if not isinstance(item, dict):
                raise TargetError("unexpected", "none", False, "a series is not an object")
            labels = item.get("metric") if isinstance(item.get("metric"), dict) else {}
            if kind == "vector":
                values = [_point(item.get("value"))]
            else:
                values = [_point(p) for p in item.get("values") or []]
            series.append({"labels": labels, "values": values})
    else:
        raise TargetError("unexpected", "none", False, f"an answer of type {kind!r}")
    total = len(result) if isinstance(result, list) else 1
    return {"result_type": kind, "series": series, "complete": total <= limit}


async def query(config: Config, call: Call, input: Json) -> Outcome:
    params: Json = {"query": _query(input)}
    limit = _limit(input)
    if (moment := _moment(input, "time", required=False)) is not None:
        params["time"] = moment
    data = await _ask(config, call, "/api/v1/query", params)
    return Outcome(output=_series(data, limit), effect={"kind": "read"})


async def range_(config: Config, call: Call, input: Json) -> Outcome:
    step = input.get("step")
    if isinstance(step, bool) or not isinstance(step, int | float) or step <= 0:
        raise invalid("step must be a positive number of seconds")
    params: Json = {
        "query": _query(input),
        "start": _moment(input, "start", required=True),
        "end": _moment(input, "end", required=True),
        "step": str(step),
    }
    limit = _limit(input)
    data = await _ask(config, call, "/api/v1/query_range", params)
    return Outcome(output=_series(data, limit), effect={"kind": "read"})


OPERATIONS = {"metrics.series.query": query, "metrics.series.range": range_}
