"""How a calendar is asked and its entries within a window read.

A call names the calendar's path under the server's address (`--target`), never a host, so
that a process cannot make the connector reach any other one. Two ways to read it, chosen by the
configuration (ADR-0197 §2):

- **an iCalendar file** (RFC 5545), the default: `GET <path>`; the window is selected here;
- **CalDAV** (RFC 4791), with `--caldav`: `REPORT <path>` with `Depth: 1` and a
  `calendar-query` whose `time-range` is the window, once for `VEVENT` and once for `VTODO`;
  the `calendar-data` of every answer is read. The `multistatus` is parsed defused: an answer
  that declares a document type or an entity is refused unparsed, as the document inbox's is.

What an entry is, and how a repeating one is expanded, is `icalendar.py`'s.

The requesting identity's credential is sent as HTTP authentication: a value of the form
`user:password` as basic authentication, any other as a bearer token.

How the server's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a refused request | `invalid` |
| 401: the credential is not admitted | `unauthenticated` |
| 403: the credential may not read the calendar | `forbidden` |
| 404: no calendar at the path | `not_found` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is neither iCalendar nor a CalDAV `multistatus` | `unexpected` |
"""

from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from taktus_connectors.calendar import icalendar
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

DAYS = 30
MAX_DAYS = 400
LIMIT = 200
MAX_LIMIT = 2000
MAX_BYTES = 10 * 1024 * 1024
DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
FROM = re.compile(r"^\d{4}-\d\d-\d\d(T\d\d:\d\d(:\d\d)?(\.\d+)?(Z|[+-]\d\d:\d\d))?$")


@dataclass(frozen=True)
class Config:
    target: str
    """The calendar server's base address; a call names a path under it."""
    caldav: bool = False
    """The server answers CalDAV; otherwise the path is an iCalendar file."""
    zone: str = "UTC"
    """The zone a time without one, and a whole day, is read in."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _authorization(token: str) -> str:
    if ":" in token:
        return "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")
    return f"Bearer {token}"


def _path(input: Json) -> str:
    path = input.get("path")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or ".." in path.split("/")
        or any(ord(c) < 33 for c in path)
    ):
        raise invalid("path must be the calendar's path under the server's address, from one /")
    return path


def _window(input: Json) -> tuple[datetime, datetime]:
    days = input.get("days", DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise invalid(f"days must be a whole number from 1 to {MAX_DAYS}")
    given = input.get("from")
    if given is None:
        start = datetime.now(UTC).replace(microsecond=0)
    elif not isinstance(given, str) or FROM.match(given) is None:
        raise invalid("from must be an RFC 3339 date or moment")
    elif "T" in given:
        start = datetime.fromisoformat(given).astimezone(UTC)
    else:
        start = datetime.combine(date.fromisoformat(given), time(), tzinfo=UTC)
    return start, start + timedelta(days=days)


async def _request(
    config: Config, call: Call, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": _authorization(call.token)},
            follow_redirects=False,
        ) as client:
            response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as error:
        raise unavailable(f"the calendar did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the calendar could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status in (200, 207):
        if len(response.content) > MAX_BYTES:
            raise _unexpected(f"the calendar answered more than {MAX_BYTES} bytes")
        return response
    if status == 400:
        raise invalid("the calendar refused the request")
    if status == 401:
        raise TargetError(
            "unauthenticated", "none", False, "the server does not admit the credential"
        )
    if status == 403:
        raise TargetError("forbidden", "none", False, "the credential may not read the calendar")
    if status == 404:
        raise TargetError("not_found", "none", False, "no calendar at the path")
    if status == 429 or status >= 500:
        raise unavailable(f"the calendar answered {status}")
    raise _unexpected(f"the calendar answered {status}")


def _query(kind: str, start: datetime, end: datetime) -> bytes:
    moment = "%Y%m%dT%H%M%SZ"
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<C:calendar-query xmlns:D="{DAV}" xmlns:C="{CALDAV}">'
        "<D:prop><C:calendar-data/></D:prop>"
        f'<C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="{kind}">'
        f'<C:time-range start="{start.strftime(moment)}" end="{end.strftime(moment)}"/>'
        "</C:comp-filter></C:comp-filter></C:filter></C:calendar-query>"
    ).encode()


def _calendar_data(content: bytes) -> list[str]:
    if FORBIDDEN.search(content):
        raise _unexpected("the calendar answered with a document type or an entity; refused")
    try:
        # Defused: a document type or an entity was refused above, before parsing.
        root = ElementTree.fromstring(content)  # noqa: S314
    except ElementTree.ParseError as error:
        raise _unexpected("the calendar's answer is not a CalDAV multistatus") from error
    if root.tag != f"{{{DAV}}}multistatus":
        raise _unexpected("the calendar's answer is not a CalDAV multistatus")
    return [
        data.text
        for data in root.iter(f"{{{CALDAV}}}calendar-data")
        if data.text and data.text.strip()
    ]


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    path = _path(input)
    start, end = _window(input)
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    zone = ZoneInfo(config.zone)
    if config.caldav:
        texts: list[str] = []
        for kind in ("VEVENT", "VTODO"):
            response = await _request(
                config,
                call,
                "REPORT",
                path,
                content=_query(kind, start, end),
                headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
            )
            texts.extend(_calendar_data(response.content))
    else:
        texts = [(await _request(config, call, "GET", path)).text]
    found: list[Json] = []
    unread: list[Json] = []
    seen: set[str] = set()
    for text in texts:
        try:
            read = icalendar.entries(text, start, end, zone)
        except icalendar.Unreadable as error:
            raise _unexpected(f"the calendar's answer is not iCalendar: {error}") from error
        for entry in read["entries"]:
            if entry["key"] not in seen:  # a to-do and an event answer the same object once
                seen.add(entry["key"])
                found.append(entry)
        unread.extend(read["unread"])
    found.sort(key=lambda e: (e["at"], e["uid"]))
    return Outcome(
        output={
            "from": _utc(start),
            "until": _utc(end),
            "entries": found[:limit],
            "unread": unread,
            "complete": len(found) <= limit,
        },
        effect={"kind": "read"},
    )


def _utc(at: datetime) -> str:
    return at.isoformat(timespec="seconds").replace("+00:00", "Z")


OPERATIONS = {"calendar.events.list": list_}
