"""How the Query API is asked for a report, and its answer read.

A report is one `GET /api/query/events` per metric asked — the API's *Aggregate Event Counts* —
with `project_id`, `workspace_id` where the project has data views, `event` (the events, a JSON
array), `type` (`general`, `unique` or `average`: the metric), `unit` (`day`, `week` or
`month`: the time dimension, `day` without one), `from_date` and `to_date`, and the service
account as HTTP Basic. The answer is `{"data": {"series": [...], "values": {event: {unit key:
number}}}, "legend_size": n}`: for each event, its number per unit of the range.

**No figure names a person.** The endpoint counts events and users per event and unit; it has no
breakdown by a property, so no value of a person's property reaches an output. The endpoints
that read profiles or a person's activity are never asked.

**Only what adds up truthfully.** The number of events of several events, or of several days,
is their sum. A number of unique users, or an average per user, is not: the users of two days
or of two events overlap. So `unique` and `average` need a time dimension, and either one event
or the dimension `event`; otherwise the connector refuses the report before the API is asked.

**Relative dates.** `today`, `yesterday` and `NdaysAgo` are resolved by the connector's clock in
UTC; the API counts the days in the project's time zone, so near midnight the two can differ by
a day.

How the API's answers map to the contract's causes. The reference documents the 200 answer and,
on its rate limits page, 429; it documents no error body, so only the status is read:

| Answer | Cause |
|---|---|
| 400: a parameter the API refuses | `invalid` |
| 401: the service account is not admitted | `unauthenticated` |
| 403: the service account may not read the project | `forbidden` |
| 404: no such project | `invalid` |
| 429 (over sixty queries an hour, or five at once), 5xx, no connection | `unavailable` |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://mixpanel.com"
UNITS = ("day", "week", "month")
"""The time dimensions: the API's `unit` (it also knows `minute` and `hour`, not served)."""
DIMENSIONS = (*UNITS, "event")
METRICS = ("general", "unique", "average")
"""The metrics: the API's `type`."""
SUMMABLE = frozenset({"general"})
MAX_EVENTS = 100
"""The connector's own bound on the events of one report; the reference states none."""
LIMIT = 1000
MAX_LIMIT = 10000
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2}|today|yesterday|(\d{1,4})daysAgo)$")
IDENTIFIER = re.compile(r"^\d{1,20}$")


def _today() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address: `https://mixpanel.com`, `https://eu.mixpanel.com`,
    `https://in.mixpanel.com`, or a fake's."""
    project: str = ""
    """The numeric identifier of the one project whose figures are read."""
    workspace: str = ""
    """The global data view's identifier, where the project has data views."""
    timeout: float = 30.0
    today: Callable[[], date] = field(default=_today)


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _names(input: Json, field: str, allowed: tuple[str, ...], low: int, high: int) -> list[str]:
    value = input.get(field, [])
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise invalid(f"{field} must be a list of {low} to {high} of {', '.join(allowed)}")
    unknown = [n for n in value if n not in allowed]
    if unknown:
        raise invalid(
            f"{field}: {', '.join(map(str, unknown))} the API does not count; "
            f"it knows {', '.join(allowed)}"
        )
    if len(set(value)) != len(value):
        raise invalid(f"{field} names one twice")
    return list(value)


def _events(input: Json) -> list[str]:
    value = input.get("events")
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_EVENTS
        or not all(isinstance(e, str) and e.strip() and len(e) <= 255 for e in value)
    ):
        raise invalid(f"events must be a list of 1 to {MAX_EVENTS} of the project's event names")
    if len(set(value)) != len(value):
        raise invalid("events names one twice")
    return list(value)


def _date(input: Json, field: str, today: date) -> date:
    value = input.get(field)
    match = DATE.match(value) if isinstance(value, str) else None
    if match is None:
        raise invalid(f"{field} must be YYYY-MM-DD, `today`, `yesterday` or `NdaysAgo`")
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    if match.group(2) is not None:
        return today - timedelta(days=int(match.group(2)))
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise invalid(f"{field} is no date") from error


def _project(config: Config) -> str:
    if IDENTIFIER.match(config.project) is None:
        raise invalid("the connector names no project, or not a numeric identifier")
    if config.workspace and IDENTIFIER.match(config.workspace) is None:
        raise invalid("the connector's workspace is not a numeric identifier")
    return config.project


