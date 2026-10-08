"""The reference connector's actions against the fake service: what the contract promises,
shown on the product it is implemented against.

The one test that matters most is the restart: a pull request opened for a step, and the same
step retried by a connector that has no memory of the first attempt, produce one pull request.
The rest is the contract read line by line — permissions pass through, errors are classified,
consumption is counted, a credential value is read at the call and appears nowhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

from taktus.adapters.driven.connectors.github import declaration
from taktus.adapters.driven.connectors.github.server import Config, Connector, build_server

from .conftest import READ_CREDENTIAL, WRITE_CREDENTIAL, Service

type Json = dict[str, Any]

REPOSITORY = "acme/product"


def config(service: Service, **overrides: Any) -> Config:
    return Config(**{"target": service.url, "repository": REPOSITORY, "timeout": 5.0, **overrides})


SEEDED = {"issues": 1, "runs": 1}  # what the fake creates with a repository on first contact


def count(service: Service, counter: str) -> int:
    state = service.state().get(REPOSITORY)
    return int(state[counter]) if state else SEEDED.get(counter, 0)


def context(step: str, key: str, *credentials: Json) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_7f3a2c",
        "run_id": "run_01",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": list(credentials) or [{"name": WRITE_CREDENTIAL, "injected_as": "env"}],
    }


async def call(connector: Connector, operation: str, ctx: Json, input: Json) -> tuple[bool, Json]:
    result = await connector.call(operation, ctx, input)
    assert isinstance(result.structured_content, dict)
    return bool(result.is_error), result.structured_content


PR_INPUT = {
    "head": "taktus/issue-412",
    "base": "main",
    "title": "Pin the model",
    "body": "Closes #412.",
}
KEY = "run_01:open-pr:1-0123456789"


@pytest.mark.usefixtures("credentials")
async def test_a_step_retried_after_a_restart_opens_one_pull_request(service: Service) -> None:
    """Two connector processes — the second knows nothing of the first — asked to open the same
    pull request for the same step: one pull request exists, and the second answer is the first,
    marked as replayed. This is ADR-0005's promise tested against the outside."""
    before = await asyncio_call(build_server(config(service)), "repository.pullrequests.open", KEY)
    assert before["effect"]["replayed"] is False
    number = before["output"]["number"]

    restarted = build_server(config(service))  # a fresh process: no memory of the first call
    after = await asyncio_call(restarted, "repository.pullrequests.open", KEY)
    assert after["effect"]["replayed"] is True
    assert after["output"]["number"] == number
    assert after["effect"]["records"] == before["effect"]["records"]
    assert after["effect"]["content_digest"] == before["effect"]["content_digest"]
    assert service.state()[REPOSITORY]["pulls"] == 1

    again = await asyncio_call(restarted, "repository.pullrequests.open", KEY)
    assert again["effect"]["replayed"] is True
    assert service.state()[REPOSITORY]["pulls"] == 1


async def asyncio_call(server: Any, operation: str, key: str) -> Json:
    """Through MCP, in process: the same wire shape the suite and Taktus use."""
    async with Client(server) as client:
        result = await client.call_tool(
            operation, {"context": context("open-pr", key), "input": PR_INPUT}
        )
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    return result.structured_content


@pytest.mark.usefixtures("credentials")
async def test_a_new_attempt_key_opens_a_new_pull_request_only_for_a_new_head(
    service: Service,
) -> None:
    connector = Connector(config(service))
    error, first = await call(
        connector, "repository.pullrequests.open", context("open-pr", KEY), PR_INPUT
    )
    assert not error
    other_key = "run_01:open-pr:2-0123456789"
    error, conflict = await call(
        connector, "repository.pullrequests.open", context("open-pr", other_key), PR_INPUT
    )
    assert error
    assert conflict["cause"] == "conflict"
    assert conflict["effect"] == "none"
    assert conflict["retryable"] is False
    assert service.state()[REPOSITORY]["pulls"] == 1
    error, second = await call(
        connector,
        "repository.pullrequests.open",
        context("open-pr", other_key),
        {**PR_INPUT, "head": "taktus/issue-413"},
    )
    assert not error
    assert second["output"]["number"] != first["output"]["number"]
    assert service.state()[REPOSITORY]["pulls"] == 2


