"""How a metric is asked and its answer read: `metrics.series` over the cloud's monitoring
service (ADR-0328).

The monitoring service answers PromQL over every metric it holds, the cloud's own system metrics
among them, at `POST /v1/projects/<project>/location/global/prometheus/api/v1/query` for one
moment and `.../query_range` for a range. The request body is the API's `QueryInstantRequest`
(`query`, `time`) or `QueryRangeRequest` (`query`, `start`, `end`, `step`); the answer is the
Prometheus HTTP API's: `{"status": "success", "data": {"resultType": …, "result": […]}}`. The
access token asks for the scope `monitoring.read`, the narrowest the API admits.

A system metric's type is named in PromQL by the service's own rule: the first `/` becomes `:`,
every other `.` and `/` becomes `_`, and `monitored_resource` selects the resource type where a
metric has several. The query is the call's own `query`, or the one the connector's
configuration maps the named `metric` to (`--metrics`, `serving.metric_query`): the bundles name
what they need, the tenant writes how its project answers it.

Every value is reported twice, as the metrics connector over Prometheus does: as the text the
service gave, and as a number where it is a finite one, `null` otherwise. Errors map to the
contract's causes as every request of this connector does (`api.request`); an answer with
`status: error` is `invalid`, the error type alone reported, never the service's words.
"""

from __future__ import annotations

import math
import re
from typing import Any

from taktus_connectors.gcp.api import Config, bearer, project, request
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, metric_query

type Json = dict[str, Any]

SCOPE = "https://www.googleapis.com/auth/monitoring.read"
LIMIT = 1000
MAX_LIMIT = 10_000
MOMENT = re.compile(r"^(\d{1,12}(\.\d{1,9})?|\d{4}-\d\d-\d\dT[0-9:.]+(Z|[+-]\d\d:\d\d))$")


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


def series(answer: Json, limit: int) -> Json:
    """The answer in the shape of `metrics.series`, as the Prometheus connector reports it."""
    if answer.get("status") == "error":
        raise invalid(f"the service refused the query: {answer.get('errorType', 'error')}")
    data = answer.get("data")
    if answer.get("status") != "success" or not isinstance(data, dict):
        raise TargetError("unexpected", "none", False, "the answer has no data")
    kind = data.get("resultType")
    result = data.get("result")
    found: list[Json] = []
    if kind in ("scalar", "string"):
        found.append({"labels": {}, "values": [_point(result)]})
    elif kind in ("vector", "matrix") and isinstance(result, list):
        for item in result[:limit]:
            if not isinstance(item, dict):
                raise TargetError("unexpected", "none", False, "a series is not an object")
            labels = item.get("metric") if isinstance(item.get("metric"), dict) else {}
            if kind == "vector":
                values = [_point(item.get("value"))]
            else:
                values = [_point(p) for p in item.get("values") or []]
            found.append({"labels": labels, "values": values})
    else:
        raise TargetError("unexpected", "none", False, f"an answer of type {kind!r}")
    total = len(result) if isinstance(result, list) else 1
    return {"result_type": kind, "series": found, "complete": total <= limit}


def _base(config: Config) -> str:
    return f"{config.monitoring}/v1/projects/{project(config)}/location/global/prometheus/api/v1"


async def query(config: Config, call: Call, input: Json) -> Outcome:
    body: Json = {"query": metric_query(input, config.metrics)}
    limit = _limit(input)
    if (moment := _moment(input, "time", required=False)) is not None:
        body["time"] = moment
    base = _base(config)
    token = await bearer(config, call, SCOPE)
    answer = await request(config, call, token, "POST", f"{base}/query", body=body)
    return Outcome(output=series(answer, limit), effect={"kind": "read"})


async def range_(config: Config, call: Call, input: Json) -> Outcome:
    step = input.get("step")
    if isinstance(step, bool) or not isinstance(step, int | float) or step <= 0:
        raise invalid("step must be a positive number of seconds")
    body: Json = {
        "query": metric_query(input, config.metrics),
        "start": _moment(input, "start", required=True),
        "end": _moment(input, "end", required=True),
        "step": f"{step}s",
    }
    limit = _limit(input)
    base = _base(config)
    token = await bearer(config, call, SCOPE)
    answer = await request(config, call, token, "POST", f"{base}/query_range", body=body)
    return Outcome(output=series(answer, limit), effect={"kind": "read"})
