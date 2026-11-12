"""The second website connector drafts a post once per key as a draft document, reads it, and
publishes it once, against the fake content lake — the operations and outputs of the first, so
that B-8.08 runs on either.

The fake under `tests/fakes/content_lake_service.py` runs in a thread of this process; the
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
from fakes import content_lake_service
from taktus_connectors.sanity.operations import Config, mark
from taktus_connectors.sanity.portable import blocks
from taktus_connectors.sanity.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "sk" + secrets.token_hex(16)
STUDIO = "https://studio.example.org"
DRAFT = {
    "title": "Release 2.0",
    "content": "<p>What <strong>changed</strong>.</p>"
    "<h2>Fixed</h2><ul><li>One</li><li>Two</li></ul>",
    "excerpt": "What changed",
}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "WEBSITE_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WEBSITE_TOKEN_FILE", str(path))


@pytest.fixture
def lake() -> Iterator[str]:
    server = content_lake_service.make_server("127.0.0.1", 0, {TOKEN})
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


def connector(url: str, **given: Any) -> McpActionConnector:
    """A fresh connector: it remembers nothing of an earlier call."""
    return McpActionConnector(build_server(Config(url, studio=STUDIO, timeout=5.0, **given)))


def documents(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()["documents"]
    return found


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


def document(url: str, identifier: str) -> dict[str, Any]:
    found = httpx.get(
        f"{url}/v2025-02-19/data/doc/production/{identifier}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=5,
    ).json()["documents"]
    assert len(found) == 1
    result: dict[str, Any] = found[0]
    return result


def edit(url: str, identifier: str) -> None:
    """A person changes the draft in the Studio."""
    changed = {**document(url, identifier), "title": "Release 2.0, edited"}
    httpx.post(
        f"{url}/v2025-02-19/data/mutate/production",
        json={"mutations": [{"createOrReplace": changed}]},
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=5,
    ).raise_for_status()


async def test_a_post_is_read_with_its_status_title_and_link(lake: str) -> None:
    result = await connector(lake).call("website.posts.read", context("read"), {"id": "post-1"})
    assert result.effect.kind.value == "read"
    assert result.output == {
        "id": "post-1",
        "status": "publish",
        "title": "Hello world",
        "link": f"{STUDIO}/intent/edit/id=post-1;type=post",
        "modified": "2026-10-01T08:00:00Z",
    }
    assert TOKEN not in str(result.output)


async def test_a_draft_is_a_draft_document_created_once_per_key(lake: str) -> None:
    first = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
    identifier = mark(idempotency_key("run_site", "draft", 1))
    assert first.effect.replayed is False
    assert first.output == {
        "id": identifier,
        "status": "draft",
        "link": f"{STUDIO}/intent/edit/id={identifier};type=post",
        "slug": identifier,
    }
    stored = document(lake, f"drafts.{identifier}")
    assert stored["_type"] == "post" and stored["title"] == "Release 2.0"
    assert stored["excerpt"] == "What changed"
    assert stored["slug"] == {"_type": "slug", "current": identifier}
    assert stored["body"] == blocks(DRAFT["content"])
    assert identifier not in documents(lake), "nothing is published"
    again = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
    assert again.effect.replayed is True and again.output == first.output
    assert [r.id for r in again.effect.records] == [r.id for r in first.effect.records]
    assert len(documents(lake)) == 2
    other = await connector(lake).call("website.posts.draft", context("draft", 2), DRAFT)
    assert other.effect.replayed is False and other.output["id"] != first.output["id"]


async def test_a_draft_is_published_once_and_a_repeat_publishes_nothing(lake: str) -> None:
    drafted = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
    identifier = drafted.output["id"]
    published = await connector(lake).call(
        "website.posts.publish", context("publish"), {"id": identifier}
    )
    assert published.effect.replayed is False and published.output["status"] == "publish"
    assert set(published.output) == {"id", "status", "link", "slug"}
    after = state(lake)
    assert after["published"] == [identifier]
    assert identifier in after["documents"] and f"drafts.{identifier}" not in after["documents"]
    again = await connector(lake).call(
        "website.posts.publish", context("publish"), {"id": identifier}
    )
    assert again.effect.replayed is True and again.output["status"] == "publish"
    assert [r.id for r in again.effect.records] == [r.id for r in published.effect.records]
    # The published post keeps its identifier, so the draft's repeat still finds it.
    repeat = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
    assert repeat.effect.replayed is True and repeat.output["id"] == identifier
    assert state(lake)["published"] == [identifier]


async def test_a_draft_changed_after_it_was_read_is_a_conflict(
    lake: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from taktus_connectors.sanity import operations

    drafted = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
    identifier = drafted.output["id"]
    versions = operations._versions

    async def read_then_edited(*args: Any) -> Any:
        found = await versions(*args)
        edit(lake, f"drafts.{identifier}")
        return found

    monkeypatch.setattr(operations, "_versions", read_then_edited)
    with pytest.raises(CallFailed) as changed:
        await connector(lake).call("website.posts.publish", context("publish"), {"id": identifier})
    assert changed.value.error.cause.value == "conflict"
    assert f"drafts.{identifier}" in documents(lake), "the person's draft stays a draft"


async def test_what_the_api_refuses_maps_to_the_contracts_causes(lake: str) -> None:
    with pytest.raises(CallFailed) as missing:
        await connector(lake).call("website.posts.publish", context("publish"), {"id": "nosuch"})
    assert missing.value.error.cause.value == "not_found"
    for wrong in ({"id": "drafts.post-1"}, {"id": 1}, {"id": "two words"}):
        with pytest.raises(CallFailed) as refused:
            await connector(lake).call("website.posts.read", context("read"), wrong)
        assert refused.value.error.cause.value == "invalid"
    with pytest.raises(CallFailed) as dataset:
        await connector(lake, dataset="staging").call(
            "website.posts.read", context("read"), {"id": "post-1"}
        )
    assert dataset.value.error.cause.value == "not_found"
    with pytest.raises(CallFailed) as old:
        drafted = await connector(lake).call("website.posts.draft", context("draft"), DRAFT)
        await connector(lake, api_version="v2021-06-07").call(
            "website.posts.publish", context("publish"), {"id": drafted.output["id"]}
        )
    assert old.value.error.cause.value == "not_found", "actions need v2024-05-23"


async def test_a_token_the_api_does_not_admit_is_unauthenticated(
    lake: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER"
    path.write_text("sk-wrong", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_FILE", str(path))
    with pytest.raises(CallFailed) as refused:
        await connector(lake).call("website.posts.draft", context("draft", name="OTHER"), DRAFT)
    assert refused.value.error.cause.value == "unauthenticated"
    assert "sk-wrong" not in refused.value.error.detail
    assert len(documents(lake)) == 1, "nothing was created"


def test_the_post_s_html_becomes_portable_text_of_the_block_type_s_defaults() -> None:
    found = blocks(
        "<h2>Added</h2><p>A <em>new</em> <a href='https://x.example'>page</a>.</p>"
        "<ol><li>First</li></ol><script>alert(1)</script>"
    )
    assert [(b["style"], b.get("listItem")) for b in found] == [
        ("h2", None),
        ("normal", None),
        ("normal", "number"),
    ]
    assert found[1]["children"] == [
        {"_type": "span", "_key": "b1s0", "text": "A ", "marks": []},
        {"_type": "span", "_key": "b1s1", "text": "new", "marks": ["em"]},
        {"_type": "span", "_key": "b1s2", "text": " page.", "marks": []},
    ]
    assert "alert" not in str(found) and "x.example" not in str(found)
    assert found == blocks(
        "<h2>Added</h2><p>A <em>new</em> <a href='https://x.example'>page</a>.</p>"
        "<ol><li>First</li></ol><script>alert(1)</script>"
    )
