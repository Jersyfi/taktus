"""What the reference connector declares about itself: the document served as the resource
`taktus://connector/v1/capabilities`, in the shape of `Connector.json#/$defs/Capabilities`.

Every operation here is an MCP tool of the same name (`server.py`). Each declares its
`demand`: the most requests to the service one call makes, which is what a run reserves before
calling it (ADR-0005). The figures are the requests each implementation in `operations.py`
makes, rounded up where the service pages its answers; `repository.branches.create` makes one
request per file and per directory besides a fixed six, so its 64 hold for a changeset of
about fifty files, and a larger one reports what it used and is recorded as a calibration
signal. Every call of the first live run used its figure or less (`docs/runs/first-run.md` §2).

The effect and the idempotency of each are facts about the target's API, stated once: a pull
request, an issue and a comment carry a mark in their body and are found again by it
(`marked`); a pipeline dispatch answers with nothing that could be found again (`none`).
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
CHANNEL = "channel.repo"

ACTIONS_CREDENTIAL = "REPOSITORY_TOKEN"
INTAKE_CREDENTIAL = "REPOSITORY_WEBHOOK_SECRET"

CAPABILITIES = [
    "repository.issues",
    "repository.pullrequests",
    "repository.pipelines",
    "repository.comments",
    "repository.branches",
    "repository.labels",
    "repository.files",
]

OPERATIONS: list[Json] = [
    {
        "name": "repository.issues.read",
        "demand": {"quota_units": 1},
        "capability": "repository.issues",
        "effect": "read",
        "summary": "Read one issue by number.",
    },
    {
        "name": "repository.issues.create",
        "demand": {"quota_units": 3},
        "capability": "repository.issues",
        "effect": "write",
        "idempotency": "marked",
        "summary": "Open an issue. The body carries the idempotency key as a mark; a repeat "
        "finds the issue by it.",
    },
    {
        "name": "repository.pullrequests.read",
        "demand": {"quota_units": 1},
        "capability": "repository.pullrequests",
        "effect": "read",
        "summary": "Read one pull request by number.",
    },
    {
        "name": "repository.pullrequests.open",
        "demand": {"quota_units": 3},
        "capability": "repository.pullrequests",
        "effect": "write",
        "idempotency": "marked",
        "summary": "Open a pull request from a head branch onto a base branch. The body "
        "carries the idempotency key as a mark; a repeat finds the pull request by its head "
        "branch and the mark.",
    },
    {
        "name": "repository.pipelines.read",
        "demand": {"quota_units": 2},
        "capability": "repository.pipelines",
        "effect": "read",
        "summary": "Read the state of one pipeline run by id.",
    },
    {
        "name": "repository.pipelines.status",
        "demand": {"quota_units": 2},
        "capability": "repository.pipelines",
        "effect": "read",
        "summary": "The state of the pipeline runs for the head of a branch: none, pending, "
        "success or failure, with every run listed.",
    },
    {
        "name": "repository.pipelines.trigger",
        "demand": {"quota_units": 1},
        "capability": "repository.pipelines",
        "effect": "write",
        "idempotency": "none",
        "summary": "Start a pipeline for a ref. The target answers with nothing a repeat could "
        "be recognised by; Taktus never repeats this on its own.",
    },
    {
        "name": "repository.comments.list",
        "demand": {"quota_units": 10},
        "capability": "repository.comments",
        "effect": "read",
        "summary": "List the comments of an issue or pull request.",
    },
    {
        "name": "repository.comments.create",
        "demand": {"quota_units": 3},
        "capability": "repository.comments",
        "effect": "write",
        "idempotency": "marked",
        "summary": "Comment on an issue or pull request. The comment carries the idempotency "
        "key as a mark; a repeat finds it.",
    },
    {
        "name": "repository.branches.create",
        "demand": {"quota_units": 64},
        "capability": "repository.branches",
        "effect": "write",
        "idempotency": "marked",
        "summary": "Create a branch from a base with one commit on it that carries the given "
        "files, or none. A file marked `executable: true` is written executable, one marked "
        "`false` plain; an unmarked file keeps the mode it has in the base, and one the base "
        "does not have is a plain file. The commit message carries the idempotency key as a "
        "trailer; a repeat finds the branch and the mark at its head.",
    },
    {
        "name": "repository.labels.set",
        "demand": {"quota_units": 3},
        "capability": "repository.labels",
        "effect": "write",
        "idempotency": "marked",
        "summary": "Put labels on an issue or pull request. The mark is the label itself: a "
        "repeat finds every requested label present and adds nothing.",
    },
    {
        "name": "repository.files.read",
        "demand": {"quota_units": 2},
        "capability": "repository.files",
        "effect": "read",
        "summary": "Read one file of the repository at a ref — a branch, a tag or a commit; "
        "the default branch when none is given. Text as text, anything else as base64, with "
        "the commit the ref resolved to.",
    },
]

INTAKE_EVENTS = [
    "issues.opened",
    "issue_comment.created",
    "pull_request.opened",
    "pipeline_run.completed",
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": list(CAPABILITIES),
        "operations": [dict(op) for op in OPERATIONS],
        "intake": {"events": list(INTAKE_EVENTS), "signature": {"scheme": "hmac-sha256"}},
        "credentials": [
            {"name": ACTIONS_CREDENTIAL, "purpose": "actions"},
            {"name": INTAKE_CREDENTIAL, "purpose": "intake"},
        ],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 3600},
        "permissions": "passthrough",
    }


def operation(name: str) -> Json:
    for op in OPERATIONS:
        if op["name"] == name:
            return op
    raise KeyError(name)
