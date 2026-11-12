"""What the directory connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Two operations, of the capabilities `directory.accounts` and `directory.groups`, both of effect
`read`: reading a directory changes nothing. Each page of an answer is one request, so the
demand names one unit and the consumption counts every page (ADR-0005). Revoking an account's
access stays a person's (UC-03 B-5.03), so nothing here writes.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "directory.accounts"
GROUPS = "directory.groups"
ACTIONS_CREDENTIAL = "DIRECTORY_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "directory.accounts.list",
        "demand": {"quota_units": 1},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "Every account of the directory, up to `limit` (default 1000, at most "
        "10000); with `group`, a group's display name, only the accounts that are its members. "
        "Each names its id, its userName, its userType, whether it is active, the display "
        "names of its groups, its roles and entitlements, and when it was last modified; no "
        "name, e-mail address or phone number. `complete` says whether every account was read.",
    },
    {
        "name": "directory.groups.list",
        "demand": {"quota_units": 1},
        "capability": GROUPS,
        "effect": "read",
        "summary": "Every group of the directory, or with `name` the groups of that display "
        "name: each its id, its display name, the ids of its members and their count. "
        "`complete` says whether every group was read.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY, GROUPS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
