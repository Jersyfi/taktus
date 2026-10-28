"""The error tracking connector lists the issues of an organisation, page after page, and reads
one; it never copies a person, and maps the provider's refusals to the contract's causes
(ADR-0150, issue #447).

Against the fake under `tests/fakes/error_tracking_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import error_tracking_service
from fakes.ports import free_port

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.sentry.operations import Config
from taktus.adapters.driven.connectors.sentry.server import build_server
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "ERRORS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "errors"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


def _serve(count: int) -> Iterator[str]:
    server = error_tracking_service.make_server("127.0.0.1", 0, {TOKEN}, count)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def tracker() -> Iterator[str]:
    yield from _serve(3)


@pytest.fixture
def busy() -> Iterator[str]:
    """A tracker with more issues than one page holds."""
    yield from _serve(250)


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_read",
        step_id="read",
        attempt=1,
        idempotency_key=idempotency_key("run_read", "read", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def errors(url: str, organization: str = "example") -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, organization, timeout=5.0)))


async def test_issues_are_listed_without_a_person(tracker: str) -> None:
    result = await errors(tracker).call("errors.issues.list", context(), {"period": "24h"})
    assert result.effect.kind.value == "read"
    issues = result.output["issues"]
    assert [i["id"] for i in issues] == ["1001", "1002", "1003"]
    first = issues[0]
    assert first == {
        "id": "1001",
        "short_id": "APP-1",
        "title": "TypeError: value 0 is undefined",
        "culprit": "handler_0",
        "level": "error",
        "status": "unresolved",
        "project": "app",
        "count": 100,
        "users": 10,
        "first_seen": "2026-10-20T08:00:00Z",
        "last_seen": "2026-10-27T08:00:00Z",
        "permalink": "https://errors.example/issues/1001/",
    }
    assert "A Person" not in str(result.output), "an assignee is never copied (principle 14)"
    assert result.output["complete"] is True
    assert result.consumption.quota_units == 1


async def test_a_project_keeps_only_its_issues(tracker: str) -> None:
    result = await errors(tracker).call("errors.issues.list", context(), {"project": "api"})
    assert [i["project"] for i in result.output["issues"]] == ["api"]


async def test_pages_are_followed_up_to_the_limit(busy: str) -> None:
    every = await errors(busy).call("errors.issues.list", context(), {"limit": 1000})
    assert len(every.output["issues"]) == 250
    assert every.output["complete"] is True
    assert every.consumption.quota_units == 3

    bounded = await errors(busy).call("errors.issues.list", context(), {"limit": 150})
    assert len(bounded.output["issues"]) == 150
    assert bounded.output["complete"] is False
    assert bounded.consumption.quota_units == 2


async def test_one_issue_is_read(tracker: str) -> None:
    result = await errors(tracker).call("errors.issues.read", context(), {"id": 1002})
    assert result.output["short_id"] == "API-2"
    assert result.output["count"] == 99


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("errors.issues.list", {"period": "yesterday"}),
        ("errors.issues.list", {"sort": "loudest"}),
        ("errors.issues.list", {"limit": 0}),
        ("errors.issues.list", {"project": "Not A Slug"}),
        ("errors.issues.read", {"id": "abc"}),
        ("errors.issues.read", {"id": "999999"}),
    ],
)
async def test_a_call_that_cannot_be_answered_is_invalid(
    tracker: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await errors(tracker).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_an_unknown_organization_is_invalid(tracker: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await errors(tracker, "elsewhere").call("errors.issues.list", context(), {})
    assert failed.value.error.cause.value == "invalid"


async def test_a_token_the_provider_does_not_admit_is_unauthenticated(
    tracker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await errors(tracker).call("errors.issues.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_provider_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await errors(f"http://127.0.0.1:{free_port()}").call("errors.issues.list", context(), {})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
