"""What the cloud operations connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

Seven capabilities of one cloud project, every operation of effect `read`: reading log entries,
costs, the metadata of secrets, metrics, the model catalogue or the expiry of keys changes
nothing. Each request
is one unit, so the demand names one and the consumption counts every request, an exchange of
a key for a token among them (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
LOGS = "logs.query"
COSTS = "billing.costs"
SECRETS = "secrets.metadata"
METRICS = "metrics.series"
MODEL_COSTS = "models.costs"
CATALOGUE = "models.catalogue"
EXPIRY = "expiry.credentials"
ACTIONS_CREDENTIAL = "CLOUD_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "logs.query.entries",
        "demand": {"quota_units": 1},
        "capability": LOGS,
        "effect": "read",
        "summary": "The log entries of the project that match `filter` (the provider's own "
        "filter, passed verbatim) within a window: the last `since_minutes` (default 15, at "
        "most 44640), or `start` to `end` (default now). At most `limit` (default 100, at most "
        "1000), newest first, each its timestamp, severity, message, log and identifier; never "
        "a person. `source` is refused: a log is chosen in the filter. `complete` says whether "
        "every matching entry was read.",
    },
    {
        "name": "billing.costs.daily",
        "demand": {"quota_units": 1},
        "capability": COSTS,
        "effect": "read",
        "summary": "The cost of each of the `days` days (default 29, at most 92) before `end` "
        "(a date, default today in UTC), by `group_by` — `service` (default), `account` or "
        "`region` — under `metric` — `unblended` (default) or `net_unblended`; `amortized` is "
        "refused, because the billing export has no such column. Read from the configured "
        "billing export table. Every amount is decimal text; each day's `total` is their exact "
        "sum. `estimated` marks a day of the current month; `complete` says whether every page "
        "of the answer was read.",
    },
    {
        "name": "secrets.metadata.list",
        "demand": {"quota_units": 1},
        "capability": SECRETS,
        "effect": "read",
        "summary": "The secrets of the project whose name starts with `prefix` (optional), at "
        "most `limit` (default 100, at most 500), oldest change first: each its name, when it "
        "was created and its current value set, its age in days, its rotation schedule, its "
        "expiry. Never a value: no method that answers one is called. `complete` says whether "
        "every matching secret was read.",
    },
    {
        "name": "metrics.series.query",
        "demand": {"quota_units": 1},
        "capability": METRICS,
        "effect": "read",
        "summary": "Evaluate `query` (PromQL), or the query the configuration maps the named "
        "`metric` to with its `parameters` (ADR-0328), over the project's monitoring at one "
        "moment (`time`, now when absent). Returns every series with its labels and its value, "
        "as a number and as the text the service gave. `complete` says whether every series "
        "fit within `limit` (default 1000).",
    },
    {
        "name": "metrics.series.range",
        "demand": {"quota_units": 1},
        "capability": METRICS,
        "effect": "read",
        "summary": "Evaluate `query`, or the named `metric` as for a query, over a range "
        "(`start`, `end`, `step` in seconds). Returns every series with its values, oldest "
        "first. `complete` says whether every series fit within `limit`.",
    },
    {
        "name": "models.costs.daily",
        "demand": {"quota_units": 1},
        "capability": MODEL_COSTS,
        "effect": "read",
        "summary": "What the model service charged on each of the `days` days (default 29, at "
        "most 92) before `end` (a date, default today in UTC), from the billing export kept to "
        "the configured service, by `group_by` — `line_item` (default, the SKU) or `project`. "
        "Every amount is decimal text; each day's `total` is their exact sum; `estimated` "
        "marks a day of the current month; `complete` says whether every page was read.",
    },
    {
        "name": "models.catalogue.list",
        "demand": {"quota_units": 1},
        "capability": CATALOGUE,
        "effect": "read",
        "summary": "The provider's own models the model service lists, at most `limit` "
        "(default and most 1000), sorted by identifier: each `{id, name, created_at, "
        "lifecycle, deprecated_at, retires_at}`, `lifecycle` the launch stage in lowercase. "
        "`name`, `created_at`, `deprecated_at` and `retires_at` are always null: the API "
        "states none; a retired model is one no longer listed. `retiring` is always empty; "
        "`complete` says whether every model was read.",
    },
    {
        "name": "expiry.credentials.list",
        "demand": {"quota_units": 1},
        "capability": EXPIRY,
        "effect": "read",
        "summary": "The project's service account keys a person created, at most `limit` "
        "(default 200, at most 1000), the nearest expiry first: each its kind `key`, "
        "identifier, the service account's address as name, type, state, expiry, whole days "
        "left (negative once expired) and a key. Never key material. `kinds` may name only "
        "`key`. `complete` says whether every key was read (ADR-0337).",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [LOGS, COSTS, SECRETS, METRICS, MODEL_COSTS, CATALOGUE, EXPIRY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