@pytest.mark.usefixtures("credentials")
@pytest.mark.parametrize(
    ("operation", "input", "counter"),
    [
        ("repository.issues.create", {"title": "Found a thing", "body": "Details."}, "issues"),
        ("repository.comments.create", {"number": 1, "body": "On it."}, "comments"),
    ],
)
async def test_issues_and_comments_are_marked_and_found_again(
    service: Service, operation: str, input: Json, counter: str
) -> None:
    connector = Connector(config(service))
    key = f"run_01:{counter}:1-0123456789"
    baseline = count(service, counter)
    error, first = await call(connector, operation, context(counter, key), input)
    assert not error
    assert first["effect"]["kind"] == "write"
    assert first["effect"]["replayed"] is False
    error, repeat = await call(Connector(config(service)), operation, context(counter, key), input)
    assert not error
    assert repeat["effect"]["replayed"] is True
    assert repeat["effect"]["records"] == first["effect"]["records"]
    assert service.state()[REPOSITORY][counter] == baseline + 1
    assert "taktus-idempotency-key" in first["output"]["body"]


@pytest.mark.usefixtures("credentials")
async def test_a_pipeline_trigger_cannot_recognise_a_repeat_and_says_so(service: Service) -> None:
    """The honest case: the declaration says `none`, the connector acts every time, and Taktus
    is the one that must not repeat it (contract README §4)."""
    assert declaration.operation("repository.pipelines.trigger")["idempotency"] == "none"
    connector = Connector(config(service))
    key = "run_01:trigger:1-0123456789"
    input = {"workflow": "ci.yml", "ref": "main"}
    runs = count(service, "runs")
    for _ in range(2):
        error, result = await call(
            connector, "repository.pipelines.trigger", context("trigger", key), input
        )
        assert not error
        assert result["effect"]["replayed"] is False
        assert result["effect"]["records"] == [{"kind": "pipeline.dispatch", "id": "ci.yml@main"}]
    assert service.state()[REPOSITORY]["runs"] == runs + 2


@pytest.mark.usefixtures("credentials")
async def test_reads_report_their_effect_and_count_their_requests(service: Service) -> None:
    connector = Connector(config(service))
    error, issue = await call(
        connector, "repository.issues.read", context("read", KEY), {"number": 1}
    )
    assert not error
    assert issue["effect"] == {"kind": "read"}
    assert issue["consumption"] == {"quota_units": 1}
    assert issue["output"]["number"] == 1
    error, run = await call(
        connector, "repository.pipelines.read", context("read", KEY), {"run": "1"}
    )
    assert not error
    assert run["output"]["status"] == "completed"
    error, comments = await call(
        connector, "repository.comments.list", context("read", KEY), {"number": 1}
    )
    assert not error
    assert comments["output"]["comments"] == []


@pytest.mark.usefixtures("credentials")
async def test_an_issue_is_read_with_its_labels_and_milestone_and_listed_page_by_page(
    service: Service,
) -> None:
    """What the ready standard of a backlog reads besides the body (issue #70): the labels by
    name and the milestone by title, and every open issue — without pull requests — read to the
    last page, with `complete` saying so."""
    connector = Connector(config(service))
    error, _ = await call(connector, "repository.issues.read", context("r", KEY), {"number": 1})
    assert not error  # the fake creates the repository, and its seed issue, on first contact
    milestone = _service_post(service, f"/repos/{REPOSITORY}/milestones", {"title": "0.2.0"})
    task = _service_post(
        service,
        f"/repos/{REPOSITORY}/issues",
        {"title": "t", "labels": ["task", "ready"], "milestone": milestone["number"]},
    )
    error, read = await call(
        connector, "repository.issues.read", context("r", KEY), {"number": task["number"]}
    )
    assert not error, read
    assert read["output"]["labels"] == ["ready", "task"]
    assert read["output"]["milestone"] == "0.2.0"
    error, seed = await call(connector, "repository.issues.read", context("r", KEY), {"number": 1})
    assert seed["output"]["labels"] == [] and seed["output"]["milestone"] is None

    for n in range(150):
        _service_post(service, f"/repos/{REPOSITORY}/issues", {"title": f"more {n}"})
    error, listed = await call(connector, "repository.issues.list", context("r", KEY), {})
    assert not error, listed
    assert listed["effect"] == {"kind": "read"}
    assert listed["output"]["complete"] is True
    numbers = [issue["number"] for issue in listed["output"]["issues"]]
    assert len(numbers) == 152 and numbers == sorted(numbers, reverse=True)
    assert listed["consumption"]["quota_units"] == 2, "two pages of 100"
    error, refused = await call(
        connector, "repository.issues.list", context("r", KEY), {"state": "draft"}
    )
    assert error and refused["cause"] == "invalid"


