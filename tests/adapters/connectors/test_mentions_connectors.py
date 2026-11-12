"""The two mentions connectors — a social network's server and a forum — answer a search in one
shape, without the author of a post (ADR-0207, UC-03 B-3.10).

Against the fakes under `tests/fakes/social_service.py` and `tests/fakes/forum_service.py`, in
a thread of this process. Each connector is served in-process over MCP, as an instance reaches
it.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import forum_service, social_service
from fakes.ports import free_port
from taktus_connectors.discourse.operations import Config as ForumConfig
from taktus_connectors.discourse.server import build_server as forum_server
from taktus_connectors.mastodon.operations import Config as SocialConfig
from taktus_connectors.mastodon.server import build_server as social_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

TOKEN = "tok-" + secrets.token_hex(8)
CREDENTIAL = "MENTIONS_TOKEN"
SEARCH = "mentions.search.query"


@dataclass(frozen=True)
class Source:
    name: str
    fake: Any
    connector: Callable[[str], McpActionConnector]
    replace: str


SOURCES = {
    "social": Source(
        "social",
        social_service,
        lambda url: McpActionConnector(social_server(SocialConfig(url, timeout=5.0))),
        "/_fake/statuses",
    ),
    "forum": Source(
        "forum",
        forum_service,
        lambda url: McpActionConnector(forum_server(ForumConfig(url, "support", timeout=5.0))),
        "/_fake/posts",
    ),
}


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "mentions"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(path))


@pytest.fixture(params=sorted(SOURCES))
def source(request: pytest.FixtureRequest) -> Iterator[tuple[Source, str]]:
    chosen = SOURCES[request.param]
    server = chosen.fake.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield chosen, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context() -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_support",
        run_id="run_mentions",
        step_id="search",
        attempt=1,
        idempotency_key=idempotency_key("run_mentions", "search", 1),
        credentials=(CredentialReference(name=CREDENTIAL, injected_as="env"),),
    )


async def test_the_matches_are_answered_in_one_shape_without_their_author(
    source: tuple[Source, str],
) -> None:
    chosen, url = source
    result = await chosen.connector(url).call(SEARCH, context(), {"query": "product"})
    assert result.effect.kind.value == "read"
    mentions = result.output["mentions"]
    assert len(mentions) == result.output["count"] >= 3
    assert result.output["complete"] is True
    for mention in mentions:
        assert set(mention) == {"id", "url", "text", "created_at", "source"}
        assert mention["source"] == chosen.name
        assert "product" in mention["text"].lower()
        assert "<" not in mention["text"]
        assert mention["url"].startswith("https://") or mention["url"].startswith(url)
    text = json.dumps(result.output)
    assert "Person " not in text and "avatar" not in text and "person4@" not in text


async def test_since_keeps_the_matches_from_that_day_on(source: tuple[Source, str]) -> None:
    chosen, url = source
    result = await chosen.connector(url).call(
        SEARCH, context(), {"query": "product", "since": "2026-11-01"}
    )
    assert result.output["mentions"]
    assert all(m["created_at"] >= "2026-11-01" for m in result.output["mentions"])


async def test_pages_are_followed_and_the_limit_bounds_the_answer(
    source: tuple[Source, str],
) -> None:
    chosen, url = source
    if chosen.name == "social":
        many = [
            social_service.status(n % 90 + 1, f"product {n}", "2026-11-05T00:00:00Z")
            for n in range(130)
        ]
        for n, record in enumerate(many):
            record["id"] = str(200000 + n)
    else:
        many = [
            forum_service.post(n, 1000 + n, f"product {n}", "2026-11-05T00:00:00Z")
            for n in range(130)
        ]
    async with httpx.AsyncClient() as client:
        await client.post(f"{url}{chosen.replace}", content=json.dumps(many), timeout=5)
    connector = chosen.connector(url)
    every = await connector.call(SEARCH, context(), {"query": "product", "limit": 400})
    assert every.output["count"] == 130 and every.output["complete"] is True
    assert len({m["id"] for m in every.output["mentions"]}) == 130
    assert every.consumption.quota_units == (4 if chosen.name == "social" else 3)
    bounded = await connector.call(SEARCH, context(), {"query": "product", "limit": 50})
    assert bounded.output["count"] == 50 and bounded.output["complete"] is False


@pytest.mark.parametrize(
    "input",
    [{"query": ""}, {"query": "product", "since": "2026-13-40"}, {"query": "product", "limit": 0}],
)
async def test_a_search_that_cannot_be_answered_is_invalid(
    source: tuple[Source, str], input: dict[str, object]
) -> None:
    chosen, url = source
    with pytest.raises(CallFailed) as failed:
        await chosen.connector(url).call(SEARCH, context(), input)
    assert failed.value.error.cause.value == "invalid"


async def test_a_token_the_source_does_not_admit_is_unauthenticated(
    source: tuple[Source, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chosen, url = source
    wrong = tmp_path / "wrong"
    wrong.write_text("not-the-token", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CREDENTIAL}_FILE", str(wrong))
    with pytest.raises(CallFailed) as failed:
        await chosen.connector(url).call(SEARCH, context(), {"query": "product"})
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize("name", sorted(SOURCES))
async def test_a_source_that_does_not_answer_is_unavailable_and_retryable(name: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await (
            SOURCES[name]
            .connector(f"http://127.0.0.1:{free_port()}")
            .call(SEARCH, context(), {"query": "product"})
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


async def test_the_forum_is_asked_as_the_configured_user() -> None:
    server = forum_service.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        await SOURCES["forum"].connector(url).call(SEARCH, context(), {"query": "product"})
        async with httpx.AsyncClient() as client:
            seen = (await client.get(f"{url}/_fake/state", timeout=5)).json()
        assert seen["usernames"] == ["support"]
    finally:
        server.shutdown()
        server.server_close()
