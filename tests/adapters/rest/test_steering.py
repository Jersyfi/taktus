"""A message to a running step, on the HTTP surface (ADR-0156 §7, issue #624).

The route hands the engine the text with the person's identity and tenant; a run of another
tenant, or one the predicate withholds, is answered `404` and the engine is never asked; a
refusal of the engine's is `409` and names why; a key is needed. What the engine does is held by
`tests/components/run/test_steering.py`.
"""

from __future__ import annotations

import httpx
import pytest

from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.domain.model import MessageRefused

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

TEXT = {"text": "use the second mirror"}


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_a_message_is_handed_to_the_engine_as_the_person(client: Client) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    asked = await http.post(f"{base}/runs/run_1/steps/a/messages", json=TEXT, headers=bearer(key))
    assert asked.status_code == 202, asked.text
    assert asked.json() == {
        "message": "msg_0001",
        "run_id": "run_1",
        "step_id": "a",
        "state": "asked",
    }
    (command,) = given.takeovers.steered
    assert (command.run_id, command.step_id, command.text, command.actor, command.tenant) == (
        "run_1",
        "a",
        "use the second mirror",
        "idn_ada",
        TENANT,
    )


async def test_a_refusal_names_why(client: Client) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    given.takeovers.refusal = MessageRefused("the worker worker.x declares no steering")
    response = await http.post(
        f"{base}/runs/run_1/steps/a/messages", json=TEXT, headers=bearer(key)
    )
    assert response.status_code == 409 and "declares no steering" in response.text


async def test_an_empty_or_long_text_does_not_validate(client: Client) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    for text in ("", "x" * 8001):
        response = await http.post(
            f"{base}/runs/run_1/steps/a/messages", json={"text": text}, headers=bearer(key)
        )
        assert response.status_code == 422
    assert given.takeovers.steered == []


async def test_a_run_one_may_not_see_is_answered_as_none_and_the_engine_is_not_asked(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    http, given, base = client
    await a_run(given, "run_9", tenant=OTHER)
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    other = await http.post(f"{base}/runs/run_9/steps/a/messages", json=TEXT, headers=bearer(key))
    assert other.status_code == 404 and OTHER not in other.text
    original = visibility.may_see

    def withheld(reader: Reader, run: RunRef) -> bool:
        return original(reader, run) and run.id != "run_1"

    monkeypatch.setattr(visibility, "may_see", withheld)
    hidden = await http.post(f"{base}/runs/run_1/steps/a/messages", json=TEXT, headers=bearer(key))
    assert hidden.status_code == 404, "an identity without the right to steer the run"
    assert (await http.post(f"{base}/runs/run_1/steps/a/messages", json=TEXT)).status_code == 401
    assert given.takeovers.steered == []