@pytest.mark.usefixtures("credentials")
async def test_a_directory_is_listed_at_a_ref_with_the_commit_it_was_read_at(
    service: Service,
) -> None:
    """`repository.files.list` (issue #70): the immediate entries of a directory at a branch,
    each with its type, and the commit the branch pointed at. A file is not a directory."""
    connector = Connector(config(service))
    error, branch = await call(
        connector,
        "repository.branches.create",
        context("b", "run_01:list:1-0123456789"),
        {
            "name": "taktus/list",
            "base": "main",
            "files": [
                {"path": "docs/open/DEC-0999-a-token.md", "content": "x\n"},
                {"path": "docs/open/README.md", "content": "y\n"},
                {"path": "docs/open/deeper/note.md", "content": "z\n"},
            ],
        },
    )
    assert not error, branch
    error, listed = await call(
        connector,
        "repository.files.list",
        context("l", KEY),
        {"path": "docs/open", "ref": "taktus/list"},
    )
    assert not error, listed
    assert listed["output"]["commit"] == branch["output"]["sha"]
    assert listed["output"]["entries"] == [
        {"name": "DEC-0999-a-token.md", "path": "docs/open/DEC-0999-a-token.md", "type": "file"},
        {"name": "README.md", "path": "docs/open/README.md", "type": "file"},
        {"name": "deeper", "path": "docs/open/deeper", "type": "dir"},
    ]
    assert listed["consumption"]["quota_units"] == 2  # the ref, then the directory
    for input, cause in [
        ({"path": "docs/open/README.md", "ref": "taktus/list"}, "invalid"),
        ({"path": "docs/nowhere", "ref": "taktus/list"}, "not_found"),
        ({"path": "docs/open", "ref": "taktus/nowhere"}, "not_found"),
    ]:
        error, refused = await call(connector, "repository.files.list", context("l", KEY), input)
        assert error and refused["cause"] == cause, (input, refused)


@pytest.mark.usefixtures("credentials")
async def test_source_system_permissions_remain_in_force(service: Service) -> None:
    """A read-only identity reads and is refused on a write; an unknown credential name is
    refused before any request; no credential at all is refused as well. The connector has no
    credential of its own to fall back on."""
    connector = Connector(config(service))
    read_only = {"name": READ_CREDENTIAL, "injected_as": "env"}
    error, _ = await call(
        connector, "repository.issues.read", context("read", KEY, read_only), {"number": 1}
    )
    assert not error
    error, refused = await call(
        connector, "repository.issues.create", context("create", KEY, read_only), {"title": "x"}
    )
    assert error
    assert refused["cause"] == "forbidden"
    assert refused["effect"] == "none"
    assert refused["consumption"] == {"quota_units": 2}  # the lookup, then the refused create

    unknown = {"name": "REPOSITORY_TOKEN_NOBODY", "injected_as": "env"}
    error, missing = await call(
        connector, "repository.issues.read", context("read", KEY, unknown), {"number": 1}
    )
    assert error
    assert missing["cause"] == "unauthenticated"
    assert "consumption" not in missing  # no request was made

    ctx = {**context("read", KEY), "credentials": []}
    error, none = await call(connector, "repository.issues.read", ctx, {"number": 1})
    assert error
    assert none["cause"] == "unauthenticated"


