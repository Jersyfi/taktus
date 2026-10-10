"""The read API answers an authenticated reader, by the one visibility predicate (issue #186).

`GET /runs`, `GET /runs/{run_id}` and `GET /runs/{run_id}/ledger` read the account key from
`Authorization: Bearer` and nowhere else. A reader sees the runs of their own identity's tenant,
whatever tenant a request names. The three reads and the stream of changes ask the same
predicate, `components/reporting/domain/service/visibility.py` (ADR-0055 §5): a predicate that
withholds a run withholds it from every one of them.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

READS = ("/runs", "/runs/run_1", "/runs/run_1/ledger")


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def refused(response: httpx.Response) -> None:
    assert response.status_code == 401, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert "run_1" not in response.text, "a refusal says nothing about what exists"


@pytest.mark.parametrize("path", READS)
async def test_each_read_without_a_key_that_proves_an_identity_is_401(
    client: Client, path: str
) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    _, key = await given.identity.person(TENANT, "idn_ada")
    refused(await http.get(f"{base}{path}"))
    refused(await http.get(f"{base}{path}", headers=bearer("not-a-key")))
    refused(await http.get(f"{base}{path}", headers={"Authorization": f"Basic {key}"}))
    refused(await http.get(f"{base}{path}", headers={"Authorization": key}))
    for name in ("key", "access_token", "api_key", "authorization"):
        refused(await http.get(f"{base}{path}", params={name: key}))
    await given.identities.issue_key(TENANT, "idn_ada")  # the old key stops working
    refused(await http.get(f"{base}{path}", headers=bearer(key)))


async def test_a_reader_sees_their_own_tenant_and_naming_another_does_not_widen_it(
    client: Client,
) -> None:
    http, given, base = client
    await a_run(given, "run_1")
    await a_run(given, "run_9", tenant=OTHER)
    _, key = await given.identity.person(TENANT, "idn_ada")
    _, theirs = await given.identity.person(OTHER, "idn_bob")
    for named in ({}, {"tenant": OTHER}, {"tenant": TENANT}):
        listed = (await http.get(f"{base}/runs", params=named, headers=bearer(key))).json()
        assert listed["tenant"] == TENANT and [r["id"] for r in listed["runs"]] == ["run_1"]
        for path in ("/runs/run_9", "/runs/run_9/ledger"):
            response = await http.get(f"{base}{path}", params=named, headers=bearer(key))
            assert response.status_code == 404, f"{path} {named}: another tenant's run"
            assert OTHER not in response.text
    listed = await http.get(f"{base}/runs", params={"tenant": TENANT}, headers=bearer(theirs))
    assert [r["id"] for r in listed.json()["runs"]] == ["run_9"], "the other way round as well"
    assert (await http.get(f"{base}/runs/run_1", headers=bearer(theirs))).status_code == 404


async def seen_by_every_path(http: httpx.AsyncClient, base: str, key: str) -> dict[str, set[str]]:
    """Which of run_1 and run_2 each of the four paths shows the reader."""
    runs = (await http.get(f"{base}/runs", headers=bearer(key))).json()["runs"]
    seen: dict[str, set[str]] = {"GET /runs": {r["id"] for r in runs}}
    seen["GET /runs/{id}"] = {
        r
        for r in ("run_1", "run_2")
        if (await http.get(f"{base}/runs/{r}", headers=bearer(key))).status_code == 200
    }
    seen["GET /runs/{id}/ledger"] = {
        r
        for r in ("run_1", "run_2")
        if (await http.get(f"{base}/runs/{r}/ledger", headers=bearer(key))).status_code == 200
    }
    return seen


async def snapshot_of_the_stream(
    http: httpx.AsyncClient, given: Services, base: str, key: str
) -> set[str]:
    """The runs the stream's snapshot shows; the stream is ended by retiring its key."""
    asked = asyncio.create_task(http.get(f"{base}/changes", headers=bearer(key)))
    await asyncio.sleep(0.2)
    await given.identities.issue_key(TENANT, "idn_ada")
    async with asyncio.timeout(5):
        response = await asked
    assert response.status_code == 200, response.text
    data = response.text.split("\n\n")[1].split("\n")[-1]
    snapshot: dict[str, Any] = json.loads(data.removeprefix("data: "))
    return {r["id"] for r in snapshot["runs"]}


@pytest.mark.parametrize("withheld", [set(), {"run_2"}, {"run_1", "run_2"}])
async def test_the_three_reads_and_the_stream_ask_the_same_predicate(
    client: Client, monkeypatch: pytest.MonkeyPatch, withheld: set[str]
) -> None:
    """The predicate is replaced by one that withholds some runs of the reader's own tenant.
    Every path must follow it; a path that held its own copy of the rule would show them."""
    http, given, base = client
    await a_run(given, "run_1")
    await a_run(given, "run_2")
    _, key = await given.identity.person(TENANT, "idn_ada")
    original = visibility.may_see
    asked: list[str] = []

    def narrowed(reader: Reader, run: RunRef) -> bool:
        asked.append(run.id)
        return original(reader, run) and run.id not in withheld

    monkeypatch.setattr(visibility, "may_see", narrowed)
    expected = {"run_1", "run_2"} - withheld
    seen = await seen_by_every_path(http, base, key)
    seen["GET /changes"] = await snapshot_of_the_stream(http, given, base, key)
    assert seen == dict.fromkeys(seen, expected), "a path shows a run another withholds"
    assert {"run_1", "run_2"} <= set(asked), "the predicate was asked"


def test_no_module_holds_its_own_reference_to_the_predicate() -> None:
    """Replacing the predicate reaches a caller only through the module: a module that
    imported the function by name would keep the original and escape the test above."""
    source = Path(visibility.__file__).parents[4]
    holders = [
        str(path.relative_to(source))
        for path in source.rglob("*.py")
        if re.search(r"import[^\n]*\bmay_see\b", path.read_text(encoding="utf-8"))
    ]
    assert holders == []
