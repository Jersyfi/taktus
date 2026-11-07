"""What the task tracker connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two reads and two writes of the capability `tasks.items` (ADR-0209). Reading the open tasks, or
one task, changes nothing. A reminder is a comment on the task, `marked`: the comment carries
the idempotency key in its last line, and a repeat finds it among the task's comments before
writing. A new task is `marked` the same way: its description's last line carries the key, and
a repeat finds it among the team's tasks before creating. The tracker notifies the task's
assignee itself; the connector never reads who that is (principle 14).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "tasks.items"
ACTIONS_CREDENTIAL = "TASKS_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "tasks.items.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every open task, up to `limit` (default 500, at most 5000); with "
        "`overdue_by_days` only those due at least that many days before today (UTC). Each "
        "names its id, key, title, due date, days_overdue, state, created_at, updated_at and "
        "url; never its assignee. `complete` says whether every task fit within `limit`.",
    },
    {
        "name": "tasks.items.read",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "One task by its `id` (or its key), in the shape of a listed one, with "
        "`open` saying whether it is still open.",
    },
    {
        "name": "tasks.items.remind",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Write `text` as a comment on the task `id`; the tracker notifies whoever "
        "the task is assigned to. The comment's last line carries the idempotency key, and a "
        "repeat that finds it among the task's comments writes nothing and reports replayed.",
    },
    {
        "name": "tasks.items.create",
        "demand": {"quota_units": 2},
        "capability": CAPABILITY,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a task with `title` (one line, at most 255 characters) and "
        "`description` in the team the connector is configured with, related to the tasks "
        "`related` names; answers its `id`, `key`, `url`, `related` and `linked`. A related "
        "task the tracker does not know is invalid, and nothing is created. The description's "
        "last line carries the idempotency key, and a repeat that finds it among the team's "
        "tasks creates nothing, relates what is missing and reports replayed.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 3600},
        "permissions": "passthrough",
    }
