"""The feedback portal connector reads a board's posts without their authors, creates a post for
a customer once and counts a customer's vote once (ADR-0207, UC-03 B-3.07).

Against the fake under `tests/fakes/feedback_service.py`, in a thread of this process. The
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import feedback_service
from fakes.ports import free_port
from taktus_connectors.canny.operations import Config
from taktus_connectors.canny.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "FEEDBACK_TOKEN"
BOARD = feedback_service.BOARD


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "feedback"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture
def portal() -> Iterator[str]:
    server = feedback_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(step: str = "read", attempt: int = 1) -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_support",
        run_id="run_wish",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_wish", step, attempt),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


def feedback(url: str) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


async def test_the_posts_of_a_board_are_listed_without_their_authors(portal: str) -> None:
    result = await feedback(portal).call("feedback.posts.list", context(), {"board": BOARD})
    assert result.effect.kind.value == "read"
    posts = result.output["posts"]
    assert [p["title"] for p in posts] == ["Dark mode", "Export to CSV", "Calendar sync"]
    assert posts[0] == {
        "id": "p0st3",
        "board": BOARD,
        "title": "Dark mode",
        "details": "Customers ask for dark mode.",
        "status": "open",
        "score": 2,
        "url": "https://example.canny.io/feature-requests/p/p0st3",
    }
    assert result.output["complete"] is True
    text = json.dumps(result.output)
    assert "@customer.example" not in text and "Person " not in text


async def test_a_search_narrows_the_posts(portal: str) -> None:
    result = await feedback(portal).call(
        "feedback.posts.list", context(), {"board": BOARD, "search": "csv"}
    )
    assert [p["id"] for p in result.output["posts"]] == ["p0st2"]


async def test_a_post_is_created_once_for_the_customer_and_a_repeat_finds_it(portal: str) -> None:
    connector = feedback(portal)
    wish = {
        "board": BOARD,
        "email": "person1@customer.example",
        "title": "Offline mode",
        "details": "The customer asks to work without a connection.",
    }
    first = await connector.call("feedback.posts.create", context("create"), wish)
    assert first.effect.kind.value == "write" and first.effect.replayed is False
    again = await connector.call("feedback.posts.create", context("create"), wish)
    assert again.effect.replayed is True
    assert again.output["id"] == first.output["id"]
    assert state(portal)["created"] == 1, "created once"
    listed = await connector.call("feedback.posts.list", context(), {"board": BOARD})
    made = next(p for p in listed.output["posts"] if p["id"] == first.output["id"])
    assert made["details"].startswith("The customer asks") and "[ref taktus-" in made["details"]
    assert "run_wish" not in made["details"], "a digest of the key, not the key"
    assert "person1" not in json.dumps(first.output)


async def test_a_vote_is_counted_once(portal: str) -> None:
    connector = feedback(portal)
    vote = {"post": "p0st1", "email": "person2@customer.example"}
    first = await connector.call("feedback.posts.vote", context("vote"), vote)
    assert first.effect.replayed is False and first.output == {"post": "p0st1", "counted": True}
    again = await connector.call("feedback.posts.vote", context("vote"), vote)
    assert again.effect.replayed is True
    assert state(portal)["voted"] == 1
    listed = await connector.call("feedback.posts.list", context(), {"board": BOARD})
    assert next(p for p in listed.output["posts"] if p["id"] == "p0st1")["score"] == 1


@pytest.mark.parametrize(
    ("operation", "input"),
    [
        ("feedback.posts.list", {"board": "unknownboard"}),
        ("feedback.posts.list", {"board": "../users"}),
        ("feedback.posts.list", {"board": BOARD, "limit": 0}),
        ("feedback.posts.vote", {"post": "p0st1", "email": "stranger@customer.example"}),
        ("feedback.posts.vote", {"post": "p0st1", "email": "no address"}),
        ("feedback.posts.create", {"board": BOARD, "email": "person1@customer.example"}),
    ],
)
async def test_a_request_that_cannot_be_answered_is_invalid(
    portal: str, operation: str, input: dict[str, object]
) -> None:
    with pytest.raises(CallFailed) as failed:
        await feedback(portal).call(operation, context("write"), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_key_the_portal_does_not_admit_is_unauthenticated(
    portal: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-key", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await feedback(portal).call("feedback.posts.list", context(), {"board": BOARD})
    assert failed.value.error.cause.value == "unauthenticated"


async def test_a_portal_that_does_not_answer_is_unavailable_and_retryable() -> None:
    with pytest.raises(CallFailed) as failed:
        await feedback(f"http://127.0.0.1:{free_port()}").call(
            "feedback.posts.list", context(), {"board": BOARD}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True