async def _query(config: Config, call: Call, params: Json) -> Json:
    user, _, secret = call.token.partition(":")
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.get(
                "/api/query/events",
                params=params,
                auth=(user, secret),
                headers={"Accept": "application/json"},
            )
    except httpx.TimeoutException as error:
        raise unavailable(f"the API did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the secret among it.
        raise unavailable(f"the API could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            found = response.json()
        except ValueError as error:
            raise _unexpected("the API answered with a body that is not JSON") from error
        data = found.get("data") if isinstance(found, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("series"), list)
            or not isinstance(data.get("values"), dict)
        ):
            raise _unexpected("the API answered counts in a shape the connector does not know")
        return data
    if status == 401:
        raise TargetError(
            "unauthenticated", "none", False, "the API does not admit the service account"
        )
    if status == 403:
        raise TargetError(
            "forbidden", "none", False, "the service account may not read this project"
        )
    if status == 404:
        raise invalid("the API knows no such project")
    if status == 400:
        raise invalid("the API refused the report: an event, a unit or a range it refuses")
    if status == 429 or status >= 500:
        raise unavailable(f"the API answered {status}")
    raise _unexpected(f"the API answered {status}, which the connector does not foresee")


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _text(value: int | float) -> str:
    return str(value) if isinstance(value, int) else repr(float(value))


def _order(input: Json, dimensions: list[str], metrics: list[str]) -> tuple[str, bool] | None:
    order = input.get("order")
    if order is None:
        return None
    if not isinstance(order, str) or not order:
        raise invalid("order must be one of the report's names, `-` first for descending")
    desc = order.startswith("-")
    name = order[1:] if desc else order
    if name not in dimensions and name not in metrics:
        raise invalid("order must be one of the report's dimensions or metrics")
    return name, desc


async def run(config: Config, call: Call, input: Json) -> Outcome:
    events = _events(input)
    dimensions = _names(input, "dimensions", DIMENSIONS, 0, 2)
    metrics = _names(input, "metrics", METRICS, 1, len(METRICS))
    units = [d for d in dimensions if d in UNITS]
    if len(units) > 1:
        raise invalid("dimensions name at most one of day, week and month")
    by_event = "event" in dimensions
    unsummable = [m for m in metrics if m not in SUMMABLE]
    if unsummable and (not units or (len(events) > 1 and not by_event)):
        raise invalid(
            f"{', '.join(unsummable)} counts users, which do not add up across days or events: "
            "name a time dimension, and one event or the dimension `event`"
        )
    today = config.today()
    start, end = _date(input, "start", today), _date(input, "end", today)
    if start > end:
        raise invalid("start lies after end")
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    order = _order(input, dimensions, metrics)
    project = _project(config)
    base: Json = {
        "project_id": project,
        "event": json.dumps(events),
        "unit": units[0] if units else "day",
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
    }
    if config.workspace:
        base["workspace_id"] = config.workspace
    answers = {m: await _query(config, call, {**base, "type": m}) for m in metrics}
    series: list[str] = []
    for data in answers.values():
        series.extend(str(k) for k in data["series"] if str(k) not in series)
    keys: list[str] = series if units else [""]
    groups: list[str] = events if by_event else [""]
    rows: list[Json] = []
    for key in keys:
        for event in groups:
            values: Json = {}
            for metric, data in answers.items():
                counted = data["values"]
                chosen = [event] if by_event else events
                numbers = [
                    _number((counted.get(e) or {}).get(k))
                    for e in chosen
                    for k in ([key] if units else [str(s) for s in data["series"]])
                    if isinstance(counted.get(e), dict)
                ]
                found = [n for n in numbers if n is not None]
                values[metric] = sum(found) if found else None
            if all(v is None for v in values.values()):
                continue
            named: Json = {}
            if units:
                named[units[0]] = key
            if by_event:
                named["event"] = event
            rows.append(
                {
                    "dimensions": {d: named[d] for d in dimensions},
                    "metrics": {m: _text(v if v is not None else 0) for m, v in values.items()},
                }
            )
    if order is not None:
        name, desc = order
        if name in metrics:
            rows.sort(key=lambda r: float(r["metrics"][name]), reverse=desc)
        else:
            rows.sort(key=lambda r: str(r["dimensions"][name]), reverse=desc)
    output = {
        "dimensions": dimensions,
        "metrics": metrics,
        "rows": rows[:limit],
        "row_count": len(rows),
        "complete": len(rows) <= limit,
        "sampled": False,
        "thresholded": False,
        "other_row": False,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"analytics.reports.run": run}
