"""What the cloud connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Three capabilities, one operation each, all of effect `read`: `billing.costs`, `logs.query`
and `secrets.metadata`. Reading changes nothing. Each page of an answer is one request, so the
demand names one unit and the consumption counts every page (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "billing.costs"
LOGS = "logs.query"
SECRETS = "secrets.metadata"
ACTIONS_CREDENTIAL = "BILLING_KEY"

OPERATIONS: list[Json] = [
    {
        "name": "billing.costs.daily",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The cost of each of the `days` days (default 29, at most 92) before `end` "
        "(a date, default today in UTC), by `group_by` — `service` (default), `account` or "
        "`region` — under `metric` — `unblended` (default), `amortized` or `net_unblended`. "
        "Every amount is the decimal text the provider gave; each day's `total` is their exact "
        "sum. `estimated` marks a day the provider has not closed; `complete` says whether "
        "every page of the answer was read.",
    },
    {
        "name": "logs.query.entries",
        "demand": {"quota_units": 1},
        "capability": LOGS,
        "effect": "read",
        "summary": "The log events of one log group — `source`, or the connector's configured "
        "group — that match `filter`, a filter pattern passed verbatim (at most 1024 "
        "characters), within the `since_minutes` (default 15, at most 44640) before now, or "
        "from `start` to `end` (RFC 3339, `end` default now); at most `limit` (default 100, "
        "at most 1000), newest first. Each entry is `timestamp`, `severity` (always null: the "
        "store has none), `message` (at most 2000 characters), `source` (the log stream) and "
        "`id` (the event's identifier). `count`, `complete`, and the window asked as `start` "
        "and `end`.",
    },
    {
        "name": "secrets.metadata.list",
        "demand": {"quota_units": 1},
        "capability": SECRETS,
        "effect": "read",
        "summary": "The metadata of the stored secrets whose name begins with `prefix` "
        "(optional), at most `limit` (default 100, at most 500), oldest change first: `name`, "
        "`created_at`, `changed_at` (last rotation, else last change, else creation), "
        "`age_days`, `rotation` (`automatic`, `period_days`, `next_at`), `expires_at` (always "
        "null) and `last_accessed_at`. Never a secret's value. `complete` and `read_at`.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, LOGS, SECRETS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
