"""A running step taken over and handed back, on the HTTP surface (ADR-0128, issue #404).

The routes hand the engine what the person asked, with the person's identity and tenant; a run
of another tenant, or one the predicate withholds, is answered `404` and the engine is never
asked; a refusal of the engine's is `409`; a key is needed. What the engine does is held by
`tests/components/run/test_takeover.py`.
"""

from __future__ import annotations

import httpx
import pytest

from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.domain.model import TakeoverRefused

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_a_step_is_taken_over_its_state_read_and_its_result_handed_back(
    client: Client,
) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")

    asked = await http.post(f"{base}/runs/run_1/steps/a/takeover", headers=bearer(key))
    assert asked.status_code == 202, asked.text
    assert asked.json() == {
        "takeover": "tko_1",
        "run_id": "run_1",
        "step_id": "a",
        "state": "asked",
        "read": "runs/run_1/takeovers/tko_1",
    }
    (command,) = given.takeovers.asked
    assert (command.run_id, command.step_id, command.actor, command.tenant) == (
        "run_1",
        "a",
        "idn_ada",
        TENANT,
    )

    pending = await http.get(f"{base}/runs/run_1/takeovers/tko_1", headers=bearer(key))
    assert pending.status_code == 404, "asked, not yet served"
    given.takeovers.states["tko_1"] = {"kind": "takeover.state", "goal": "g"}
    served = await http.get(f"{base}/runs/run_1/takeovers/tko_1", headers=bearer(key))
    assert served.status_code == 200 and served.json()["goal"] == "g"

    handed = await http.post(
        f"{base}/runs/run_1/takeovers/tko_1/hand-back",
        json={"result": {"answer": 42}},
        headers=bearer(key),
    )
    assert handed.status_code == 200, handed.text
    assert handed.json()["id"] == "run_1"
    (back,) = given.takeovers.handed
    assert (back.takeover, back.result, back.actor) == ("tko_1", {"answer": 42}, "idn_ada")


async def test_a_refusal_of_the_engine_is_a_conflict(client: Client) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    given.takeovers.refusal = TakeoverRefused("a take-over of it is asked or held already")
    response = await http.post(f"{base}/runs/run_1/steps/a/takeover", headers=bearer(key))
    assert response.status_code == 409 and "held already" in response.text
    late = await http.post(
        f"{base}/runs/run_1/takeovers/tko_1/hand-back", json={"result": 1}, headers=bearer(key)
    )
    assert late.status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/runs/run_9/steps/a/takeover"),
        ("GET", "/runs/run_9/takeovers/tko_1"),
        ("POST", "/runs/run_9/takeovers/tko_1/hand-back"),
    ],
)
async def test_a_run_of_another_tenant_is_answered_as_none_and_the_engine_is_not_asked(
    client: Client, method: str, path: str
) -> None:
    http, given, base = client
    await a_run(given, "run_9", tenant=OTHER)
    _, key = await given.identity.person(TENANT, "idn_ada")
    given.takeovers.states["tko_1"] = {"kind": "takeover.state"}
    response = await http.request(method, f"{base}{path}", json={"result": 1}, headers=bearer(key))
    assert response.status_code == 404 and OTHER not in response.text
    assert given.takeovers.asked == [] and given.takeovers.handed == []
    assert (await http.request(method, f"{base}{path}", json={"result": 1})).status_code == 401


async def test_a_run_the_predicate_withholds_is_not_taken_over(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    original = visibility.may_see

    def withheld(reader: Reader, run: RunRef) -> bool:
        return original(reader, run) and run.id != "run_1"

    monkeypatch.setattr(visibility, "may_see", withheld)
    response = await http.post(f"{base}/runs/run_1/steps/a/takeover", headers=bearer(key))
    assert response.status_code == 404
    assert given.takeovers.asked == []
