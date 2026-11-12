"""What the cloud operations connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

Three capabilities of one cloud project, each one operation of effect `read`: reading log
entries, costs or the metadata of secrets changes nothing. Each request is one unit, so the
demand names one and the consumption counts every request, an exchange of a key for a token
among them (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
LOGS = "logs.query"
COSTS = "billing.costs"
SECRETS = "secrets.metadata"
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
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [LOGS, COSTS, SECRETS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
