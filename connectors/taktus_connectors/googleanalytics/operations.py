"""How the analytics API is asked for a report, and its answer read.

A report is `POST /v1beta/properties/<property>:runReport` with `dimensions`, `metrics` (each
`{"name": ...}`), one `dateRanges` entry, `limit` and `orderBys`, and the service account's
access token as a bearer token (`auth.py`). The answer's rows carry `dimensionValues` and
`metricValues`, each `{"value": ...}` in the order of `dimensionHeaders` and `metricHeaders`;
`rowCount` counts every row the report has; `metadata` says whether the figures were sampled
(`samplingMetadatas`), withheld below a threshold (`subjectToThresholding`) or grouped into an
"(other)" row (`dataLossFromOtherRow`).

**No dimension that can name a person.** The API's own dimensions aggregate; none of them is a
person's identifier (`signedInWithUserId` is a yes or no, not the identifier). A user-scoped
custom dimension, `customUser:<parameter>`, carries whatever the business stored on the user,
an address among it. It is refused before the API is asked: an analysis reads a copy without
personal fields (UC-7.7).

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a name or a range the API refuses | `invalid` |
| 404: no such property | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the service account may not read the property | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The API's own `message` stays out of the error's `detail`: it can quote the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.googleanalytics.auth import access_token
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://analyticsdata.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
MAX_DIMENSIONS = 9
""""You can use up to nine dimensions per request" (the API's report basics)."""
MAX_METRICS = 10
""""Requests are allowed up to 10 metrics" (the API's Metric reference)."""
LIMIT = 1000
MAX_LIMIT = 10000
PERSONAL = ("customUser:",)
"""The prefixes of dimensions that can name a person: a user-scoped custom dimension."""
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_:]{0,99}$")
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2}|today|yesterday|\d{1,4}daysAgo)$")
PROPERTY = re.compile(r"^\d{1,20}$")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; Google's own, or a fake's."""
    property: str = ""
    """The numeric identifier of the one property whose figures are read."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _names(input: Json, field: str, low: int, high: int) -> list[str]:
    value = input.get(field, [])
    if (
        not isinstance(value, list)
        or not low <= len(value) <= high
        or not all(isinstance(n, str) and NAME.match(n) for n in value)
    ):
        raise invalid(f"{field} must be a list of {low} to {high} of the API's names")
    if len(set(value)) != len(value):
        raise invalid(f"{field} names one twice")
    return list(value)


def _date(input: Json, field: str) -> str:
    value = input.get(field)
    if not isinstance(value, str) or DATE.match(value) is None:
        raise invalid(f"{field} must be YYYY-MM-DD, `today`, `yesterday` or `NdaysAgo`")
    return value


def _order(input: Json, dimensions: list[str], metrics: list[str]) -> list[Json]:
    """`order`: a name of the report's, optionally `-` first for descending."""
    order = input.get("order")
    if order is None:
        return []
    if not isinstance(order, str) or not order:
        raise invalid("order must be one of the report's names, `-` first for descending")
    desc = order.startswith("-")
    name = order[1:] if desc else order
    if name in metrics:
        return [{"metric": {"metricName": name}, "desc": desc}]
    if name in dimensions:
        return [{"dimension": {"dimensionName": name}, "desc": desc}]
    raise invalid("order must be one of the report's dimensions or metrics")


def _property(config: Config) -> str:
    if PROPERTY.match(config.property) is None:
        raise invalid("the connector names no property, or not a numeric identifier")
    return config.property


async def _report(config: Config, call: Call, token: str, body: Json) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.post(
                f"/v1beta/properties/{_property(config)}:runReport", json=body
            )
    except httpx.TimeoutException as error:
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            found = response.json()
        except ValueError as error:
            raise _unexpected("the API answered with a body that is not JSON") from error
        if not isinstance(found, dict):
            raise _unexpected("the API answered a report in a shape the connector does not know")
        return found
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the API does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not read this property")
    if status == 404:
        raise invalid("the API knows no such property")
    if status == 400:
        raise invalid("the API refused the report: a name or a range it does not know")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _values(row: Json, field: str, names: list[str]) -> Json:
    values = row.get(field) or []
    if not isinstance(values, list) or len(values) != len(names):
        raise _unexpected("a row of the report does not match its headers")
    return {
        name: (v.get("value") if isinstance(v, dict) else None)
        for name, v in zip(names, values, strict=True)
    }


async def run(config: Config, call: Call, input: Json) -> Outcome:
    dimensions = _names(input, "dimensions", 0, MAX_DIMENSIONS)
    metrics = _names(input, "metrics", 1, MAX_METRICS)
    personal = [d for d in dimensions if d.startswith(PERSONAL)]
    if personal:
        raise invalid(
            f"{', '.join(personal)} can name a person; a report reads aggregates only (UC-7.7)"
        )
    start, end = _date(input, "start"), _date(input, "end")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    body: Json = {
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "dateRanges": [{"startDate": start, "endDate": end}],
        "limit": str(limit),
    }
    order = _order(input, dimensions, metrics)
    if order:
        body["orderBys"] = order
    _property(config)
    token = await access_token(call, SCOPE, config.timeout)
    found = await _report(config, call, token, body)
    rows = found.get("rows") or []
    if not isinstance(rows, list):
        raise _unexpected("the report's rows are not a list")
    out = [
        {
            "dimensions": _values(row, "dimensionValues", dimensions),
            "metrics": _values(row, "metricValues", metrics),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    try:
        count = int(found.get("rowCount", len(out)))
    except (TypeError, ValueError):
        count = len(out)
    metadata = found.get("metadata") or {}
    output = {
        "dimensions": dimensions,
        "metrics": metrics,
        "rows": out,
        "row_count": count,
        "complete": count <= len(out),
        "sampled": bool(metadata.get("samplingMetadatas")),
        "thresholded": bool(metadata.get("subjectToThresholding")),
        "other_row": bool(metadata.get("dataLossFromOtherRow")),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"analytics.reports.run": run}