async def test_a_credential_can_be_injected_as_a_file(service: Service, tmp_path: Path) -> None:
    secret_file = tmp_path / "repository-token"
    secret_file.write_text(service.write_value + "\n")
    reference = {"name": WRITE_CREDENTIAL, "injected_as": "file", "path": str(secret_file)}
    error, issue = await call(
        Connector(config(service)),
        "repository.issues.read",
        context("read", KEY, reference),
        {"number": 1},
    )
    assert not error
    assert issue["output"]["number"] == 1


@pytest.mark.usefixtures("credentials")
async def test_errors_are_classified(service: Service) -> None:
    connector = Connector(config(service))
    error, not_found = await call(
        connector, "repository.issues.read", context("read", KEY), {"number": 999}
    )
    assert error
    assert (not_found["cause"], not_found["effect"], not_found["retryable"]) == (
        "not_found",
        "none",
        False,
    )

    error, invalid = await call(
        connector, "repository.issues.read", context("read", KEY), {"number": -1}
    )
    assert error
    assert invalid["cause"] == "invalid"
    assert "consumption" not in invalid

    error, invalid = await call(
        connector, "repository.issues.create", context("c", KEY), {"title": ""}
    )
    assert error
    assert invalid["cause"] == "invalid"

    service.control("/_fake/outage", {"on": True})
    try:
        error, unavailable = await call(
            connector, "repository.issues.read", context("read", KEY), {"number": 1}
        )
    finally:
        service.control("/_fake/outage", {"on": False})
    assert error
    assert (unavailable["cause"], unavailable["effect"], unavailable["retryable"]) == (
        "unavailable",
        "none",
        True,
    )

    service.control("/_fake/hang", {"seconds": 1.5})
    try:
        error, unknown = await call(
            Connector(config(service, timeout=0.3)),
            "repository.issues.read",
            context("read", KEY),
            {"number": 1},
        )
    finally:
        service.control("/_fake/hang", {"seconds": 0})
    assert error
    assert (unknown["cause"], unknown["effect"], unknown["retryable"]) == (
        "unknown",
        "unknown",
        False,
    )

    error, missing_key = await call(
        connector,
        "repository.issues.read",
        {**context("read", KEY), "idempotency_key": ""},
        {"number": 1},
    )
    assert error
    assert missing_key["cause"] == "invalid"


@pytest.mark.usefixtures("credentials")
async def test_the_declaration_is_served_and_every_operation_is_a_tool(service: Service) -> None:
    async with Client(build_server(config(service))) as client:
        resource = await client.read_resource("taktus://connector/v1/capabilities")
        content = resource.contents[0]
        assert getattr(content, "mime_type", None) == "application/json"
        capabilities = json.loads(content.text)
        assert capabilities == declaration.capabilities()
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        for op in capabilities["operations"]:
            assert op["name"] in tools
            assert tools[op["name"]].meta == {"taktus.eu/connector/v1": op}
    for op in capabilities["operations"]:
        assert op["name"].startswith(op["capability"] + ".")
        assert op["capability"] in capabilities["capabilities"]
        assert (op["effect"] == "read") == ("idempotency" not in op)


@pytest.mark.usefixtures("credentials")
async def test_no_credential_value_reaches_a_result_an_error_or_the_log(
    service: Service, capsys: pytest.CaptureFixture[str]
) -> None:
    connector = Connector(config(service))
    texts: list[str] = []
    for operation, input in (
        ("repository.issues.read", {"number": 1}),
        ("repository.issues.create", {"title": "t", "body": "b"}),
        ("repository.issues.read", {"number": 999}),
    ):
        result = await connector.call(operation, context("s", KEY), input)
        texts.append(json.dumps(result.structured_content))
        texts.extend(getattr(c, "text", "") for c in result.content)
    texts.append(capsys.readouterr().err)
    for text in texts:
        assert service.write_value not in text
        assert service.read_value not in text


