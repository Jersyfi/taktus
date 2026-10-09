"""The chat connector's actions against the fake of its service.

What the contract asks of an outward operation, tried where it matters: a message posted for a
step is posted once, across a restart of the connector, whether it goes into a thread or to the
top of a conversation. Every error is a classified failure. A credential is read at the moment
of the call — from the file its variable names, as every secret here is — and appears nowhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taktus.adapters.driven.connectors.slack import declaration
from taktus.adapters.driven.connectors.slack.operations import MARK_TYPE
from taktus.adapters.driven.connectors.slack.server import Config, Connector

from .conftest import CHAT_READ, CHAT_WRITE, ChatService

type Json = dict[str, Any]

CONVERSATION = "C0000000001"
THREAD = "1700000000.000100"


def context(step: str, key: str | None = None, credential: str | None = CHAT_WRITE) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_7f3a2c",
        "run_id": "run_chat",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key or f"taktus:run_chat:{step}:1",
        "credentials": [] if credential is None else [{"name": credential, "injected_as": "env"}],
    }


def connector(service: ChatService) -> Connector:
    return Connector(Config(target=service.url, timeout=5.0))


async def call(service: ChatService, name: str, ctx: Json, input: Json) -> tuple[bool, Json]:
    result = await connector(service).call(name, ctx, input)
    content = result.structured_content
    assert isinstance(content, dict)
    return bool(result.is_error), content


@pytest.mark.usefixtures("chat_credentials")
async def test_the_answer_to_an_unknown_sender_lands_once_in_their_thread(
    chat_service: ChatService,
) -> None:
    """`channel.chat.reply` is how Taktus answers a sender it cannot place (ADR-0040): the
    reply address of the intake, posted and found again as any post is."""
    input = {"address": CONVERSATION, "thread": THREAD, "text": "Link this account first."}
    key = "taktus:intake:offer:0123456789abcdef"
    failed, first = await call(chat_service, "channel.chat.reply", context("reply", key=key), input)
    assert not failed, first
    failed, again = await call(chat_service, "channel.chat.reply", context("reply", key=key), input)
    assert not failed and again["effect"]["replayed"] is True
    replies = [m for m in chat_service.messages(CONVERSATION) if m.get("thread_ts") == THREAD]
    assert [m["text"] for m in replies] == ["Link this account first."]


@pytest.mark.usefixtures("chat_credentials")
async def test_a_reply_posted_for_a_step_is_posted_once_across_a_restart(
    chat_service: ChatService,
) -> None:
    input = {"address": CONVERSATION, "thread": THREAD, "text": "The pull request is open."}
    failed, first = await call(chat_service, "chat.threads.post", context("reply"), input)
    assert not failed, first
    # A second connector, with no memory of the first: the service holds the mark.
    failed, again = await call(chat_service, "chat.threads.post", context("reply"), input)
    assert not failed, again
    assert first["effect"]["replayed"] is False and again["effect"]["replayed"] is True
    assert again["effect"]["records"] == first["effect"]["records"]
    assert first["effect"]["kind"] == "delivery"
    replies = [m for m in chat_service.messages(CONVERSATION) if m.get("thread_ts") == THREAD]
    assert len(replies) == 1
    assert replies[0]["text"] == "The pull request is open.", "the text carries no mark"
    assert replies[0]["metadata"]["event_type"] == MARK_TYPE
    failed, other = await call(
        chat_service, "chat.threads.post", context("reply", key="taktus:run_chat:reply:2"), input
    )
    assert not failed and other["effect"]["replayed"] is False
    assert len([m for m in chat_service.messages(CONVERSATION) if m.get("thread_ts")]) == 2


@pytest.mark.usefixtures("chat_credentials")
async def test_a_message_at_the_top_of_a_conversation_is_found_again_too(
    chat_service: ChatService,
) -> None:
    input = {"address": "D0000000001", "text": "A question about issue 412."}
    _, first = await call(chat_service, "chat.threads.post", context("ask"), input)
    _, again = await call(chat_service, "chat.threads.post", context("ask"), input)
    assert again["effect"]["replayed"] is True
    assert again["output"]["ts"] == first["output"]["ts"]
    assert chat_service.state()["D0000000001"] == 2  # the seed and one message


@pytest.mark.usefixtures("chat_credentials")
async def test_a_thread_is_read_oldest_first_with_its_authors(chat_service: ChatService) -> None:
    await call(
        chat_service,
        "chat.threads.post",
        context("reply"),
        {"address": CONVERSATION, "thread": THREAD, "text": "First reply."},
    )
    failed, read = await call(
        chat_service,
        "chat.threads.read",
        context("read"),
        {"address": CONVERSATION, "thread": THREAD},
    )
    assert not failed, read
    assert read["effect"] == {"kind": "read"}
    assert read["output"]["complete"] is True
    messages = read["output"]["messages"]
    assert [m["text"] for m in messages] == ["The first message.", "First reply."]
    assert messages[0]["author"] == {"account": "U0000000001", "kind": "person"}
    assert messages[1]["author"]["kind"] == "automation"
    assert read["consumption"] == {"quota_units": 1}


@pytest.mark.usefixtures("chat_credentials")
@pytest.mark.parametrize(
    ("name", "ctx", "input", "cause"),
    [
        (
            "chat.threads.read",
            context("r", credential=None),
            {"address": CONVERSATION, "thread": THREAD},
            "unauthenticated",
        ),
        (
            "chat.threads.post",
            context("p", credential=CHAT_READ),
            {"address": CONVERSATION, "text": "x"},
            "forbidden",
        ),
        (
            "chat.threads.read",
            context("r"),
            {"address": "C0000000999", "thread": THREAD},
            "not_found",
        ),
        (
            "chat.threads.post",
            context("p"),
            {"address": CONVERSATION, "thread": "1700000000.999999", "text": "x"},
            "not_found",
        ),
        ("chat.threads.post", context("p"), {"address": CONVERSATION, "text": " "}, "invalid"),
        ("chat.threads.read", context("r"), {"address": "not a conversation"}, "invalid"),
    ],
)
async def test_every_error_is_a_classified_failure(
    chat_service: ChatService, name: str, ctx: Json, input: Json, cause: str
) -> None:
    failed, error = await call(chat_service, name, ctx, input)
    assert failed
    assert error["class"] == "failure" and error["cause"] == cause
    assert error["effect"] == "none" and error["retryable"] is False
    assert len(chat_service.messages(CONVERSATION)) == 1, "nothing was posted"


@pytest.mark.usefixtures("chat_credentials")
async def test_an_outage_is_unavailable_and_may_be_repeated(chat_service: ChatService) -> None:
    chat_service.control("/_fake/outage", {"on": True})
    try:
        failed, error = await call(
            chat_service,
            "chat.threads.post",
            context("p"),
            {"address": CONVERSATION, "text": "x"},
        )
    finally:
        chat_service.control("/_fake/outage", {"on": False})
    assert failed and error["cause"] == "unavailable" and error["retryable"] is True


async def test_the_token_is_read_from_the_file_its_variable_names(
    chat_service: ChatService, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chat_service.reset()
    token = tmp_path / "chat-token"
    token.write_text(chat_service.write_value + "\n", encoding="utf-8")
    monkeypatch.delenv(CHAT_WRITE, raising=False)
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CHAT_WRITE}_FILE", str(token))
    failed, result = await call(
        chat_service,
        "chat.threads.post",
        context("p"),
        {"address": CONVERSATION, "text": "From a file."},
    )
    assert not failed, result
    monkeypatch.setenv(f"TAKTUS_CREDENTIAL_{CHAT_WRITE}_FILE", str(tmp_path / "missing"))
    monkeypatch.setenv(CHAT_WRITE, chat_service.write_value)
    failed, error = await call(
        chat_service, "chat.threads.read", context("r"), {"address": CONVERSATION, "thread": THREAD}
    )
    assert failed and error["cause"] == "unauthenticated", "a named file wins, even when absent"


@pytest.mark.usefixtures("chat_credentials")
async def test_no_credential_value_reaches_a_result_an_error_or_the_log(
    chat_service: ChatService, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = []
    for name, ctx, input in [
        ("chat.threads.post", context("p"), {"address": CONVERSATION, "text": "x"}),
        ("chat.threads.read", context("r"), {"address": CONVERSATION, "thread": THREAD}),
        ("chat.threads.post", context("p", credential=CHAT_READ), {"address": CONVERSATION}),
        ("chat.threads.read", context("r"), {"address": "C0000000999", "thread": THREAD}),
    ]:
        _, content = await call(chat_service, name, ctx, input)
        seen.append(json.dumps(content))
    text = "\n".join(seen) + json.dumps(declaration.capabilities()) + capsys.readouterr().err
    assert chat_service.write_value not in text
    assert chat_service.read_value not in text
