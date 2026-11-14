"""How the costs are asked and their answer read: `billing.costs.daily`.

The provider writes a billing account's charges into a table of its data warehouse, the
*standard usage cost export*, when the account's owner turns the export on. The connector reads
that table with one query, `POST /bigquery/v2/projects/<project>/queries`, in the dialect
GoogleSQL (`useLegacySql: false`), with the two dates as named query parameters: no input is
ever written into the query's text. The table is the connector's configuration
(`--billing-table project.dataset.table`), checked to be three plain identifiers before it is
named in the query; without one the operation is `invalid`.

The query sums each day's charges per group in the type NUMERIC, a decimal type, so that the
API answers every amount as decimal text and nothing is ever a floating-point number. The day
is the UTC date of `usage_start_time`. The groups:

| `group_by` | Column |
|---|---|
| `service` | `service.description` |
| `account` | `project.id` (empty text for a charge that belongs to no project) |
| `region` | `location.region` (empty text for a charge that has none) |

| `metric` | Amount |
|---|---|
| `unblended` | `cost` |
| `net_unblended` | `cost` plus the amounts of its `credits`, which the export writes as negative |
| `amortized` | refused as `invalid`: the standard export has no amortized column |

A day's `total` is the exact sum of its groups, computed in decimal arithmetic. A day with
amounts in more than one currency is `unexpected`, because no rule here converts. The export
never says that a day is closed: `estimated` is true for every day of the current UTC month,
whose invoice is still open.

**An unfinished query.** The API answers within its `timeoutMs`, finished or not. An answer
with `jobComplete: false` is asked again with `GET .../queries/<jobId>` (`getQueryResults`),
at most `MAX_WAITS` times; a query still running after that is `unavailable` and retryable,
because nothing was acted on. Further pages are read with the answer's `pageToken`, at most
`MAX_PAGES`.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from taktus_connectors.gcp.api import READ_ONLY, Config, bearer, project, request
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

DAYS = 29
MAX_DAYS = 92
MAX_PAGES = 10
MAX_WAITS = 3
WAIT_MS = 10_000
"""How long one request waits for the query to finish: the API's own default."""
ROWS = 1000
GROUPS = {
    "service": "service.description",
    "account": "project.id",
    "region": "location.region",
}
METRICS = ("unblended", "net_unblended", "amortized")
TABLE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]\.[A-Za-z0-9_]{1,1024}\.[A-Za-z0-9_]{1,1024}$")
"""`project.dataset.table`: a project identifier, then a dataset and a table of letters, digits
and underscores, as the export names them. Nothing else may reach the query's text."""
CREDITS = "IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC)) FROM UNNEST(credits) AS c), 0)"


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


def _table(config: Config) -> str:
    if not config.billing_table:
        raise invalid("the connector names no billing export table (--billing-table)")
    if TABLE.match(config.billing_table) is None:
        raise invalid("the billing export table is not `project.dataset.table`")
    return config.billing_table


def statement(table: str, group_by: str, metric: str) -> str:
    """The query: the table and the columns are the connector's own; the dates are parameters."""
    amount = "CAST(cost AS NUMERIC)"
    if metric == "net_unblended":
        amount = f"{amount} + {CREDITS}"
    # The table is checked against TABLE, the column and the amount are this module's own,
    # and the dates are parameters: nothing of the call's input is in the text.
    select = (
        "SELECT FORMAT_DATE('%F', DATE(usage_start_time)) AS day, "
        f"IFNULL({GROUPS[group_by]}, '') AS grp, currency, SUM({amount}) AS amount"
    )
    where = "WHERE DATE(usage_start_time) >= @start AND DATE(usage_start_time) < @end"
    return f"{select} FROM `{table}` {where} GROUP BY day, grp, currency ORDER BY day, grp"


def _amount(text: Any) -> Decimal:
    try:
        value = Decimal(str(text))
    except InvalidOperation as error:
        raise TargetError("unexpected", "none", False, "an amount is not a number") from error
    if not value.is_finite():
        raise TargetError("unexpected", "none", False, "an amount is not a finite number")
    return value


def _rows(answer: Json) -> list[list[Any]]:
    rows = answer.get("rows") or []
    if not isinstance(rows, list):
        raise TargetError("unexpected", "none", False, "the answer's rows are not a list")
    out: list[list[Any]] = []
    for row in rows:
        cells = row.get("f") if isinstance(row, dict) else None
        if not isinstance(cells, list) or len(cells) != 4:
            raise TargetError("unexpected", "none", False, "a row is not the query's four columns")
        out.append([c.get("v") if isinstance(c, dict) else None for c in cells])
    return out