# --- branches, labels, pipeline status ---------------------------------------------------------

BRANCH_INPUT = {
    "name": "taktus/issue-412",
    "base": "main",
    "message": "Pin the model",
    "files": [{"path": "docs/note.md", "content": "# Note\n"}],
}


@pytest.mark.usefixtures("credentials")
async def test_a_branch_created_for_a_step_is_created_once_across_a_restart(
    service: Service,
) -> None:
    """The branch is found by its name; the commit at its head carries the key as a trailer.
    A second connector with no memory of the first finds both and replays."""
    key = "run_01:branch:1-0123456789"
    error, first = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("branch", key),
        BRANCH_INPUT,
    )
    assert not error, first
    assert first["effect"]["replayed"] is False
    assert [r["kind"] for r in first["effect"]["records"]] == ["vcs.branch", "vcs.commit"]
    assert first["output"]["name"] == "taktus/issue-412"
    error, again = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("branch", key),
        BRANCH_INPUT,
    )
    assert not error
    assert again["effect"]["replayed"] is True
    assert again["output"]["sha"] == first["output"]["sha"]
    assert again["effect"]["records"] == first["effect"]["records"]
    assert service.state()[REPOSITORY]["branches"] == 2  # main and ours

    other = "run_01:branch:2-0123456789"
    error, conflict = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("branch", other),
        BRANCH_INPUT,
    )
    assert error
    assert conflict["cause"] == "conflict"
    assert conflict["effect"] == "none"


@pytest.mark.usefixtures("credentials")
async def test_a_branch_without_files_carries_an_empty_marked_commit(service: Service) -> None:
    key = "run_01:bare:1-0123456789"
    error, result = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("bare", key),
        {"name": "taktus/bare", "base": "main"},
    )
    assert not error
    assert result["output"]["base"] == "main"
    error, missing = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("bare", key),
        {"name": "taktus/other", "base": "nowhere"},
    )
    assert error
    assert missing["cause"] == "not_found"


@pytest.mark.usefixtures("credentials")
async def test_a_changed_file_keeps_the_mode_it_had(service: Service) -> None:
    """An executable file that a change touches stays executable (DEC-0020).

    The tree entry carries the mode, and a write that does not carry it forward makes the file
    plain. The first live run met exactly this: the coding worker changed `tools/preflight.sh`,
    the branch carried it as a plain file, and every job of the pipeline died on
    `Permission denied` before it ran a single check.
    """
    base = _base_with_executable(service, "tools/script.sh")
    error, result = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("modes", "run_01:modes:1-0123456789"),
        {
            "name": "taktus/modes",
            "base": base,
            "message": "change both",
            "files": [
                {"path": "tools/script.sh", "content": "#!/bin/sh\necho changed\n"},
                {"path": "docs/note.md", "content": "# Note\n"},
            ],
        },
    )
    assert not error, result
    modes = _tree_modes(service, str(result["output"]["sha"]))
    assert modes["tools/script.sh"] == "100755", "the executable stayed executable"
    assert modes["docs/note.md"] == "100644", "a new file is a plain file"


@pytest.mark.usefixtures("credentials")
async def test_a_new_file_marked_executable_arrives_executable(service: Service) -> None:
    """A file the base does not have arrives executable when its entry says so (issue #28).

    Without the flag the connector has nothing to go by for a new path and writes a plain
    file: a script a change adds would fail with `Permission denied` the first time anything
    ran it — DEC-0020's failure, one case further out. The flag wins over the base, both
    ways; a file without it keeps the base's mode as before.
    """
    base = _base_with_executable(service, "tools/script.sh")
    error, result = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("new-modes", "run_01:new-modes:1-0123456789"),
        {
            "name": "taktus/new-modes",
            "base": base,
            "message": "add a script",
            "files": [
                {"path": "tools/new.sh", "content": "#!/bin/sh\n", "executable": True},
                {"path": "tools/script.sh", "content": "plain now\n", "executable": False},
                {"path": "docs/new.md", "content": "# New\n"},
            ],
        },
    )
    assert not error, result
    modes = _tree_modes(service, str(result["output"]["sha"]))
    assert modes["tools/new.sh"] == "100755", "a new executable is executable"
    assert modes["tools/script.sh"] == "100644", "the flag wins over the base"
    assert modes["docs/new.md"] == "100644", "a new file without the flag is a plain file"

    error, refused = await call(
        Connector(config(service)),
        "repository.branches.create",
        context("new-modes", "run_01:new-modes:2-0123456789"),
        {
            "name": "taktus/bad-flag",
            "base": "main",
            "files": [{"path": "a.sh", "content": "", "executable": "yes"}],
        },
    )
    assert error
    assert refused["cause"] == "invalid"


