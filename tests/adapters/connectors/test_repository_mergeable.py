"""The repository connector's operations that keep a pull request mergeable and merge it under
a policy (ADR-0193, ADR-0194), against the fake service.

Each write is tried twice with one key across two connectors that share no memory, and once
with a new key, so that a repeat is shown to act once; and each refusal the operations promise —
a branch that moved, a merge with a conflict, another head — is shown to write nothing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from taktus_connectors.github.server import Config, Connector

from .conftest import Service

type Json = dict[str, Any]

REPOSITORY = "acme/mergeable"


def config(service: Service) -> Config:
    return Config(target=service.url, repository=REPOSITORY, timeout=5.0)


def context(step: str, key: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_7f3a2c",
        "run_id": "run_01",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}],
    }


async def call(operation: str, service: Service, key: str, input: Json) -> tuple[bool, Json]:
    """Through a fresh connector each time: it remembers nothing of an earlier call."""
    result = await Connector(config(service)).call(operation, context("s", key), input)
    assert isinstance(result.structured_content, dict)
    return bool(result.is_error), result.structured_content


async def ok(operation: str, service: Service, key: str, input: Json) -> Json:
    error, body = await call(operation, service, key, input)
    assert not error, body
    return body


def api(service: Service, method: str, path: str, body: Json | None = None) -> Any:
    answer = httpx.request(
        method,
        f"{service.url}/repos/{REPOSITORY}{path}",
        json=body,
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    )
    answer.raise_for_status()
    return answer.json() if answer.content else None


def head(service: Service, branch: str) -> str:
    return str(api(service, "GET", f"/git/ref/heads/{branch}")["object"]["sha"])


async def on_branch(service: Service, name: str, base: str, files: dict[str, str], key: str) -> Json:
    entries = [{"path": p, "content": c} for p, c in files.items()]
    return await ok(
        "repository.branches.create",
        service,
        key,
        {"name": name, "base": base, "message": f"change {name}", "files": entries},
    )


async def advance_main(service: Service, files: dict[str, str], key: str) -> None:
    """`main` gains a commit, as a merge by somebody else gives it one."""
    await on_branch(service, "side-" + key[-6:], "main", files, key)
    api(
        service,
        "PATCH",
        "/git/refs/heads/main",
        {"sha": head(service, "side-" + key[-6:]), "force": False},
    )


async def pull(service: Service, branch: str, title: str = "A change") -> int:
    body = await ok(
        "repository.pullrequests.open",
        service,
        f"run_01:open:{branch}-0123456789",
        {"head": branch, "base": "main", "title": title, "body": "Opened by a test."},
    )
    return int(body["output"]["number"])


@pytest.mark.usefixtures("credentials")
async def test_the_list_says_how_far_each_pull_request_is_behind_and_what_its_pipeline_says(
    service: Service,
) -> None:
    await on_branch(service, "taktus/one", "main", {"a.txt": "a\n"}, "run_01:b1:1-0123456789")
    number = await pull(service, "taktus/one")
    await advance_main(service, {"b.txt": "b\n"}, "run_01:side:1-0123456789")

    body = await ok(
        "repository.pullrequests.list", service, "run_01:l:1-0123456789", {"with_state": True}
    )
    assert body["effect"] == {"kind": "read"} and body["output"]["complete"] is True
    (listed,) = [p for p in body["output"]["pulls"] if p["number"] == number]
    assert listed["head"] == "taktus/one" and listed["base"] == "main"
    assert listed["behind"] == 1 and listed["ahead"] == 1
    assert listed["pipeline"] == "success" and listed["draft"] is False
    assert listed["head_key"] == "run_01:b1:1-0123456789"
    assert listed["idle_hours"] == 0 and listed["open_hours"] == 0

    plain = await ok("repository.pullrequests.list", service, "run_01:l:2-0123456789", {})
    assert "behind" not in plain["output"]["pulls"][0]


@pytest.mark.usefixtures("credentials")
async def test_the_base_is_merged_into_a_branch_once_and_a_branch_that_has_it_gets_nothing(
    service: Service,
) -> None:
    await on_branch(service, "taktus/two", "main", {"a.txt": "a\n"}, "run_01:b2:1-0123456789")
    await advance_main(service, {"b.txt": "b\n"}, "run_01:side:2-0123456789")
    before = head(service, "taktus/two")
    key = "run_01:update:1-0123456789"
    input = {"name": "taktus/two", "base": "main", "expected": before}

    first = await ok("repository.branches.update", service, key, input)
    assert first["output"]["updated"] is True and first["effect"]["replayed"] is False
    merged = head(service, "taktus/two")
    assert merged != before
    again = await ok("repository.branches.update", service, key, input)
    assert again["effect"]["replayed"] is True and head(service, "taktus/two") == merged

    nothing = await ok(
        "repository.branches.update",
        service,
        "run_01:update:2-0123456789",
        {"name": "taktus/two", "base": "main"},
    )
    assert nothing["output"]["updated"] is False and head(service, "taktus/two") == merged


@pytest.mark.usefixtures("credentials")
async def test_an_update_of_a_branch_that_moved_or_conflicts_writes_nothing(
    service: Service,
) -> None:
    await on_branch(service, "taktus/three", "main", {"c.txt": "ours\n"}, "run_01:b3:1-0123456789")
    await advance_main(service, {"c.txt": "theirs\n"}, "run_01:side:3-0123456789")
    before = head(service, "taktus/three")

    error, moved = await call(
        "repository.branches.update",
        service,
        "run_01:update:3-0123456789",
        {"name": "taktus/three", "base": "main", "expected": "0" * 40},
    )
    assert error and moved["cause"] == "conflict" and moved["effect"] == "none"
    error, conflict = await call(
        "repository.branches.update",
        service,
        "run_01:update:4-0123456789",
        {"name": "taktus/three", "base": "main"},
    )
    assert error and conflict["cause"] == "conflict"
    assert head(service, "taktus/three") == before


@pytest.mark.usefixtures("credentials")
async def test_a_commit_goes_onto_the_branch_once_and_only_onto_the_head_it_was_made_against(
    service: Service,
) -> None:
    await on_branch(service, "taktus/four", "main", {"d.txt": "1\n"}, "run_01:b4:1-0123456789")
    expected = head(service, "taktus/four")
    key = "run_01:commit:1-0123456789"
    input = {
        "name": "taktus/four",
        "expected": expected,
        "message": "repair",
        "files": [{"path": "d.txt", "content": "2\n"}],
    }
    first = await ok("repository.branches.commit", service, key, input)
    assert first["output"]["parent"] == expected and first["effect"]["replayed"] is False
    written = head(service, "taktus/four")
    again = await ok("repository.branches.commit", service, key, input)
    assert again["effect"]["replayed"] is True and again["output"]["sha"] == written
    assert head(service, "taktus/four") == written

    error, moved = await call(
        "repository.branches.commit", service, "run_01:commit:2-0123456789", input
    )
    assert error and moved["cause"] == "conflict" and moved["effect"] == "none"
    assert head(service, "taktus/four") == written


@pytest.mark.usefixtures("credentials")
async def test_the_paths_of_a_pull_request_are_read_at_its_head(service: Service) -> None:
    await on_branch(
        service, "taktus/five", "main", {"docs/a.md": "x\ny\n", "src/b.py": "z\n"},
        "run_01:b5:1-0123456789",
    )  # fmt: skip
    number = await pull(service, "taktus/five")
    body = await ok(
        "repository.pullrequests.files",
        service,
        "run_01:f:1-0123456789",
        {"number": number, "patches": True},
    )
    output = body["output"]
    assert output["head_sha"] == head(service, "taktus/five") and output["complete"] is True
    assert [f["path"] for f in output["files"]] == ["docs/a.md", "src/b.py"]
    assert output["count"] == 2 and output["additions"] == 3 and output["deletions"] == 0
    assert output["files"][0]["status"] == "added" and "+x" in output["files"][0]["patch"]


@pytest.mark.usefixtures("credentials")
async def test_a_pull_request_is_merged_once_at_the_head_named_and_never_at_another(
    service: Service,
) -> None:
    await on_branch(service, "taktus/six", "main", {"e.md": "e\n"}, "run_01:b6:1-0123456789")
    number = await pull(service, "taktus/six")
    sha = head(service, "taktus/six")

    error, other = await call(
        "repository.pullrequests.merge",
        service,
        "run_01:merge:0-0123456789",
        {"number": number, "sha": "0" * 40},
    )
    assert error and other["cause"] == "conflict"
    assert api(service, "GET", f"/pulls/{number}")["merged"] is False

    key = "run_01:merge:1-0123456789"
    first = await ok("repository.pullrequests.merge", service, key, {"number": number, "sha": sha})
    assert first["output"]["merged"] is True and first["effect"]["replayed"] is False
    main = head(service, "main")
    again = await ok("repository.pullrequests.merge", service, key, {"number": number, "sha": sha})
    assert again["effect"]["replayed"] is True and head(service, "main") == main

    error, theirs = await call(
        "repository.pullrequests.merge",
        service,
        "run_01:merge:2-0123456789",
        {"number": number, "sha": sha},
    )
    assert error and theirs["cause"] == "conflict", "merged, but not under this key"


@pytest.mark.usefixtures("credentials")
async def test_the_runs_of_one_status_are_listed_with_their_age(service: Service) -> None:
    service.control("/_fake/ci", {"pending": True})
    try:
        await on_branch(service, "taktus/seven", "main", {"f": "f\n"}, "run_01:b7:1-0123456789")
    finally:
        service.control("/_fake/ci", {"conclusion": "success"})
    body = await ok(
        "repository.pipelines.list", service, "run_01:r:1-0123456789", {"status": "in_progress"}
    )
    runs = body["output"]["runs"]
    assert runs and all(r["status"] == "in_progress" for r in runs)
    assert runs[0]["head_sha"] == head(service, "taktus/seven") and runs[0]["age_minutes"] == 0
