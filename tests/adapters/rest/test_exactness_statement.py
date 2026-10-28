"""The exactness statement where its reader is, on the HTTP surface (UC-6.9 §1, #224).

The process level and every run show the statement of the version they show, with all four
parts; the overview shows it per process. What every level carries is the statement the process
component generates from the version, unchanged: no level edits, shortens or rewrites it.
"""

from __future__ import annotations

from typing import Any

import httpx

from taktus.components.process.application.service.register_version import statement_of

from .conftest import TENANT, Services, a_run
from .test_process_level import bearer, bundle, register

type Client = tuple[httpx.AsyncClient, Services, str]


def generated(version: str) -> dict[str, Any]:
    return statement_of(bundle(version)).as_document()


async def test_the_process_level_carries_the_statement_of_its_version_unchanged(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    _, key = await given.identity.person(TENANT, "idn_ada")
    level = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    statement = level["exactness"]
    assert statement == generated("1")
    assert [p["title"] for p in statement["parts"]] == [
        "Which checks apply",
        "What they cover",
        "What they do not cover",
        "The residual risk",
    ]
    assert any("not yet measured" in line for line in statement["parts"][3]["lines"])


async def test_a_run_carries_the_statement_of_the_version_it_executes(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    run = await a_run(given)
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, run.model_copy(update={"process_version": "invoices@1"}))
    _, key = await given.identity.person(TENANT, "idn_ada")
    level = (await http.get(f"{base}/levels/runs/{run.id}", headers=bearer(key))).json()
    assert level["exactness"] == generated("1")


async def test_a_run_of_no_registered_version_carries_no_invented_statement(
    client: Client,
) -> None:
    http, given, base = client
    run = await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    level = (await http.get(f"{base}/levels/runs/{run.id}", headers=bearer(key))).json()
    assert level.get("exactness") is None


async def test_the_overview_carries_the_statement_per_process(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    await register(given, bundle("2", review=True))
    _, key = await given.identity.person(TENANT, "idn_ada")
    overview = (await http.get(f"{base}/levels/overview", headers=bearer(key))).json()
    (process,) = [p for area in overview["areas"] for p in area["processes"]]
    assert process["exactness"] == generated("2")
