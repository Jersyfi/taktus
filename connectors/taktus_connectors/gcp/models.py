"""The cloud's model service: `models.costs` and `models.catalogue` (ADR-0330).

**Costs.** The model service publishes no costs API of its own. What it charges is written into
the billing export like every other service of the cloud, under the service's description in
the export, `Vertex AI` unless the connector is configured otherwise (`--model-service`). So
`models.costs.daily` is the export's query of `billing.costs`, kept to that one service by a
named query parameter and grouped by `line_item` — the SKU's description, what the export names
each charge — or by `project`. The amounts are summed as NUMERIC, as decimal text; each day's
`total` is their exact sum; `estimated` marks a day of the current month. Credits are left out:
the amount is the charge, as the model providers' cost reports state theirs.

**Catalogue.** `GET /v1beta1/publishers/google/models` lists the provider's own models, page by
page. A model is reported as `models.catalogue` reports every provider's: `{id, name,
created_at, lifecycle, deprecated_at, retires_at}`. The API states a model's launch stage
(`EXPERIMENTAL`, `PRIVATE_PREVIEW`, `PUBLIC_PREVIEW`, `GA`), which becomes `lifecycle` in
lowercase. It states **no deprecation and no retirement date**: those are on the provider's
documentation pages only. `deprecated_at` and `retires_at` are therefore always null, `retiring`
is always empty, and a model the provider retired is seen only when it is no longer listed —
which is how the retired-models process (B-2.04) reads a model in use that is missing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from taktus_connectors.gcp import billing
from taktus_connectors.gcp.api import FULL, Config, bearer, request
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

GROUPS = {"line_item": "sku.description", "project": "project.id"}
MAX_MODELS = 1000
PAGE = 100
MAX_PAGES = 10
PATH = "/v1beta1/publishers/google/models"


def statement(table: str, group_by: str) -> str:
    """The query: the table is checked, the column is this module's own, the service and the
    dates are parameters."""
    select = (
        "SELECT FORMAT_DATE('%F', DATE(usage_start_time)) AS day, "
        f"IFNULL({GROUPS[group_by]}, '') AS grp, currency, SUM(CAST(cost AS NUMERIC)) AS amount"
    )
    where = (
        "WHERE DATE(usage_start_time) >= @start AND DATE(usage_start_time) < @end "
        "AND service.description = @service"
    )
    return f"{select} FROM `{table}` {where} GROUP BY day, grp, currency ORDER BY day, grp"


async def costs(config: Config, call: Call, input: Json) -> Outcome:
    days = billing._days(input)
    end = billing._end(input)
    group_by = input.get("group_by", "line_item")
    if group_by not in GROUPS:
        raise invalid(f"group_by must be one of {', '.join(sorted(GROUPS))}")
    table = billing._table(config)
    start = end - timedelta(days=days)
    rows, following = await billing.rows_of(
        config,
        call,
        statement(table, str(group_by)),
        start,
        end,
        [billing._parameter("service", "STRING", config.model_service)],
    )
    summed = billing._output(rows, start, end, str(group_by), "unblended")
    output: Json = {
        "currency": summed["currency"],
        "group_by": group_by,
        "days": summed["days"],
        "complete": not following,
    }
    return Outcome(output=output, effect={"kind": "read"})


def _model(entry: Any) -> Json:
    name = entry.get("name") if isinstance(entry, dict) else None
    if not isinstance(name, str) or not name.startswith("publishers/") or "/models/" not in name:
        raise TargetError("unexpected", "none", False, "a model names no resource name")
    stage = entry.get("launchStage")
    return {
        "id": name.rsplit("/", 1)[1],
        "name": None,
        "created_at": None,
        "lifecycle": stage.lower() if isinstance(stage, str) and stage else None,
        "deprecated_at": None,
        "retires_at": None,
    }


async def catalogue(config: Config, call: Call, input: Json) -> Outcome:
    limit = input.get("limit", MAX_MODELS)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_MODELS:
        raise invalid(f"limit must be a whole number from 1 to {MAX_MODELS}")
    token = await bearer(config, call, FULL)
    models: list[Json] = []
    params: Json = {"pageSize": PAGE}
    following: Any = None
    for _ in range(MAX_PAGES):
        answer = await request(
            config, call, token, "GET", f"{config.aiplatform}{PATH}", params=params
        )
        listed = answer.get("publisherModels") or []
        if not isinstance(listed, list):
            raise TargetError("unexpected", "none", False, "the models are not a list")
        models.extend(_model(entry) for entry in listed)
        following = answer.get("nextPageToken")
        if not following:
            break
        params = {**params, "pageToken": following}
    ordered = sorted({m["id"]: m for m in models}.values(), key=lambda m: m["id"])
    kept = ordered[:limit]
    output: Json = {
        "models": kept,
        "ids": [m["id"] for m in kept],
        "retiring": [],
        "current": [m["id"] for m in kept],
        "complete": not following and len(kept) == len(ordered),
    }
    return Outcome(output=output, effect={"kind": "read"})
