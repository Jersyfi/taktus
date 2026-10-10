"""The reference connector against the real service: the promise of ADR-0005 tested outside.

A fake proves the mechanics; only the real service proves that its API keeps what the connector
relies on — one open pull request per head branch, the mark in a body, the trailer in a commit
message, a reference that exists once. This test runs when the repository and one identity are
set, and skips otherwise:

    TAKTUS_LIVE_REPOSITORY=owner/name   the repository to act in; the test creates a branch, a
                                        pull request, a comment and a label there, and removes
                                        the branch and closes the pull request afterwards

and either Taktus's own app installed on that repository (ADR-0033) — the connector then mints
its installation token from the key, and the pull request must show the app as its author:

    TAKTUS_REPOSITORY_APP_ID=…                     the app's identifier
    TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE=…    the file that holds the app's private key

or a token, for a tenant without an app:

    REPOSITORY_TOKEN=…                  the requesting identity's token, with contents and
                                        pull request write permissions on that repository

The app wins when both are set. A value is read by the connector, as the contract says, and
never appears in a result, an error or the log (`test_no_credential_value_reaches_a_result_an_
error_or_the_log` and `test_no_key_token_or_statement_reaches_a_result_an_error_or_the_log`
cover that against the fake; here it is asserted once more on what came back). It is never
written anywhere by this test.

Every step below is executed twice: once on a connector, once on a second connector that has
no memory of the first, with the same idempotency key. The second answer must be the first,
marked as replayed, and the service must hold one record.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from taktus.adapters.driven.connectors.github.app import AppConfig, AppTokens
from taktus.adapters.driven.connectors.github.server import Config, Connector

type Json = dict[str, Any]

CREDENTIAL = "REPOSITORY_TOKEN"
TARGET = "https://api.github.com"
APP = AppConfig.from_environment()

pytestmark = pytest.mark.skipif(
    not (os.environ.get("TAKTUS_LIVE_REPOSITORY") and (APP or os.environ.get(CREDENTIAL))),
    reason="set TAKTUS_LIVE_REPOSITORY=owner/name and the app's two variables, or "
    "REPOSITORY_TOKEN, to run against the service",
)


async def service_token(repository: str) -> str:
    """The token this test reads the service with directly: the app's, minted like the
    connector's, or the one in the environment."""
    if APP is None:
        return os.environ[CREDENTIAL]
    token, _ = await AppTokens(APP, TARGET, repository, timeout=30.0).token()
    return token


def context(step: str, key: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_live",
        "run_id": "run_live",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
    }


async def call(connector: Connector, operation: str, ctx: Json, input: Json) -> Json:
    result = await connector.call(operation, ctx, input)
    assert isinstance(result.structured_content, dict)
    assert not result.is_error, result.structured_content
    return result.structured_content


@pytest.fixture
async def live() -> AsyncIterator[tuple[str, str]]:
    """The repository and a unique suffix; the branch and pull request are removed afterwards
    whatever happened in between."""
    repository = os.environ["TAKTUS_LIVE_REPOSITORY"]
    suffix = secrets.token_hex(4)
    yield repository, suffix
    token = await service_token(repository)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(base_url=TARGET, headers=headers, timeout=30.0) as client:
        head = f"{repository.split('/')[0]}:taktus/live-{suffix}"
        for pull in (await client.get(f"/repos/{repository}/pulls", params={"head": head})).json():
            await client.patch(
                f"/repos/{repository}/pulls/{pull['number']}", json={"state": "closed"}
            )
        await client.delete(f"/repos/{repository}/git/refs/heads/taktus/live-{suffix}")


