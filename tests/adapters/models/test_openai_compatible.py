"""The model port over the chat-completions dialect, against a fake endpoint in a thread: the
prompt goes out as messages, the answer comes back as a completion with its usage, the
credential goes into the header and nowhere else, and every refusal is a `ModelError` that
names the endpoint and never the key."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator

import pytest
from fakes import model_service

from taktus.adapters.driven.models import OpenAiCompatibleModel, StaticModelPool
from taktus.ports.configuration import Secret
from taktus.ports.model import ModelError, Prompt

KEY = "key-" + secrets.token_hex(8)


@pytest.fixture
def endpoint() -> Iterator[tuple[str, model_service.Script]]:
    server, script = model_service.make_server("127.0.0.1", 0, token=KEY)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", script
    finally:
        server.shutdown()
        server.server_close()


async def test_a_prompt_becomes_messages_and_the_answer_a_completion(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    model = OpenAiCompatibleModel(url, "fake-model", credential=Secret(KEY), timeout=5.0)
    completion = await model.complete(
        Prompt(system="Be brief.", user="Issue #11: report git", max_output_tokens=64)
    )
    assert completion.text.startswith("## Acceptance criteria")
    assert "Issue #11: report git" in completion.text, "the prompt reached the endpoint"
    assert completion.model == "fake-model" and completion.finish == "stop"
    assert completion.tokens_in > 0 and completion.tokens_out > 0
    (request,) = script.requests
    assert request["model"] == "fake-model" and request["max_tokens"] == 64
    assert [m["role"] for m in request["messages"]] == ["system", "user"]


async def test_a_refusal_is_a_model_error_without_the_credential(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    wrong = OpenAiCompatibleModel(url, "fake-model", credential=Secret("not-" + KEY), timeout=5.0)
    with pytest.raises(ModelError, match="answered 401") as refused:
        await wrong.complete(Prompt(user="x"))
    assert KEY not in str(refused.value) and "not-" + KEY not in str(refused.value)
    none = OpenAiCompatibleModel(url, "fake-model", timeout=5.0)
    with pytest.raises(ModelError, match="401"):
        await none.complete(Prompt(user="x"))
    script.status = 503
    with pytest.raises(ModelError, match="503"):
        await OpenAiCompatibleModel(url, "m", credential=Secret(KEY), timeout=5.0).complete(
            Prompt(user="x")
        )
    script.status = 200
    script.finish = "length"
    cut = await OpenAiCompatibleModel(url, "m", credential=Secret(KEY), timeout=5.0).complete(
        Prompt(user="x")
    )
    assert cut.finish == "length"


async def test_an_endpoint_that_is_down_is_a_model_error() -> None:
    down = OpenAiCompatibleModel("http://127.0.0.1:9/v1", "m", timeout=1.0)
    with pytest.raises(ModelError, match="did not answer"):
        await down.complete(Prompt(user="x"))


async def test_the_pool_resolves_by_purpose_or_every_purpose() -> None:
    model = OpenAiCompatibleModel("http://127.0.0.1:9/v1", "m")
    pool = StaticModelPool([("model.endpoint", ["reasoning"], model, "m")])
    assert (await pool.resolve("reasoning")) is not None
    assert await pool.resolve("triage") is None
    every = StaticModelPool([("model.endpoint", ["*"], model, "m")])
    resolved = await every.resolve("triage")
    assert resolved is not None and resolved.adapter == "model.endpoint" and resolved.version == "m"