@pytest.mark.usefixtures("credentials")
async def test_a_file_is_read_at_a_ref_and_names_the_commit_it_was_read_at(
    service: Service,
) -> None:
    """`repository.files.read` (issue #34): what a branch carries, byte for byte, with the
    commit the branch pointed at — so that the provenance of a step that read it says which
    version it read. A read is a read: no record, no replay."""
    connector = Connector(config(service))
    key = "run_01:read-file:1-0123456789"
    error, branch = await call(
        connector,
        "repository.branches.create",
        context("b", "run_01:files:1-0123456789"),
        {
            "name": "taktus/files",
            "base": "main",
            "files": [
                {"path": "docs/note.md", "content": "# Note\n\nsecond line\n"},
                {"path": "bin/blob", "content": "AAEC/w==", "encoding": "base64"},
            ],
        },
    )
    assert not error, branch
    error, text = await call(
        connector,
        "repository.files.read",
        context("read-file", key),
        {"path": "docs/note.md", "ref": "taktus/files"},
    )
    assert not error, text
    assert text["effect"] == {"kind": "read"}
    assert text["output"]["content"] == "# Note\n\nsecond line\n"
    assert text["output"]["encoding"] == "utf-8"
    assert text["output"]["commit"] == branch["output"]["sha"]
    assert text["output"]["ref"] == "taktus/files"
    assert text["output"]["size"] == len(b"# Note\n\nsecond line\n")
    assert text["consumption"]["quota_units"] == 2  # the ref, then the file

    error, binary = await call(
        connector,
        "repository.files.read",
        context("read-file", key),
        {"path": "bin/blob", "ref": branch["output"]["sha"]},
    )
    assert not error, binary
    assert binary["output"] == {
        "path": "bin/blob",
        "ref": branch["output"]["sha"],
        "commit": branch["output"]["sha"],
        "sha": binary["output"]["sha"],
        "size": 4,
        "content": "AAEC/w==",
        "encoding": "base64",
    }
    assert binary["consumption"]["quota_units"] == 1, "a commit needs no resolving"

    for input, cause in [
        ({"path": "docs/missing.md", "ref": "taktus/files"}, "not_found"),
        ({"path": "docs/note.md", "ref": "taktus/nowhere"}, "not_found"),
        ({"path": "docs", "ref": "taktus/files"}, "invalid"),
        ({"path": "../outside", "ref": "main"}, "invalid"),
        ({"path": "docs/note.md"}, "invalid"),
    ]:
        error, refused = await call(connector, "repository.files.read", context("r", key), input)
        assert error, input
        assert refused["cause"] == cause, (input, refused)
        assert refused["effect"] == "none"


