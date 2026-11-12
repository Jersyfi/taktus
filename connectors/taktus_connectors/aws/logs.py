"""How a log query is asked and its answer read: `logs.query.entries` over CloudWatch Logs.

The API answers `POST /` with `X-Amz-Target: Logs_20140328.FilterLogEvents`, signed for the
service `logs` in the configured region. The connector names the log group (`logGroupName`),
passes the call's `filter` verbatim as `filterPattern`, and the window as `startTime` and
`endTime` in milliseconds since the epoch. `startFromHead` is false, so that the newest events
come first; the provider supports that only for a `startTime` on or after 2024-01-01 and
refuses an earlier one, which the connector reports as `invalid`.

The provider documents that a page may be partly full or even empty while it still names a
`nextToken`, and that only an answer without a `nextToken` ends the list. The connector
therefore follows `nextToken` past an empty page, up to `MAX_PAGES` requests, asking each time
for no more than the entries still missing.

CloudWatch Logs gives an event no severity: `severity` is null. `source` is the event's log
stream, `id` its `eventId`. Logs Insights (`StartQuery`, `GetQueryResults`) is not used: a
query there runs asynchronously and is polled for its result, which one bounded read does not
fit (README).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from taktus_connectors.aws.api import Config, from_epoch, key_of, post, rfc3339
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

SERVICE = "logs"
ACTION = "Logs_20140328.FilterLogEvents"
SINCE = 15
MAX_SINCE = 44640
LIMIT = 100
MAX_LIMIT = 1000
MAX_FILTER = 1024
"""The longest `filterPattern` the provider takes; the contract's longer filter is refused."""
MAX_MESSAGE = 2000
MAX_PAGES = 20
"""How many requests one read makes at most; empty pages count."""
GROUP = re.compile(r"^[.\-_/#A-Za-z0-9]{1,512}$")
"""A log group's name as the provider's `logGroupName` pattern admits it."""


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


def window(input: Json) -> tuple[datetime, datetime]:
    """The window a log query asks: `start` to `end` (default now) where `start` is given,
    otherwise the `since_minutes` (default 15) before `end`."""
    since = _whole(input, "since_minutes", SINCE, MAX_SINCE)
    end = _moment(input, "end") or datetime.now(UTC)
    start = _moment(input, "start") or end - timedelta(minutes=since)
    if not start < end:
        raise invalid("start must be before end")
    return start, end


def _filter(input: Json) -> str:
    value = input.get("filter")
    if not isinstance(value, str) or not 1 <= len(value) <= 2000:
        raise invalid("filter must be a text of 1 to 2000 characters")
    if len(value) > MAX_FILTER:
        raise invalid(f"the provider takes a filter pattern of at most {MAX_FILTER} characters")
    return value


def _group(config: Config, input: Json) -> str:
    group = input.get("source", config.log_group)
    if group is None or group == "":
        raise invalid("the call names no `source` and the connector no log group")
    if not isinstance(group, str) or GROUP.match(group) is None:
        raise invalid("source must be a log group's name")
    return group


def _millis(moment: datetime) -> int:
    return (moment - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)


def _entry(event: Any) -> tuple[int, Json]:
    if not isinstance(event, dict):
        raise TargetError("unexpected", "none", False, "an event is not an object")
    stamp = event.get("timestamp")
    at = from_epoch(stamp, 1000)
    if at is None or isinstance(stamp, bool) or not isinstance(stamp, int):
        raise TargetError("unexpected", "none", False, "an event has no timestamp")
    stream = event.get("logStreamName")
    id = event.get("eventId")
    return stamp, {
        "timestamp": rfc3339(at),
        "severity": None,
        "message": str(event.get("message") or "")[:MAX_MESSAGE],
        "source": stream if isinstance(stream, str) else None,
        "id": id if isinstance(id, str) else None,
    }


async def entries(config: Config, call: Call, input: Json) -> Outcome:
    query = _filter(input)
    limit = _whole(input, "limit", LIMIT, MAX_LIMIT)
    group = _group(config, input)
    start, end = window(input)
    key = key_of(call)
    body: Json = {
        "logGroupName": group,
        "filterPattern": query,
        "startTime": _millis(start),
        "endTime": _millis(end),
        "startFromHead": False,
    }
    read: list[tuple[int, Json]] = []
    token: Any = None
    for _ in range(MAX_PAGES):
        asked = {**body, "limit": limit - len(read)}
        if token:
            asked["nextToken"] = token
        answer = await post(
            config,
            call,
            key,
            address=config.logs(),
            region=config.services_region,
            service=SERVICE,
            action=ACTION,
            body=asked,
            what="this log group",
        )
        events = answer.get("events", [])
        if not isinstance(events, list):
            raise TargetError("unexpected", "none", False, "the answer's events are not a list")
        read.extend(_entry(event) for event in events)
        token = answer.get("nextToken")
        if not token or len(read) >= limit:
            break
    complete = not token and len(read) <= limit
    read.sort(key=lambda pair: pair[0], reverse=True)
    found = [entry for _, entry in read[:limit]]
    output: Json = {
        "entries": found,
        "count": len(found),
        "complete": complete,
        "start": rfc3339(start),
        "end": rfc3339(end),
    }
    return Outcome(output=output, effect={"kind": "read"})
