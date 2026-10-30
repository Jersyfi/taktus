"""The organisation seen as value streams, on the HTTP surface (UC-15.6, ADR-0159).

Only the owner declares a stream; the map and the swimlanes are read from the records of the
processes on each request and store nothing; the structure (`org_path`) is overlaid on the role
lanes and stays as it is; another tenant sees none of it; no figure names a person.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.domain.model import RunState

from .conftest import OTHER, TENANT, Services, a_run
from .test_process_level import bearer
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]


def bundle(process: str, role: str) -> dict[str, Any]:
    return {
        "id": process,
        "version": "1",
        "name": process.title(),
        "autonomy": {"level": 2, "reason": "a test", "toward_next": "nothing"},
        "steps": [
            {
                "id": "prepare",
                "method": "rule",
                "reason": "a fixed value",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": 1},
            },
            {
                "id": "decide",
                "method": "human",
                "reason": "it binds the organisation",
                "rejected": [],
                "role": role,
                "depends_on": ["prepare"],
            },
        ],
        "limits": {"quota": {"units": 5}},
    }


STREAM = {
    "name": "Order to cash",
    "kind": "core",
    "trigger": "A customer wants to buy",
    "outcome": "the customer has what they paid for",
    "role": "sales",
    "processes": ["order", "invoice"],
}


async def world(given: Services) -> dict[str, str]:
    """Two processes whose people sit in two units, and a key for each person by role."""
    keys: dict[str, str] = {}
    for name, path, roles in [
        ("idn_owner", (TENANT,), ("owner",)),
        ("idn_ada", (TENANT, "sales"), ("sales",)),
        ("idn_bo", (TENANT, "sales"), ("sales",)),
        ("idn_cy", (TENANT, "finance"), ("accounting",)),
    ]:
        _, keys[name] = await given.identities.add(TENANT, name, path, roles=roles)
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    for process, role in [("order", "sales"), ("invoice", "accounting")]:
        await register.execute(
            RegisterProcessVersion(bundle(process, role), tenant=TENANT, by="idn_owner")
        )
    return keys


def stored(given: Services) -> tuple[str, int]:
    """Everything the memory persistence holds, to show that a read writes nothing."""
    tables = repr(sorted((k, repr(v)) for k, v in given.persistence._tables.items()))
    return tables, sum(len(e) for e in given.persistence._ledger.values())


async def test_only_the_owner_declares_a_stream_and_a_changed_one_is_a_new_revision(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    path = f"{base}/streams/order-to-cash"
    assert is_problem(await http.put(path, json=STREAM), 401)
    assert is_problem(await http.put(path, json=STREAM, headers=bearer(keys["idn_ada"])), 403)
    first = await http.put(path, json=STREAM, headers=bearer(keys["idn_owner"]))
    assert first.status_code == 200 and first.json()["id"] == "order-to-cash@1"
    changed = {**STREAM, "outcome": "the customer is paid up"}
    second = await http.put(path, json=changed, headers=bearer(keys["idn_owner"]))
    assert second.json()["id"] == "order-to-cash@2"
    unknown = {**STREAM, "processes": ["order", "quote"]}
    refused = await http.put(path, json=unknown, headers=bearer(keys["idn_owner"]))
    assert is_problem(refused, 422) and "quote" in refused.json()["detail"]


async def test_the_map_and_the_lanes_are_read_from_the_records_and_store_nothing(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given)
    await http.put(f"{base}/streams/order-to-cash", json=STREAM, headers=bearer(keys["idn_owner"]))
    run = await a_run(given, "run_9")
    finished = run.model_copy(
        update={
            "process_version": "order@1",
            "state": RunState.FINISHED,
            "updated_at": run.created_at + timedelta(hours=2),
        }
    )
    async with given.persistence.transaction(TENANT):
        await given.runs.put(TENANT, finished)
    before = stored(given)

    drawn = (await http.get(f"{base}/streams", headers=bearer(keys["idn_ada"]))).json()
    (card,) = drawn["core"]
    assert card["stream"] == "order-to-cash" and card["role"] == "sales"
    figures = card["figures"]
    assert figures["autonomy"] == {"2": 1.0} and figures["methods"] == {"human": 0.5, "rule": 0.5}
    assert figures["runs"] == 1 and figures["flow_efficiency"] == 1.0
    (crossing,) = figures["crossings"]
    sales, finance = f"{TENANT}/sales", f"{TENANT}/finance"
    assert (crossing["from_units"], crossing["to_units"]) == ([sales], [finance])
    assert drawn["outside"] == []

    lanes = (
        await http.get(f"{base}/streams/order-to-cash", headers=bearer(keys["idn_ada"]))
    ).json()
    assert [c["process"] for c in lanes["columns"]] == ["order", "invoice"]
    assert [lane["key"] for lane in lanes["lanes"]][2:] == ["role:sales", "role:accounting"]
    assert lanes["units"] == [f"{TENANT}/finance", f"{TENANT}/sales"]
    assert stored(given) == before, "the view stores nothing of its own"

    ada = await given.identities.authenticate(keys["idn_ada"])
    assert ada is not None and ada.org_path == (TENANT, "sales"), "the structure stays as it is"
    missing = await http.get(f"{base}/streams/nothing", headers=bearer(keys["idn_ada"]))
    assert is_problem(missing, 404)


async def test_another_tenant_sees_no_stream_and_no_process_of_this_one(client: Client) -> None:
    http, given, base = client
    keys = await world(given)
    await http.put(f"{base}/streams/order-to-cash", json=STREAM, headers=bearer(keys["idn_owner"]))
    _, elsewhere = await given.identity.person(OTHER, "idn_zed")
    drawn = (await http.get(f"{base}/streams", headers=bearer(elsewhere))).json()
    assert drawn["core"] == [] and drawn["outside"] == []
    assert is_problem(
        await http.get(f"{base}/streams/order-to-cash", headers=bearer(elsewhere)), 404
    )