async def test_a_step_retried_after_a_restart_acts_once_on_the_real_service(
    live: tuple[str, str],
) -> None:
    repository, suffix = live
    branch = f"taktus/live-{suffix}"
    fresh = lambda: Connector(  # noqa: E731
        Config(target=TARGET, repository=repository, timeout=60.0, app=APP)
    )
    token = await service_token(repository)

    # A branch with one commit, twice: one branch, the second answer replayed.
    key = f"run_live:branch-{suffix}:1"
    branch_input = {
        "name": branch,
        "base": "main",
        "message": f"live check {suffix}",
        "files": [
            {"path": f"conformance/live-{suffix}.md", "content": "Created by a test.\n"},
            {"path": f"conformance/live-{suffix}.sh", "content": "#!/bin/sh\n", "executable": True},
        ],
    }
    first = await call(fresh(), "repository.branches.create", context("branch", key), branch_input)
    again = await call(fresh(), "repository.branches.create", context("branch", key), branch_input)
    assert first["effect"]["replayed"] is False and again["effect"]["replayed"] is True
    assert again["output"]["sha"] == first["output"]["sha"]

    # The file the branch carries, read back at the branch: the same bytes, at its commit.
    read = await call(
        fresh(),
        "repository.files.read",
        context("read", f"run_live:read-{suffix}:1"),
        {"path": f"conformance/live-{suffix}.md", "ref": branch},
    )
    assert read["effect"] == {"kind": "read"}
    assert read["output"]["content"] == "Created by a test.\n"
    assert read["output"]["commit"] == first["output"]["sha"]

    # A pull request, twice: one pull request, the second answer replayed. Then the service is
    # asked directly how many pull requests that head has.
    key = f"run_live:open-pr-{suffix}:1"
    pr_input = {
        "head": branch,
        "base": "main",
        "title": f"live idempotency check {suffix}",
        "body": "Opened by tests/adapters/connectors/test_repository_live.py; closed by it.",
    }
    opened = await call(fresh(), "repository.pullrequests.open", context("open-pr", key), pr_input)
    replayed = await call(
        fresh(), "repository.pullrequests.open", context("open-pr", key), pr_input
    )
    assert opened["effect"]["replayed"] is False and replayed["effect"]["replayed"] is True
    assert replayed["output"]["number"] == opened["output"]["number"]
    assert replayed["effect"]["records"] == opened["effect"]["records"]
    number = int(opened["output"]["number"])
    if APP is not None:
        # Acting as the app, the pull request is the app's, not a person's (issue #50).
        assert opened["output"]["author"]["kind"] == "automation", opened["output"]["author"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(base_url=TARGET, headers=headers, timeout=30.0) as client:
        pulls = (
            await client.get(
                f"/repos/{repository}/pulls",
                params={"head": f"{repository.split('/')[0]}:{branch}", "state": "all"},
            )
        ).json()
    assert [p["number"] for p in pulls] == [number]
    async with httpx.AsyncClient(base_url=TARGET, headers=headers, timeout=30.0) as client:
        head = first["output"]["sha"]
        commit = (await client.get(f"/repos/{repository}/git/commits/{head}")).json()
        listed = await client.get(
            f"/repos/{repository}/git/trees/{commit['tree']['sha']}", params={"recursive": "1"}
        )
    modes = {entry["path"]: entry["mode"] for entry in listed.json()["tree"]}
    assert modes[f"conformance/live-{suffix}.sh"] == "100755", "a new executable (issue #28)"

    # A comment and a label, twice each.
    key = f"run_live:comment-{suffix}:1"
    comment_input = {"number": number, "body": "One comment, whatever the retries."}
    first_comment = await call(
        fresh(), "repository.comments.create", context("comment", key), comment_input
    )
    again_comment = await call(
        fresh(), "repository.comments.create", context("comment", key), comment_input
    )
    assert again_comment["effect"]["replayed"] is True
    assert again_comment["output"]["id"] == first_comment["output"]["id"]

    key = f"run_live:label-{suffix}:1"
    label_input = {"number": number, "labels": ["taktus"]}
    await call(fresh(), "repository.labels.set", context("label", key), label_input)
    labelled = await call(fresh(), "repository.labels.set", context("label", key), label_input)
    assert labelled["effect"]["replayed"] is True
    assert "taktus" in labelled["output"]["labels"]

    # The pipeline's state for the branch is whatever the service says, in one of four words.
    status = await call(
        fresh(),
        "repository.pipelines.status",
        context("ci", f"run_live:ci-{suffix}:1"),
        {"ref": branch},
    )
    assert status["output"]["state"] in ("none", "pending", "success", "failure")
    assert status["output"]["sha"] == first["output"]["sha"]

    for document in (first, again, read, opened, replayed, first_comment, labelled, status):
        assert token not in str(document)


async def test_the_member_list_is_read_from_the_real_service() -> None:
    """DEC-0127's proof on the real service: with the permissions it holds, the app reads the
    repository's collaborators — account, login name, kind, role — and the service names no
    address. Only counts are asserted, so that a failure prints no member."""
    repository = os.environ["TAKTUS_LIVE_REPOSITORY"]
    connector = Connector(Config(target=TARGET, repository=repository, timeout=60.0, app=APP))
    result = await connector.call(
        "repository.members.list",
        context("members", f"run_live:members-{secrets.token_hex(4)}"),
        {},
    )
    content = result.structured_content
    assert isinstance(content, dict)
    cause = content.get("cause") if result.is_error else None
    assert cause is None, f"the member list was refused: {cause}"
    members = content["output"]["members"]
    shaped = sum(1 for m in members if set(m) == {"account", "kind", "name", "role"})
    admins = sum(1 for m in members if m["kind"] == "person" and m["role"] == "admin")
    assert content["output"]["complete"] is True
    assert shaped == len(members), "every member carries exactly the four fields"
    assert admins >= 1, "at least one person administers the repository: its owner"
