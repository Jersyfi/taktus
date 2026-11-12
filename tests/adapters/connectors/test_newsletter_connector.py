"""The newsletter connector drafts a campaign once per key, reads it, and sends it once,
against the fake newsletter service.

The fake under `tests/fakes/newsletter_service.py` runs in a thread of this process; the
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import newsletter_service
from taktus_connectors.mailchimp.operations import Config, mark
from taktus_connectors.mailchimp.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "key-" + secrets.token_hex(8) + "-us6"
DRAFT = {
    "list": "list-1",
    "subject": "November news",
    "text": "What changed.\n\nAnd what comes next.",
    "from_name": "Example",
    "reply_to": "news@example.org",
}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "NEWSLETTER_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_NEWSLETTER_TOKEN_FILE", str(path))


@pytest.fixture
def service() -> Iterator[str]:
    server = newsletter_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(step: str, attempt: int = 1, name: str = "NEWSLETTER_TOKEN") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_news",
        run_id="run_news",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_news", step, attempt),
        credentials=(CredentialReference(name=name, injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


def empty_campaign(url: str) -> dict[str, Any]:
    """A campaign somebody created in the service without a subject or content."""
    found: dict[str, Any] = httpx.post(
        f"{url}/3.0/campaigns",
        json={"type": "regular", "recipients": {"list_id": "list-1"}, "settings": {}},
        auth=("any", TOKEN),
        timeout=5,
    ).json()
    return found


async def test_a_campaign_is_read_with_its_audience_size_and_never_an_address(
    service: str,
) -> None:
    result = await connector(service).call(
        "newsletter.broadcasts.read", context("read"), {"id": "c-seeded"}
    )
    assert result.effect.kind.value == "read"
    assert result.output == {
        "id": "c-seeded",
        "web_id": 1,
        "status": "sent",
        "list": "list-1",
        "recipients": 1200,
        "emails_sent": 1200,
        "send_time": "2026-10-01T08:00:00+00:00",
    }
    assert "@" not in str(result.output) and TOKEN not in str(result.output)


async def test_a_draft_is_created_once_per_key_and_found_again_by_a_fresh_connector(
    service: str,
) -> None:
    first = await connector(service).call("newsletter.broadcasts.draft", context("draft"), DRAFT)
    assert first.effect.replayed is False and first.output["status"] == "save"
    assert first.output["recipients"] == 1200
    again = await connector(service).call("newsletter.broadcasts.draft", context("draft"), DRAFT)
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records] == [r.id for r in first.effect.records]
    campaigns = state(service)["campaigns"]
    assert len(campaigns) == 2, "one campaign seeded, one drafted"
    drafted = campaigns[first.output["id"]]
    assert drafted["title"] == mark(idempotency_key("run_news", "draft", 1))
    assert drafted["subject"] == "November news" and state(service)["sent"] == []
    other = await connector(service).call("newsletter.broadcasts.draft", context("draft", 2), DRAFT)
    assert other.effect.replayed is False and other.output["id"] != first.output["id"]


async def test_a_draft_is_sent_once_and_a_repeat_sends_nothing(service: str) -> None:
    drafted = await connector(service).call("newsletter.broadcasts.draft", context("draft"), DRAFT)
    identifier = drafted.output["id"]
    sent = await connector(service).call(
        "newsletter.broadcasts.send", context("send"), {"id": identifier}
    )
    assert sent.effect.replayed is False and sent.output["status"] == "sending"
    assert state(service)["sent"] == [identifier]
    again = await connector(service).call(
        "newsletter.broadcasts.send", context("send"), {"id": identifier}
    )
    assert again.effect.replayed is True and again.output["status"] == "sent"
    assert [r.id for r in again.effect.records] == [r.id for r in sent.effect.records]
    assert state(service)["sent"] == [identifier]


async def test_what_the_api_refuses_maps_to_the_contracts_causes(service: str) -> None:
    with pytest.raises(CallFailed) as missing:
        await connector(service).call(
            "newsletter.broadcasts.send", context("send"), {"id": "nosuch"}
        )
    assert missing.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as audience:
        await connector(service).call(
            "newsletter.broadcasts.draft", context("draft"), {**DRAFT, "list": "list-9"}
        )
    assert audience.value.error.cause.value == "invalid"
    for wrong in ({**DRAFT, "reply_to": "nobody"}, {**DRAFT, "subject": ""}):
        with pytest.raises(CallFailed) as refused:
            await connector(service).call("newsletter.broadcasts.draft", context("draft"), wrong)
        assert refused.value.error.cause.value == "invalid"
    assert len(state(service)["campaigns"]) == 1, "nothing was created"


async def test_a_campaign_not_ready_to_send_is_invalid_and_nothing_is_sent(
    service: str,
) -> None:
    created = empty_campaign(service)
    with pytest.raises(CallFailed) as refused:
        await connector(service).call(
            "newsletter.broadcasts.send", context("send"), {"id": created["id"]}
        )
    assert refused.value.error.cause.value == "invalid"
    assert "Bad Request" in refused.value.error.detail
    assert state(service)["sent"] == []


async def test_a_key_the_service_does_not_admit_is_unauthenticated(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER"
    path.write_text("key-wrong", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_FILE", str(path))
    with pytest.raises(CallFailed) as refused:
        await connector(service).call(
            "newsletter.broadcasts.read", context("read", name="OTHER"), {"id": "c-seeded"}
        )
    assert refused.value.error.cause.value == "unauthenticated"
    assert "key-wrong" not in refused.value.error.detail
