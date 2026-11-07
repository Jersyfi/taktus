"""The work tracker connector over a REST API: the open tasks read without their assignee,
one task read, and a reminder written once, marked (ADR-0209, UC-03 B-5.01).

Against the fake under `tests/fakes/task_rest_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fakes import task_rest_service
from fakes.ports import free_port
from taktus_connectors.jira.operations import Config
from taktus_connectors.jira.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "ops@team.example:" + secrets.token_hex(8)
CREDENTIAL = "TASKS_TOKEN"


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "tasks"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def tracker() -> Iterator[str]:
    server = task_rest_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(attempt: int = 1, run: str = "run_tasks") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id=run,
        step_id="remind",
        attempt=attempt,
        idempotency_key=idempotency_key(run, "remind", attempt),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def tasks(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, "TSK", timeout=5.0)))


def state(url: str) -> dict[str, object]:
    found: dict[str, object] = httpx.get(f"{url}/_fake/state", timeout=5.0).json()
    return found


async def test_the_open_tasks_are_listed_without_their_assignee(tracker: str) -> None:
    result = await tasks(tracker).call("tasks.items.list", context(), {})
    assert result.effect.kind.value == "read"
    items = result.output["items"]
    assert [t["key"] for t in items] == ["TSK-1", "TSK-2", "TSK-3", "TSK-4"], "done is left out"
    assert set(items[0]) == {
        "id", "key", "title", "due", "days_overdue", "state", "created_at", "updated_at", "url",
    }  # fmt: skip
    assert items[0]["days_overdue"] == 10 and items[2]["days_overdue"] == 0
    assert items[3]["due"] is None and items[3]["days_overdue"] is None
    assert result.output["complete"] is True
    text = json.dumps(result.output)
    assert "Person 1" not in text and "@team.example" not in text


async def test_overdue_by_days_keeps_the_tasks_due_that_long_ago(tracker: str) -> None:
    connector = tasks(tracker)
    late = await connector.call("tasks.items.list", context(), {"overdue_by_days": 1})
    assert [t["key"] for t in late.output["items"]] == ["TSK-1", "TSK-2"]
    week = await connector.call("tasks.items.list", context(), {"overdue_by_days": 7})
    assert [t["key"] for t in week.output["items"]] == ["TSK-1"]


async def test_pages_are_followed_and_the_limit_bounds_the_answer(tracker: str) -> None:
    many = [task_rest_service.issue(n) for n in range(1, 251)]
    httpx.post(f"{tracker}/_fake/issues", content=json.dumps(many), timeout=5.0)
    connector = tasks(tracker)
    result = await connector.call("tasks.items.list", context(), {})
    assert len(result.output["items"]) == 250 and result.output["complete"] is True
    assert result.consumption.quota_units == 3, "three pages of at most 100"
    bounded = await connector.call("tasks.items.list", context(), {"limit": 150})
    assert len(bounded.output["items"]) == 150 and bounded.output["complete"] is False


async def test_one_task_is_read_by_its_key(tracker: str) -> None:
    result = await tasks(tracker).call("tasks.items.read", context(), {"id": "TSK-5"})
    assert result.output["key"] == "TSK-5" and result.output["open"] is False
    assert result.output["url"] == f"{tracker}/browse/TSK-5"


async def test_a_reminder_is_written_once_and_a_repeat_finds_its_mark(tracker: str) -> None:
    connector = tasks(tracker)
    given = {"id": "TSK-1", "text": "This task is past its due date."}
    first = await connector.call("tasks.items.remind", context(), given)
    assert first.effect.kind.value == "write" and first.effect.replayed is False
    again = await connector.call("tasks.items.remind", context(), given)
    assert again.effect.replayed is True
    assert again.output["comment"] == first.output["comment"]
    [written] = state(tracker)["comments"]  # type: ignore[misc]
    assert written["issue"] == "TSK-1"
    last = written["body"]["content"][-1]["content"][0]["text"]
    assert last == f"Taktus reference: {idempotency_key('run_tasks', 'remind', 1)}"
    other = await connector.call("tasks.items.remind", context(attempt=2), given)
    assert other.effect.replayed is False, "another key is another reminder"


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("tasks.items.read", {"id": "TSK-999"}),
        ("tasks.items.read", {"id": "../search"}),
        ("tasks.items.read", {"id": "OPS-1"}),
        ("tasks.items.list", {"limit": 0}),
        ("tasks.items.list", {"overdue_by_days": -1}),
        ("tasks.items.remind", {"id": "TSK-1", "text": ""}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    tracker: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await tasks(tracker).call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"
    assert "refused by the fake" not in (failed.value.error.detail or "")


async def test_a_key_the_tracker_does_not_admit_is_unauthenticated(
    tracker: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-key", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await tasks(tracker).call("tasks.items.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_an_absent_site_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as absent:
        await tasks(f"http://127.0.0.1:{free_port()}").call("tasks.items.list", context(), {})
    assert absent.value.error.cause.value == "unavailable"
