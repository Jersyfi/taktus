"""How log entries are asked and their answer read: `logs.query.entries`.

The logging API lists entries at `POST /v2/entries:list` with the parent resources
(`resourceNames`, here the one project), a filter, an order (`timestamp desc`, newest first), a
page size and a `pageToken`; an answer names `entries` and, while more may exist, a
`nextPageToken`. The call's filter is passed verbatim in parentheses, and the window is added
to it as two comparisons of `timestamp`.

Each entry is normalised to five fields. The message is the text payload; else the structured
payload's `message`; else that payload as compact JSON. Of an audit entry, whose payload is a
protocol buffer, only the method it records is copied, `methodName`, and never who called it:
no figure here may assess a named person (principle 14).

`source` is refused as `invalid`: the logging API's scope is the project the connector names,
and a log is chosen in the filter (`logName="projects/<project>/logs/<log>"`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from taktus_connectors.gcp.api import READ_ONLY, Config, bearer, instant, project, request, stamp
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

PATH = "/v2/entries:list"
SINCE = 15
MAX_SINCE = 44640
LIMIT = 100
MAX_LIMIT = 1000
MAX_FILTER = 2000
MAX_MESSAGE = 2000
MAX_PAGES = 10
"""The logging API may answer a page with fewer entries than asked, even none, and a token;
at most this many pages are read."""


def _whole(input: Json, name: str, default: int, top: int) -> int:
    value = input.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
        raise invalid(f"{name} must be a whole number from 1 to {top}")
    return value


def _moment(input: Json, name: str) -> datetime | None:
    value = input.get(name)
    if value is None:
        return None
    moment = instant(value)
    if moment is None:
        raise invalid(f"{name} must be an RFC 3339 timestamp with its offset")
    return moment


def window(input: Json, now: datetime) -> tuple[datetime, datetime]:
    """The window the call asks: `start` to `end` (default now), or `since_minutes` back."""
    start = _moment(input, "start")
    end = _moment(input, "end")
    since = _whole(input, "since_minutes", SINCE, MAX_SINCE)
    if start is None:
        if end is not None:
            raise invalid("end is given only with start")
        return now - timedelta(minutes=since), now
    end = end or now
    if start >= end:
        raise invalid("start must be before end")
    return start, end


def message(entry: Json) -> str:
    """The entry's message, at most `MAX_MESSAGE` characters; never the person an audit names."""
    text: Any = entry.get("textPayload")
    payload = entry.get("jsonPayload")
    proto = entry.get("protoPayload")
    if not isinstance(text, str):
        if isinstance(payload, dict):
            found = payload.get("message")
            text = (
                found
                if isinstance(found, str)
                else json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            )
        elif isinstance(proto, dict) and isinstance(proto.get("methodName"), str):
            text = proto["methodName"]
        else:
            text = ""
    return str(text)[:MAX_MESSAGE]


def entry(item: Any) -> Json:
    """The five fields a process judges an entry by."""
    if not isinstance(item, dict):
        raise TargetError("unexpected", "none", False, "an entry is not an object")
    moment = instant(item.get("timestamp")) or instant(item.get("receiveTimestamp"))
    if moment is None:
        raise TargetError("unexpected", "none", False, "an entry has no timestamp")
    severity = item.get("severity")
    log = item.get("logName")
    id = item.get("insertId")
    return {
        "timestamp": stamp(moment),
        "severity": severity if isinstance(severity, str) else None,
        "message": message(item),
        "source": log if isinstance(log, str) else None,
        "id": id if isinstance(id, str) else None,
    }


async def entries(config: Config, call: Call, input: Json) -> Outcome:
    query = input.get("filter")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_FILTER:
        raise invalid(f"filter must be a text of 1 to {MAX_FILTER} characters")
    if input.get("source") is not None:
        raise invalid("source is not taken here: the scope is the project; name a log in filter")
    start, end = window(input, datetime.now(UTC))
    limit = _whole(input, "limit", LIMIT, MAX_LIMIT)
    body: Json = {
        "resourceNames": [f"projects/{project(config)}"],
        "filter": f'({query}) AND timestamp >= "{stamp(start)}" AND timestamp <= "{stamp(end)}"',
        "orderBy": "timestamp desc",
    }
    token = await bearer(config, call, READ_ONLY)
    found: list[Json] = []
    following: Any = None
    for _ in range(MAX_PAGES):
        asked = {**body, "pageSize": limit - len(found)}
        if following:
            asked["pageToken"] = following
        page = await request(config, call, token, "POST", config.logging + PATH, body=asked)
        items = page.get("entries") or []
        if not isinstance(items, list):
            raise TargetError("unexpected", "none", False, "the answer's entries are not a list")
        found.extend(entry(item) for item in items)
        following = page.get("nextPageToken")
        if not following or len(found) >= limit:
            break
    complete = not following and len(found) <= limit
    listed = found[:limit]
    output = {
        "entries": listed,
        "count": len(listed),
        "complete": complete,
        "start": stamp(start),
        "end": stamp(end),
    }
    return Outcome(output=output, effect={"kind": "read"})
