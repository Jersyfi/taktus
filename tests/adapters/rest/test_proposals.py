"""Proposals on the HTTP surface (UC-4.15, ADR-0091 §1 and §6, issue #294).

A changed bundle becomes a proposal with its difference; the active version is unchanged; a
bundle that would not register gives every finding; a process of another tenant, or none, is
answered alike; a key is needed; an open proposal is discarded once.
"""

from __future__ import annotations

import httpx

from .conftest import OTHER, TENANT, Services
from .test_process_level import bundle, register

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_a_changed_bundle_becomes_a_proposal_and_the_active_version_is_unchanged(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    response = await http.post(
        f"{base}/processes/invoices/proposals",
        json={"bundle": bundle("2", review=True), "request": "a person signs the draft"},
        headers=bearer(key),
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert (proposal["base_version"], proposal["version"], proposal["state"]) == (
        "1",
        "2",
        "proposed",
    )
    assert [(c["id"], c["change"]) for c in proposal["difference"]["steps"]] == [
        ("review", "added")
    ]
    level = (await http.get(f"{base}/levels/processes/invoices", headers=bearer(key))).json()
    assert level["process"]["version"] == "1", "nothing was registered"
    listed = (await http.get(f"{base}/processes/invoices/proposals", headers=bearer(key))).json()
    assert [p["id"] for p in listed["proposals"]] == [proposal["id"]]
    one = await http.get(
        f"{base}/processes/invoices/proposals/{proposal['id']}", headers=bearer(key)
    )
    assert one.json() == proposal


async def test_a_bundle_that_would_not_register_gives_every_finding(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    broken = bundle("2")
    del broken["steps"][0]["checks"]
    response = await http.post(
        f"{base}/processes/invoices/proposals", json={"bundle": broken}, headers=bearer(key)
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["findings"]
    listed = (await http.get(f"{base}/processes/invoices/proposals", headers=bearer(key))).json()
    assert listed["proposals"] == []


async def test_another_tenants_process_or_none_is_answered_alike_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"), tenant=OTHER)
    key = await given.linked()
    for process in ("invoices", "nothing"):
        response = await http.post(
            f"{base}/processes/{process}/proposals",
            json={"bundle": {**bundle("2"), "id": process}},
            headers=bearer(key),
        )
        assert response.status_code == 404, process
    missing = await http.post(f"{base}/processes/invoices/proposals", json={"bundle": bundle("2")})
    assert missing.status_code == 401
    assert TENANT != OTHER


async def test_an_open_proposal_is_discarded_once(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await given.linked()
    made = await http.post(
        f"{base}/processes/invoices/proposals", json={"bundle": bundle("2")}, headers=bearer(key)
    )
    path = f"{base}/processes/invoices/proposals/{made.json()['id']}/discard"
    first = await http.post(path, headers=bearer(key))
    assert first.status_code == 200 and first.json()["state"] == "discarded"
    assert (await http.post(path, headers=bearer(key))).status_code == 409