def _base_with_executable(service: Service, path: str) -> str:
    """A branch of the fake service whose tree carries `path` as an executable file, built
    through the service's own object interface, so that the connector has a real base to
    preserve a mode from."""
    name = "with-executable"
    ref = _service_get(service, f"/repos/{REPOSITORY}/git/ref/heads/main")
    head = _service_get(service, f"/repos/{REPOSITORY}/git/commits/{ref['object']['sha']}")
    blob = _service_post(
        service, f"/repos/{REPOSITORY}/git/blobs", {"content": "#!/bin/sh\n", "encoding": "utf-8"}
    )
    tree = _service_post(
        service,
        f"/repos/{REPOSITORY}/git/trees",
        {
            "base_tree": head["tree"]["sha"],
            "tree": [{"path": path, "mode": "100755", "type": "blob", "sha": blob["sha"]}],
        },
    )
    commit = _service_post(
        service,
        f"/repos/{REPOSITORY}/git/commits",
        {"message": "an executable", "tree": tree["sha"], "parents": [ref["object"]["sha"]]},
    )
    _service_post(
        service,
        f"/repos/{REPOSITORY}/git/refs",
        {"ref": f"refs/heads/{name}", "sha": commit["sha"]},
    )
    return name


def _tree_modes(service: Service, commit_sha: str) -> dict[str, str]:
    commit = _service_get(service, f"/repos/{REPOSITORY}/git/commits/{commit_sha}")
    tree = _service_get(service, f"/repos/{REPOSITORY}/git/trees/{commit['tree']['sha']}")
    return {str(e["path"]): str(e["mode"]) for e in tree["tree"]}


def _service_get(service: Service, path: str) -> Json:
    answer = httpx.get(
        f"{service.url}{path}",
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    )
    answer.raise_for_status()
    result: Json = answer.json()
    return result


def _service_post(service: Service, path: str, body: Json) -> Json:
    answer = httpx.post(
        f"{service.url}{path}",
        json=body,
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5.0,
    )
    answer.raise_for_status()
    result: Json = answer.json()
    return result


@pytest.mark.usefixtures("credentials")
async def test_labels_are_their_own_mark(service: Service) -> None:
    key = "run_01:label:1-0123456789"
    connector = Connector(config(service))
    error, first = await call(
        connector,
        "repository.labels.set",
        context("label", key),
        {"number": 1, "labels": ["taktus"]},
    )
    assert not error
    assert first["effect"]["replayed"] is False
    assert first["output"]["labels"] == ["taktus"]
    assert first["effect"]["records"] == [{"kind": "label", "id": "1#taktus"}]
    error, again = await call(
        Connector(config(service)),
        "repository.labels.set",
        context("label", key),
        {"number": 1, "labels": ["taktus"]},
    )
    assert not error
    assert again["effect"]["replayed"] is True
    assert service.state()[REPOSITORY]["labels"] == 1


@pytest.mark.usefixtures("credentials")
async def test_the_pipeline_state_of_a_branch_is_the_pipelines_verdict(service: Service) -> None:
    connector = Connector(config(service))
    key = "run_01:ci:1-0123456789"
    error, before = await call(
        connector, "repository.pipelines.status", context("ci", key), {"ref": "main"}
    )
    assert not error
    assert before["effect"] == {"kind": "read"}
    assert before["output"]["state"] == "success"
    assert [r["name"] for r in before["output"]["runs"]] == ["ci"]

    service.control("/_fake/ci", {"conclusion": "failure"})
    await call(
        connector,
        "repository.branches.create",
        context("b", "run_01:b:1-0123456789"),
        {"name": "taktus/red", "base": "main"},
    )
    error, red = await call(
        connector, "repository.pipelines.status", context("ci", key), {"ref": "taktus/red"}
    )
    assert not error
    assert red["output"]["state"] == "failure"

    service.control("/_fake/ci", {"pending": True})
    await call(
        connector,
        "repository.branches.create",
        context("b", "run_01:b:2-0123456789"),
        {"name": "taktus/slow", "base": "main"},
    )
    error, slow = await call(
        connector, "repository.pipelines.status", context("ci", key), {"ref": "taktus/slow"}
    )
    assert not error
    assert slow["output"]["state"] == "pending"
    error, sha = await call(
        connector,
        "repository.pipelines.status",
        context("ci", key),
        {"ref": slow["output"]["sha"], "workflow": "nothing"},
    )
    assert not error
    assert sha["output"]["state"] == "none"
    error, gone = await call(
        connector, "repository.pipelines.status", context("ci", key), {"ref": "taktus/nowhere"}
    )
    assert error
    assert gone["cause"] == "not_found"
