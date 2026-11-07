"""What the package licence connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

One operation of the capability `packages.licences`, of effect `read`: asking a public index
changes nothing. Each package version asked is one request (ADR-0005).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CAPABILITY = "packages.licences"
ACTIONS_CREDENTIAL = "PACKAGES_TOKEN"

OPERATIONS: list[Json] = [
    {
        "name": "packages.licences.list",
        "demand": {"quota_units": 100},
        "capability": CAPABILITY,
        "effect": "read",
        "summary": "The licences the public index states for every exact version the "
        "dependency manifest `manifest` pins, its text as a repository holds it, in the "
        "`format` its file name gives — package-lock.json, uv.lock or requirements.txt —, up to "
        "`limit` packages (default 500, at most 2000). Each names its system, name, version, "
        "whether it is a development dependency, `licences` as SPDX expressions the index "
        "gives, empty where it states none, and `known`, false where the index does not hold "
        "the version. `unpinned` names the requirements without an exact version, which are "
        "never guessed; `complete` says whether every package fit within `limit`.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [CAPABILITY],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 1},
        "permissions": "passthrough",
    }
