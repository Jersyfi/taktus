"""The app stores connector reads an app's reviews on either store without the reviewer, and
publishes a reply marked by its own text, in one shape, so that a process runs on either; the
call's `platform` names the store (ADR-0207, ADR-0210).

Each store against the fake of its API under `tests/fakes/`, in a thread of this process, and
the connector served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import customer_reviews_service as first_store
from fakes import review_replies_service as second_store
from fakes.ports import free_port
from taktus_connectors.appstores.operations import Config
from taktus_connectors.appstores.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference


@dataclass(frozen=True)
class Store:
    name: str
    platform: str
    credential: str
    make_credential: Callable[[str], str]
    """The store's key as `STORES_KEY`, given the fake's address."""
    module: Any
    connector: Callable[[str], McpActionConnector]
    app: str
    reviews: tuple[str, ...]
    """The fake's reviews, rated 1, 2, 5 and 1, the third answered."""
    nickname: str
    """What the fake says of the reviewer, which no output may carry."""


STORES = {
    "first": Store(
        "first",
        "ios",
        "STORES_KEY",
        lambda url: first_store.credential(),
        first_store,
        lambda url: McpActionConnector(build_server(Config(url, url, timeout=5.0))),
        first_store.APP,
        ("rev-1", "rev-2", "rev-3", "rev-4"),
        "nickname1",
    ),
    "second": Store(
        "second",
        "android",
        "STORES_KEY",
        lambda url: second_store.credential(f"{url}/token"),
        second_store,
        lambda url: McpActionConnector(build_server(Config(url, url, timeout=5.0))),
        second_store.PACKAGE,
        ("gp:1", "gp:2", "gp:3", "gp:4"),
        "A Person",
    ),
}


@dataclass
class Running:
    store: Store
    url: str
    value: str

    def connector(self) -> McpActionConnector:
        return self.store.connector(self.url)

    def state(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.url}/_fake/state", timeout=5).json()
        return found


@pytest.fixture(params=sorted(STORES))
def store(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Running]:
    spec = STORES[request.param]
    url = f"http://127.0.0.1:{free_port()}"
    value = spec.make_credential(url)
    path = tmp_path / spec.credential
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{spec.credential}_FILE", str(path))
    server = spec.module.make_server("127.0.0.1", int(url.rsplit(":", 1)[1]), {value})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield Running(spec, url, value)
    server.shutdown()
    server.server_close()


def context(store: Store, step: str = "read") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_ops",
        run_id="run_reviews",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_reviews", step, 1),
        credentials=(CredentialReference(name=store.credential, injected_as="env"),),
    )


async def test_the_reviews_are_listed_without_the_reviewer(store: Running) -> None:
    result = await store.connector().call(
        "stores.reviews.list",
        context(store.store),
        {"platform": store.store.platform, "app": store.store.app},
    )
    assert result.effect.kind.value == "read"
    reviews = result.output["reviews"]
    assert {r["id"] for r in reviews} == set(store.store.reviews)
    assert result.output["complete"] is True
    first = next(r for r in reviews if r["id"] == store.store.reviews[0])
    assert first["rating"] == 1 and "export crashes" in first["text"]
    assert first["responded"] is False and first["response"] is None
    answered = next(r for r in reviews if r["id"] == store.store.reviews[2])
    assert answered["responded"] is True and answered["response"] == "Thank you!"
    assert set(first) == {
        "id", "rating", "title", "text", "territory", "language", "at", "version",
        "responded", "response",
    }  # fmt: skip
    text = json.dumps(result.output)
    assert store.store.nickname not in text and "device-1" not in text and "maker" not in text


async def test_the_ratings_asked_for_are_kept(store: Running) -> None:
    result = await store.connector().call(
        "stores.reviews.list",
        context(store.store),
        {"platform": store.store.platform, "app": store.store.app, "ratings": [1, 2]},
    )
    assert sorted(r["rating"] for r in result.output["reviews"]) == [1, 1, 2]


async def test_pages_are_followed_and_the_limit_bounds_the_answer(store: Running) -> None:
    module = store.store.module
    many = [
        module.review(n, 1 + n % 5) if store.store.name == "second" else module.review(1, 1)
        for n in range(1, 251)
    ]
    if store.store.name == "first":
        many = [{**r, "id": f"rev-{n}"} for n, r in enumerate(many, start=1)]
    httpx.post(f"{store.url}/_fake/reviews", content=json.dumps(many), timeout=5)  # noqa: ASYNC210
    connector = store.connector()
    every = await connector.call("stores.reviews.list", context(store.store), {
        "platform": store.store.platform, "app": store.store.app, "limit": 1000,
    })  # fmt: skip
    assert len({r["id"] for r in every.output["reviews"]}) == 250
    assert every.output["complete"] is True
    bounded = await connector.call(
        "stores.reviews.list",
        context(store.store),
        {"platform": store.store.platform, "app": store.store.app, "limit": 10},
    )
    assert len(bounded.output["reviews"]) == 10 and bounded.output["complete"] is False


