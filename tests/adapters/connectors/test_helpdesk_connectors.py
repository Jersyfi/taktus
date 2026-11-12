"""The two helpdesk connectors read tickets in one shape, add an internal note and close a ticket
with a tag, each once; the first also lists the help centre's articles and writes a draft that
is never published (ADR-0205).

Against the fakes under `tests/fakes/helpdesk_service.py` and `tests/fakes/support_desk_service.py`,
each in a thread of this process. The connectors are served in-process over MCP, as an instance
reaches them.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import helpdesk_service, support_desk_service
from fakes.ports import free_port
from taktus_connectors.freshdesk.operations import Config as SecondConfig
from taktus_connectors.freshdesk.server import build_server as second_server
from taktus_connectors.zendesk.operations import Config as FirstConfig
from taktus_connectors.zendesk.server import build_server as first_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

CREDENTIAL = "HELPDESK_TOKEN"
PAIR = "agent@product.example:tok-" + secrets.token_hex(8)
KEY = "key-" + secrets.token_hex(8)


@dataclass(frozen=True)
class Desk:
    name: str
    url: str
    connector: McpActionConnector

    def state(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.url}/_fake/state", timeout=5).json()
        return found


def _serve(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(params=["first", "second"])
def desk(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Desk]:
    path = tmp_path / "helpdesk"
    if request.param == "first":
        path.write_text(PAIR, encoding="utf-8")
        server = helpdesk_service.make_server("127.0.0.1", 0, {PAIR})
        url = _serve(server)
        connector = McpActionConnector(first_server(FirstConfig(url, timeout=5.0)))
    else:
        path.write_text(KEY, encoding="utf-8")
        server = support_desk_service.make_server("127.0.0.1", 0, {KEY})
        url = _serve(server)
        connector = McpActionConnector(second_server(SecondConfig(url, timeout=5.0)))
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))
    yield Desk(request.param, url, connector)
    server.shutdown()
    server.server_close()


def context(run: str = "run_desk", step: str = "act") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id=run,
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key(run, step, 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


async def test_tickets_are_listed_in_one_shape_without_the_requesters_address(desk: Desk) -> None:
    result = await desk.connector.call("helpdesk.tickets.list", context(), {"status": "all"})
    assert result.effect.kind.value == "read"
    tickets = result.output["tickets"]
    assert {t["id"] for t in tickets} == {"1", "2", "3", "4", "5"}
    first = next(t for t in tickets if t["id"] == "1")
    assert set(first) == {
        "id", "subject", "description", "status", "requester", "tags", "created_at", "updated_at",
    }  # fmt: skip
    assert first["subject"] == "Export fails" and first["status"] == "open"
    assert first["requester"] == "9001"
    assert result.output["complete"] is True
    assert "customer.example" not in json.dumps(result.output)


async def test_a_status_is_kept_and_comments_come_on_request(desk: Desk) -> None:
    result = await desk.connector.call(
        "helpdesk.tickets.list", context(), {"status": "solved", "with_comments": True}
    )
    solved = result.output["tickets"]
    assert sorted(t["id"] for t in solved) == ["3", "4"]
    three = next(t for t in solved if t["id"] == "3")
    assert three["description"].startswith("I want to use another e-mail address")
    assert [c["text"] for c in three["comments"]] == [
        "Open Settings, choose Account and enter the new address there."
    ]
    assert three["comments"][0]["public"] is True
    assert three["comments"][0]["from_requester"] is False
    unsolved = await desk.connector.call("helpdesk.tickets.list", context(), {})
    assert sorted(t["id"] for t in unsolved.output["tickets"]) == ["1", "2", "5"]


async def test_one_ticket_is_read_with_its_comments(desk: Desk) -> None:
    result = await desk.connector.call("helpdesk.tickets.read", context(), {"id": "1"})
    assert result.output["subject"] == "Export fails"
    assert result.output["description"] == "The CSV export stops with an error since Monday."
    assert [c["text"] for c in result.output["comments"]] == ["Thank you, we are looking into it."]


async def test_a_note_is_internal_and_written_once(desk: Desk) -> None:
    first = await desk.connector.call(
        "helpdesk.tickets.note", context(), {"id": "1", "text": "Sorted by Taktus."}
    )
    assert first.effect.kind.value == "write" and first.effect.replayed is False
    again = await desk.connector.call(
        "helpdesk.tickets.note", context(), {"id": "1", "text": "Sorted by Taktus."}
    )
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records] == [r.id for r in first.effect.records]
    state = desk.state()
    assert state["writes"] == 1
    ticket = next(t for t in state["tickets"] if t["id"] == 1)
    notes = ticket.get("comments", ticket.get("conversations"))
    written = [n for n in notes if "Sorted by Taktus." in (n.get("body") or "")]
    assert len(written) == 1
    assert written[0].get("public") is False or written[0].get("private") is True


async def test_a_ticket_is_closed_with_its_tag_and_the_tag_is_its_mark(desk: Desk) -> None:
    first = await desk.connector.call(
        "helpdesk.tickets.close", context(), {"id": "2", "tag": "sorted-bounce"}
    )
    assert first.effect.replayed is False and first.output["previous"] in ("new", "open")
    again = await desk.connector.call(
        "helpdesk.tickets.close", context("run_other"), {"id": "2", "tag": "sorted-bounce"}
    )
    assert again.effect.replayed is True, "solved with the tag already: nothing changes"
    read = await desk.connector.call("helpdesk.tickets.read", context(), {"id": "2"})
    assert read.output["status"] == "solved" and read.output["tags"] == ["sorted-bounce"]
    assert desk.state()["writes"] == 1


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("helpdesk.tickets.read", {"id": "../users"}),
        ("helpdesk.tickets.list", {"status": "lost"}),
        ("helpdesk.tickets.list", {"limit": 0}),
        ("helpdesk.tickets.list", {"with_comments": True, "limit": 26}),
        ("helpdesk.tickets.close", {"id": "2", "tag": "Not A Tag"}),
        ("helpdesk.tickets.note", {"id": "1", "text": ""}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    desk: Desk, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await desk.connector.call(operation, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_an_unknown_ticket_is_not_found(desk: Desk) -> None:
    with pytest.raises(CallFailed) as failed:
        await desk.connector.call("helpdesk.tickets.read", context(), {"id": "999"})
    assert failed.value.error.cause.value == "not_found"


async def test_a_key_the_helpdesk_does_not_admit_is_unauthenticated(
    desk: Desk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("someone@product.example:not-the-key", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await desk.connector.call("helpdesk.tickets.list", context(), {})
    assert failed.value.error.cause.value == "unauthenticated"
    assert "refused by the fake" not in (failed.value.error.detail or "")


@pytest.mark.parametrize("which", ["first", "second"])
async def test_a_helpdesk_that_does_not_answer_is_unavailable_and_retryable(
    which: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "helpdesk"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))
    url = f"http://127.0.0.1:{free_port()}"
    server = (
        first_server(FirstConfig(url, timeout=2.0))
        if which == "first"
        else second_server(SecondConfig(url, timeout=2.0))
    )
    with pytest.raises(CallFailed) as failed:
        await McpActionConnector(server).call("helpdesk.tickets.list", context(), {})
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


# --- the help centre -----------------------------------------------------------------------------


@pytest.fixture
def first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Desk]:
    path = tmp_path / "helpdesk"
    path.write_text(PAIR, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))
    server = helpdesk_service.make_server("127.0.0.1", 0, {PAIR})
    url = _serve(server)
    yield Desk("first", url, McpActionConnector(first_server(FirstConfig(url, timeout=5.0))))
    server.shutdown()
    server.server_close()


async def test_the_help_centre_articles_are_listed(first: Desk) -> None:
    result = await first.connector.call("helpcentre.articles.list", context(), {})
    assert result.output["complete"] is True
    assert result.output["articles"] == [
        {
            "id": "500",
            "title": "Resetting your password",
            "section": "100",
            "draft": False,
            "url": "https://example.zendesk.com/hc/en-us/articles/500",
            "labels": [],
            "updated_at": "2026-09-01T08:00:00Z",
        }
    ]


async def test_an_article_is_written_as_a_draft_once_and_never_published(first: Desk) -> None:
    input = {"section": "100", "title": "Changing your e-mail address", "body": "<p>Open…</p>"}
    made = await first.connector.call("helpcentre.articles.draft", context(), input)
    assert made.effect.replayed is False
    assert made.output["draft"] is True and made.output["published"] is False
    again = await first.connector.call("helpcentre.articles.draft", context(), input)
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records] == [r.id for r in made.effect.records]
    drafts = [a for a in first.state()["articles"] if a["title"] == input["title"]]
    assert len(drafts) == 1 and drafts[0]["draft"] is True


async def test_a_draft_in_a_section_the_help_centre_does_not_have_is_not_found(
    first: Desk,
) -> None:
    with pytest.raises(CallFailed) as failed:
        await first.connector.call(
            "helpcentre.articles.draft", context(), {"section": "999", "title": "T", "body": "B"}
        )
    assert failed.value.error.cause.value == "not_found"
