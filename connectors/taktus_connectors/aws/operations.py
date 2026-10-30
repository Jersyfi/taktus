"""How the costs are asked and their answer read.

The Cost Explorer API answers one JSON request, `POST /` with the header
`X-Amz-Target: AWSInsightsIndexService.GetCostAndUsage`, signed with Signature Version 4 for
the service `ce` (`signing.py`). The connector asks for daily costs grouped by one dimension
and reads `ResultsByTime`, page after page while the answer names a `NextPageToken`, up to ten.

Every amount stays the decimal text the provider gave. A day's `total` is the exact sum of its
groups, computed in decimal arithmetic, never in floating point: a figure a later step holds
`exact` is built from it (CLAUDE.md §4). A day with amounts in more than one currency is not
summed: the answer is `unexpected`, because no rule here converts.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| a refusal of the request, an error type in `INVALID` | `invalid` |
| the key is not admitted, an error type in `UNAUTHENTICATED`, or 401 | `unauthenticated` |
| `AccessDeniedException`, or 403 without one of the above | `forbidden` |
| an error type in `UNAVAILABLE`, 429, 5xx, no answer in time | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its error type is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from taktus_connectors.aws.signing import Key, signed_headers
from taktus_connectors.serving import (
    Call,
    Outcome,
    TargetError,
    invalid,
    unavailable,
)

type Json = dict[str, Any]

TARGET = "https://ce.us-east-1.amazonaws.com"
REGION = "us-east-1"
SERVICE = "ce"
ACTION = "AWSInsightsIndexService.GetCostAndUsage"
DAYS = 29
"""The day judged and the 28 before it: four weeks of history for a median."""
MAX_DAYS = 92
MAX_PAGES = 10
GROUPS = {"service": "SERVICE", "account": "LINKED_ACCOUNT", "region": "REGION"}
METRICS = {
    "unblended": "UnblendedCost",
    "amortized": "AmortizedCost",
    "net_unblended": "NetUnblendedCost",
}
INVALID = {
    "ValidationException",
    "DataUnavailableException",
    "InvalidNextTokenException",
    "BillExpirationException",
    "RequestChangedException",
}
UNAUTHENTICATED = {
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "IncompleteSignature",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "MissingAuthenticationToken",
}
UNAVAILABLE = {"LimitExceededException", "ThrottlingException", "ServiceUnavailable"}


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    region: str = REGION
    timeout: float = 30.0


def _days(input: Json) -> int:
    days = input.get("days", DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise invalid(f"days must be a whole number from 1 to {MAX_DAYS}")
    return days


def _end(input: Json) -> date:
    end = input.get("end")
    if end is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(str(end))
    except ValueError as error:
        raise invalid("end must be a date, YYYY-MM-DD") from error


def _choice(input: Json, name: str, table: dict[str, str], default: str) -> str:
    value = input.get(name, default)
    if value not in table:
        raise invalid(f"{name} must be one of {', '.join(sorted(table))}")
    return str(value)


def _amount(text: Any) -> Decimal:
    try:
        value = Decimal(str(text))
    except InvalidOperation as error:
        raise TargetError("unexpected", "none", False, "an amount is not a number") from error
    if not value.is_finite():
        raise TargetError("unexpected", "none", False, "an amount is not a finite number")
    return value


def _error_type(response: httpx.Response) -> str:
    kind = response.headers.get("x-amzn-errortype", "")
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        kind = str(body.get("__type") or body.get("code") or kind)
    return str(kind).split("#")[-1].split(":")[0].strip()


async def _page(config: Config, call: Call, key: Key, body: Json) -> Json:
    url = httpx.URL(config.target.rstrip("/") + "/")
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = signed_headers(
        key,
        host=url.netloc.decode("ascii"),
        path=url.path,
        headers={"content-type": "application/x-amz-json-1.1", "x-amz-target": ACTION},
        body=data,
        region=config.region,
        service=SERVICE,
        at=datetime.now(UTC),
    )
    call.count()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
        ) as client:
            response = await client.post(url, content=data, headers=headers)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            answer = response.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict) or not isinstance(answer.get("ResultsByTime"), list):
            raise TargetError("unexpected", "none", False, "the answer has no ResultsByTime")
        return answer
    kind = _error_type(response)
    if kind in UNAUTHENTICATED or status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if kind == "AccessDeniedException" or status == 403:
        raise TargetError("forbidden", "none", False, "the key may not read the costs")
    if kind in UNAVAILABLE or status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status} {kind}".rstrip())
    if kind in INVALID and status == 400:
        raise invalid(f"the provider refused the request: {kind}")
    raise TargetError("unexpected", "none", False, f"the provider answered {status} {kind}")


def _day(result: Any, metric: str) -> Json:
    if not isinstance(result, dict) or not isinstance(result.get("TimePeriod"), dict):
        raise TargetError("unexpected", "none", False, "a result names no time period")
    groups: list[Json] = []
    units: set[str] = set()
    total = Decimal(0)
    for group in result.get("Groups") or []:
        keys = group.get("Keys") if isinstance(group, dict) else None
        figure = (group.get("Metrics") or {}).get(metric) if isinstance(group, dict) else None
        if not isinstance(keys, list) or not isinstance(figure, dict):
            raise TargetError("unexpected", "none", False, "a group has no keys or no amount")
        text = str(figure.get("Amount"))
        total += _amount(text)
        units.add(str(figure.get("Unit")))
        groups.append({"group": " / ".join(str(k) for k in keys), "amount": text})
    if len(units) > 1:
        raise TargetError("unexpected", "none", False, "a day's amounts are in several currencies")
    return {
        "date": str(result["TimePeriod"].get("Start")),
        "estimated": bool(result.get("Estimated")),
        "total": format(total, "f"),
        "groups": sorted(groups, key=lambda g: g["group"]),
        "currency": units.pop() if units else None,
    }


async def daily(config: Config, call: Call, input: Json) -> Outcome:
    days = _days(input)
    end = _end(input)
    group_by = _choice(input, "group_by", GROUPS, "service")
    metric = _choice(input, "metric", METRICS, "unblended")
    key = Key.parse(call.token)
    if key is None:
        raise TargetError(
            "unauthenticated",
            "none",
            False,
            "the credential is not `<access key id>:<secret access key>[:<session token>]`",
        )
    body: Json = {
        "TimePeriod": {
            "Start": (end - timedelta(days=days)).isoformat(),
            "End": end.isoformat(),
        },
        "Granularity": "DAILY",
        "Metrics": [METRICS[metric]],
        "GroupBy": [{"Type": "DIMENSION", "Key": GROUPS[group_by]}],
    }
    read: list[Json] = []
    token: Any = None
    for _ in range(MAX_PAGES):
        asked = {**body, "NextPageToken": token} if token else body
        answer = await _page(config, call, key, asked)
        read.extend(_day(r, METRICS[metric]) for r in answer["ResultsByTime"])
        token = answer.get("NextPageToken")
        if not token:
            break
    by_date: dict[str, Json] = {}
    for day in read:  # a day split across pages is joined
        known = by_date.get(day["date"])
        if known is None:
            by_date[day["date"]] = day
            continue
        if day["currency"] and known["currency"] and day["currency"] != known["currency"]:
            raise TargetError(
                "unexpected", "none", False, "a day's amounts are in several currencies"
            )
        known["groups"] = sorted(known["groups"] + day["groups"], key=lambda g: g["group"])
        known["total"] = format(_amount(known["total"]) + _amount(day["total"]), "f")
        known["currency"] = known["currency"] or day["currency"]
        known["estimated"] = known["estimated"] or day["estimated"]
    currencies = {d["currency"] for d in by_date.values() if d["currency"]}
    if len(currencies) > 1:
        raise TargetError("unexpected", "none", False, "the days are in several currencies")
    ordered = [
        {k: v for k, v in day.items() if k != "currency"} for _, day in sorted(by_date.items())
    ]
    output: Json = {
        "currency": currencies.pop() if currencies else None,
        "group_by": group_by,
        "metric": metric,
        "days": ordered,
        "complete": not token,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"billing.costs.daily": daily}
