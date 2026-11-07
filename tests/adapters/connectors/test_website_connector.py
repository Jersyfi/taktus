"""The website connector drafts a post once per key, reads it, and publishes it once, against
the fake website.

The fake under `tests/fakes/website_service.py` runs in a thread of this process; the connector
is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import website_service
from taktus_connectors.wordpress.operations import Config, mark
from taktus_connectors.wordpress.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "editor:" + secrets.token_hex(12)
DRAFT = {"title": "Release 2.0", "content": "<p>What changed.</p>", "excerpt": "What changed"}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "WEBSITE_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WEBSITE_TOKEN_FILE", str(path))


@pytest.fixture
def site() -> Iterator[str]:
    server = website_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(step: str, attempt: int = 1, name: str = "WEBSITE_TOKEN") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_site",
        run_id="run_site",
        step_id=step,
        attempt=attempt,
        idempotency_key=idempotency_key("run_site", step, attempt),
        credentials=(CredentialReference(name=name, injected_as="env"),),
    )


def connector(url: str) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, timeout=5.0)))


def posts(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["posts"]
    return found


def schedule(url: str, identifier: int) -> None:
    """A person schedules the post in the site."""
    user, _, password = TOKEN.partition(":")
    httpx.post(
        f"{url}/wp-json/wp/v2/posts/{identifier}",
        json={"status": "future"},
        auth=(user, password),
        timeout=5,
    ).raise_for_status()


async def test_a_post_is_read_with_its_status_title_and_address(site: str) -> None:
    result = await connector(site).call("website.posts.read", context("read"), {"id": 1})
    assert result.effect.kind.value == "read"
    assert result.output == {
        "id": 1,
        "status": "publish",
        "title": "Hello world",
        "link": f"{site}/hello-world/",
        "modified": "2026-10-01T08:00:00",
    }
    assert TOKEN.split(":")[1] not in str(result.output)


async def test_a_draft_is_created_once_per_key_and_found_again_by_a_fresh_connector(
    site: str,
) -> None:
    first = await connector(site).call("website.posts.draft", context("draft"), DRAFT)
    assert first.effect.replayed is False and first.output["status"] == "draft"
    assert first.output["slug"] == mark(idempotency_key("run_site", "draft", 1))
    again = await connector(site).call("website.posts.draft", context("draft"), DRAFT)
    assert again.effect.replayed is True and again.output == first.output
    assert [r.id for r in again.effect.records] == [r.id for r in first.effect.records]
    assert len(posts(site)) == 2
    other = await connector(site).call("website.posts.draft", context("draft", 2), DRAFT)
    assert other.effect.replayed is False and other.output["id"] != first.output["id"]


async def test_a_draft_is_published_once_and_a_repeat_publishes_nothing(site: str) -> None:
    drafted = await connector(site).call("website.posts.draft", context("draft"), DRAFT)
    identifier = drafted.output["id"]
    published = await connector(site).call(
        "website.posts.publish", context("publish"), {"id": identifier}
    )
    assert published.effect.replayed is False and published.output["status"] == "publish"
    again = await connector(site).call(
        "website.posts.publish", context("publish"), {"id": identifier}
    )
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records] == [r.id for r in published.effect.records]
    # A published draft keeps its slug, so the draft's repeat still finds it.
    repeat = await connector(site).call("website.posts.draft", context("draft"), DRAFT)
    assert repeat.effect.replayed is True and repeat.output["id"] == identifier


async def test_a_scheduled_post_is_a_conflict_and_a_missing_one_not_found(site: str) -> None:
    drafted = await connector(site).call("website.posts.draft", context("draft"), DRAFT)
    schedule(site, drafted.output["id"])
    with pytest.raises(CallFailed) as scheduled:
        await connector(site).call(
            "website.posts.publish", context("publish"), {"id": drafted.output["id"]}
        )
    assert scheduled.value.error.cause.value == "conflict"
    assert posts(site)[str(drafted.output["id"])]["status"] == "future"
    with pytest.raises(CallFailed) as missing:
        await connector(site).call("website.posts.publish", context("publish"), {"id": 99})
    assert missing.value.error.cause.value == "not_found"
    for wrong in ({"id": 0}, {"id": True}):
        with pytest.raises(CallFailed) as refused:
            await connector(site).call("website.posts.read", context("read"), wrong)
        assert refused.value.error.cause.value == "invalid"


async def test_a_credential_the_site_does_not_admit_is_unauthenticated(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for value in ("editor:wrong-password", "no-colon"):
        path = tmp_path / "OTHER"
        path.write_text(value, encoding="utf-8")
        monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_FILE", str(path))
        with pytest.raises(CallFailed) as refused:
            await connector(site).call("website.posts.draft", context("draft", name="OTHER"), DRAFT)
        assert refused.value.error.cause.value == "unauthenticated"
        assert "wrong-password" not in refused.value.error.detail
    assert len(posts(site)) == 1, "nothing was created"