async def daily(config: Config, call: Call, input: Json) -> Outcome:
    days = _days(input)
    end = _end(input)
    group_by = input.get("group_by", "service")
    if group_by not in GROUPS:
        raise invalid(f"group_by must be one of {', '.join(sorted(GROUPS))}")
    metric = input.get("metric", "unblended")
    if metric not in METRICS:
        raise invalid(f"metric must be one of {', '.join(sorted(METRICS))}")
    if metric == "amortized":
        raise invalid("the billing export has no amortized cost; ask unblended or net_unblended")
    table = _table(config)
    start = end - timedelta(days=days)
    rows, following = await rows_of(
        config, call, statement(table, str(group_by), str(metric)), start, end
    )
    output = _output(rows, start, end, str(group_by), str(metric))
    output["complete"] = not following
    return Outcome(output=output, effect={"kind": "read"})


def _parameter(name: str, kind: str, value: str) -> Json:
    return {"name": name, "parameterType": {"type": kind}, "parameterValue": {"value": value}}


async def rows_of(
    config: Config,
    call: Call,
    query: str,
    start: date,
    end: date,
    extra: list[Json] | None = None,
) -> tuple[list[list[Any]], Any]:
    """The rows of one of this connector's own queries over the export between two dates, and
    the page token left unread, if any: the query asked, waited for and paged as the module's
    text says. `extra` are further named parameters; nothing of a call's input is in `query`."""
    home = project(config)
    base = f"{config.bigquery}/bigquery/v2/projects/{home}/queries"
    token = await bearer(config, call, READ_ONLY)
    answer = await request(
        config,
        call,
        token,
        "POST",
        base,
        body={
            "query": query,
            "useLegacySql": False,
            "parameterMode": "NAMED",
            "queryParameters": [
                _parameter("start", "DATE", start.isoformat()),
                _parameter("end", "DATE", end.isoformat()),
                *(extra or []),
            ],
            "maxResults": ROWS,
            "timeoutMs": WAIT_MS,
        },
    )
    reference = answer.get("jobReference")
    job = reference.get("jobId") if isinstance(reference, dict) else None
    location = reference.get("location") if isinstance(reference, dict) else None

    async def results(page_token: str | None) -> Json:
        if not isinstance(job, str) or not job:
            raise TargetError("unexpected", "none", False, "the answer names no job")
        params: Json = {"maxResults": ROWS, "timeoutMs": WAIT_MS}
        if isinstance(location, str) and location:
            params["location"] = location
        if page_token:
            params["pageToken"] = page_token
        return await request(config, call, token, "GET", f"{base}/{job}", params=params)

    waits = 0
    while answer.get("jobComplete") is not True:
        if waits >= MAX_WAITS:
            raise unavailable("the cost query did not finish in time; nothing was acted on")
        waits += 1
        answer = await results(None)
    rows = _rows(answer)
    following = answer.get("pageToken")
    for _ in range(MAX_PAGES - 1):
        if not following:
            break
        answer = await results(str(following))
        rows.extend(_rows(answer))
        following = answer.get("pageToken")
    return rows, following


def _output(rows: list[list[Any]], start: date, end: date, group_by: str, metric: str) -> Json:
    by_date: dict[str, Json] = {}
    currencies: set[str] = set()
    month = datetime.now(UTC).date().replace(day=1)
    for day, group, currency, amount in rows:
        try:
            when = date.fromisoformat(str(day))
        except ValueError:
            raise TargetError("unexpected", "none", False, "a row names no day") from None
        if not start <= when < end:
            raise TargetError("unexpected", "none", False, "a row lies outside the days asked")
        value = _amount(amount)
        if isinstance(currency, str) and currency:
            currencies.add(currency)
        known = by_date.setdefault(
            when.isoformat(),
            {
                "date": when.isoformat(),
                "estimated": when >= month,
                "total": Decimal(0),
                "groups": [],
            },
        )
        known["total"] += value
        known["groups"].append({"group": str(group or ""), "amount": str(amount)})
    if len(currencies) > 1:
        raise TargetError("unexpected", "none", False, "the amounts are in several currencies")
    ordered = []
    for _, day in sorted(by_date.items()):
        day["total"] = format(day["total"], "f")
        day["groups"] = sorted(day["groups"], key=lambda g: g["group"])
        ordered.append(day)
    return {
        "currency": currencies.pop() if currencies else None,
        "group_by": group_by,
        "metric": metric,
        "days": ordered,
    }
