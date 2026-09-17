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