async def test_one_review_is_read(store: Running) -> None:
    result = await store.connector().call(
        "stores.reviews.read",
        context(store.store),
        {
            "platform": store.store.platform,
            "app": store.store.app,
            "review": store.store.reviews[1],
        },
    )
    assert result.output["id"] == store.store.reviews[1] and result.output["rating"] == 2


async def test_a_reply_is_written_once_and_a_repeat_writes_nothing(store: Running) -> None:
    connector = store.connector()
    given = {
        "platform": store.store.platform,
        "app": store.store.app,
        "review": store.store.reviews[0],
        "text": "We are on it.",
    }
    first = await connector.call("stores.reviews.reply", context(store.store, "send"), given)
    assert first.effect.kind.value == "write" and first.effect.replayed is False
    again = await connector.call("stores.reviews.reply", context(store.store, "send"), given)
    assert again.effect.replayed is True
    assert [r.id for r in again.effect.records] == [r.id for r in first.effect.records]
    assert store.state()["written"] == [{"review": store.store.reviews[0], "text": "We are on it."}]
    read = await connector.call(
        "stores.reviews.read",
        context(store.store),
        {"platform": store.store.platform, "app": store.store.app, "review": given["review"]},
    )
    assert read.output["response"] == "We are on it."


async def test_a_response_of_another_text_is_replaced_only_when_asked(store: Running) -> None:
    connector = store.connector()
    given = {
        "platform": store.store.platform,
        "app": store.store.app,
        "review": store.store.reviews[2],
        "text": "Glad you like it.",
    }
    with pytest.raises(CallFailed) as failed:
        await connector.call("stores.reviews.reply", context(store.store, "send"), given)
    assert failed.value.error.cause.value == "conflict"
    assert store.state()["written"] == []
    replaced = await connector.call(
        "stores.reviews.reply", context(store.store, "send"), {**given, "replace": True}
    )
    assert replaced.effect.replayed is False
    assert store.state()["written"] == [{"review": given["review"], "text": "Glad you like it."}]


@pytest.mark.parametrize(
    ("operation", "input", "cause"),
    [
        ("stores.reviews.read", {"review": "../apps"}, "invalid"),
        ("stores.reviews.list", {"ratings": [0]}, "invalid"),
        ("stores.reviews.list", {"limit": 0}, "invalid"),
        ("stores.reviews.reply", {"review": "x", "text": ""}, "invalid"),
        ("stores.reviews.read", {"review": "unknown"}, "not_found"),
    ],
)
async def test_a_request_that_cannot_be_answered_is_refused(
    store: Running, operation: str, input: dict[str, object], cause: str
) -> None:
    with pytest.raises(CallFailed) as failed:
        await store.connector().call(
            operation,
            context(store.store),
            {"platform": store.store.platform, "app": store.store.app, **input},
        )
    assert failed.value.error.cause.value == cause
    assert "refused by the fake" not in (failed.value.error.detail or "")


async def test_a_key_the_store_does_not_admit_is_unauthenticated(
    store: Running, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other"
    other.write_text(store.store.make_credential(store.url), encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{store.store.credential}_FILE", str(other))
    with pytest.raises(CallFailed) as failed:
        await store.connector().call(
            "stores.reviews.list",
            context(store.store),
            {"platform": store.store.platform, "app": store.store.app},
        )
    assert failed.value.error.cause.value == "unauthenticated"
    garbled = tmp_path / "garbled"
    garbled.write_text("not-a-key", encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{store.store.credential}_FILE", str(garbled))
    with pytest.raises(CallFailed) as failed:
        await store.connector().call(
            "stores.reviews.list",
            context(store.store),
            {"platform": store.store.platform, "app": store.store.app},
        )
    assert failed.value.error.cause.value == "unauthenticated"


@pytest.mark.parametrize("name", sorted(STORES))
async def test_a_store_that_does_not_answer_is_unavailable_and_retryable(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = STORES[name]
    path = tmp_path / spec.credential
    nowhere = f"http://127.0.0.1:{free_port()}"
    path.write_text(spec.make_credential(nowhere), encoding="utf-8")
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{spec.credential}_FILE", str(path))
    with pytest.raises(CallFailed) as failed:
        await spec.connector(nowhere).call(
            "stores.reviews.list", context(spec), {"platform": spec.platform, "app": spec.app}
        )
    assert failed.value.error.cause.value == "unavailable"
    assert failed.value.error.retryable is True


def test_the_two_stores_are_served_by_one_declared_shape() -> None:
    from taktus_connectors.appstores import declaration

    def shape(declared: list[dict[str, Any]]) -> list[tuple[str, str, str | None]]:
        return [
            (op["name"], op["effect"], op.get("idempotency"))
            for op in declared
            if op["capability"] == "stores.reviews"
        ]

    assert shape(declaration.OPERATIONS) == [
        ("stores.reviews.list", "read", None),
        ("stores.reviews.read", "read", None),
        ("stores.reviews.reply", "write", "marked"),
    ], "one set of operations, the platform naming the store"
