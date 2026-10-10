"""The overview on the HTTP surface (ADR-0067, issue #191).

A registered process appears in its area with how many of its runs work and wait; the figures
equal what the read API's runs give by the run component's own definitions; another tenant's
runs are not counted; a key is needed.
"""

from __future__ import annotations

from typing import Any

import httpx

from taktus.components.run.domain.model import WAITING, WORKING, Run, RunState

from .conftest import TENANT, Services, a_run
from .test_process_level import bundle, register

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def stored(given: Services, run_id: str, state: RunState, tenant: str = TENANT) -> None:
    run = await a_run(given, run_id, tenant=tenant)
    moved = run.model_copy(update={"process_version": "invoices@1", "state": state})
    async with given.persistence.transaction(tenant):
        await given.runs.put(tenant, moved)


def process(level: dict[str, Any], process_id: str) -> dict[str, Any]:
    [area] = level["areas"]
    found: dict[str, Any] = next(p for p in area["processes"] if p["id"] == process_id)
    return found


async def test_a_process_is_found_in_its_area_with_how_busy_it_is(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    await stored(given, "run_1", RunState.RUNNING)
    await stored(given, "run_2", RunState.WAITING_HUMAN)
    await stored(given, "run_3", RunState.FINISHED)
    await stored(given, "run_9", RunState.RUNNING, tenant="other")
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.get(f"{base}/levels/overview", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    level = answer.json()
    assert [a["id"] for a in level["areas"]] == [TENANT]
    invoices = process(level, "invoices")
    assert (invoices["working"], invoices["waiting"]) == (1, 1)
    assert invoices["autonomy_level"] == 2 and invoices["active_version"] == "1"
    assert "1 run working, 1 waiting" in invoices["text"]

    listed = (await http.get(f"{base}/runs", headers=bearer(key))).json()["runs"]
    runs = [Run.model_validate(r) for r in listed if r["process_version"].startswith("invoices@")]
    assert invoices["working"] == sum(r.state in WORKING for r in runs)
    assert invoices["waiting"] == sum(r.state in WAITING for r in runs)


async def test_the_overview_needs_a_key(client: Client) -> None:
    http, _, base = client
    assert (await http.get(f"{base}/levels/overview")).status_code == 401
