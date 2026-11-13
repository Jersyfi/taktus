"""End-to-end chains across domains on the HTTP surface (UC-15.4, ADR-0301 §4, ADR-0302 §3).

What is real: the HTTP surface, registration, the run engine and the composition's
`ChainRuns` over memory. What is proven: only the role `owner` declares, starts and decides a
chain (NTC-0277); a chain that does not hold to its versions is refused; a chain is stored,
started and shown as a whole with its runs; a halted chain goes on with what the person gave;
a reader sees a chain only where they may see every process it links; another tenant sees none.
"""

from __future__ import annotations

from typing import Any

import httpx
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion

from .conftest import OTHER, TENANT, Services
from .test_process_level import bearer
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]


def rule(step_id: str, value: Any) -> dict[str, Any]:
    return {
        "id": step_id,
        "method": "rule",
        "reason": "a value by rule",
        "rejected": [],
        "exactness": "exact",
        "checks": [{"kind": "recomputation"}],
        "work": {"rule": "constant", "value": value},
    }


def order(value: dict[str, Any]) -> dict[str, Any]:
    return instructed(
        {
            "id": "purchase-order",
            "version": "1",
            "name": "Purchase order",
            "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
            "limits": {"quota": {"units": 5}},
            "steps": [rule("order", value)],
        }
    )


BOOKING = instructed(
    {
        "id": "book-invoice",
        "version": "1",
        "name": "Book the invoice",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "limits": {"quota": {"units": 5}},
        "inputs": {
            "order": {"description": "the order number", "example": "PO-1"},
            "amount": {"description": "the ordered amount", "example": "1.00"},
        },
        "steps": [rule("book", {"order": {"$input": "order"}, "amount": {"$input": "amount"}})],
    }
)
CHAIN = {
    "name": "Procure to pay",
    "links": [
        {"process_version": "purchase-order@1"},
        {
            "process_version": "book-invoice@1",
            "handover": [
                {
                    "input": "order",
                    "step": "order",
                    "select": "number",
                    "clause": "the invoice is booked against its order",
                },
                {
                    "input": "amount",
                    "step": "order",
                    "select": "amount",
                    "clause": "the booked amount is the ordered one",
                },
            ],
        },
    ],
    "slo": {"latency": "PT1H"},
}


async def world(given: Services, value: dict[str, Any]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for name, roles in [("idn_owner", ("owner",)), ("idn_ada", ("sales",))]:
        _, keys[name] = await given.identities.add(TENANT, name, (TENANT,), roles=roles)
    register = RegisterProcessVersionHandler(
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
        MemoryRepository(given.persistence, Process),
        ledger=given.ledger,
    )
    for bundle in (order(value), BOOKING):
        await register.execute(RegisterProcessVersion(bundle, tenant=TENANT, by="idn_owner"))
    return keys


async def test_only_the_owner_declares_and_starts_a_chain_and_it_is_shown_as_a_whole(
    client: Client,
) -> None:
    http, given, base = client
    keys = await world(given, {"number": "PO-7", "amount": "120.00"})
    path = f"{base}/chains/procure-to-pay"
    owner, ada = bearer(keys["idn_owner"]), bearer(keys["idn_ada"])
    assert is_problem(await http.put(path, json=CHAIN), 401)
    assert is_problem(await http.put(path, json=CHAIN, headers=ada), 403)
    lacking = {**CHAIN, "links": [CHAIN["links"][0], {**CHAIN["links"][1], "handover": []}]}
    assert is_problem(await http.put(path, json=lacking, headers=owner), 422)
    wrong = {
        **CHAIN,
        "links": [
            CHAIN["links"][0],
            {**CHAIN["links"][1], "handover": [CHAIN["links"][1]["handover"][0]]},
        ],
    }
    refused = await http.put(path, json=wrong, headers=owner)
    assert is_problem(refused, 422) and "gives no 'amount'" in refused.json()["detail"]
    declared = await http.put(path, json=CHAIN, headers=owner)
    assert declared.status_code == 200 and declared.json()["id"] == "procure-to-pay"

    assert is_problem(await http.post(f"{path}/runs", json={}, headers=ada), 403)
    started = await http.post(f"{path}/runs", json={}, headers=owner)
    assert started.status_code == 200, started.text
    run = started.json()
    assert run["state"] == "finished" and len(run["runs"]) == 2 and len(run["handovers"]) == 1
    assert run["measured"] == "met"

    listed = (await http.get(f"{base}/chains", headers=ada)).json()["chains"]
    (card,) = listed
    assert card["id"] == "procure-to-pay" and card["runs"][0]["state"] == "finished"
    shown = (await http.get(path, headers=ada)).json()
    clauses = [i["clause"] for i in shown["links"][1]["handover"]]
    assert clauses == [
        "the invoice is booked against its order",
        "the booked amount is the ordered one",
    ]
    assert shown["slo"] == {"latency": "PT1H"} and [r["id"] for r in shown["runs"]] == [run["id"]]
    assert is_problem(await http.get(f"{base}/chains/nothing", headers=ada), 404)


async def test_a_halted_chain_goes_on_with_what_the_owner_gave(client: Client) -> None:
    http, given, base = client
    keys = await world(given, {"number": "PO-7"})
    owner, ada = bearer(keys["idn_owner"]), bearer(keys["idn_ada"])
    await http.put(f"{base}/chains/procure-to-pay", json=CHAIN, headers=owner)
    halted = (await http.post(f"{base}/chains/procure-to-pay/runs", json={}, headers=owner)).json()
    assert halted["state"] == "halted" and halted["missing"] == ["amount"]
    decision = f"{base}/chain-runs/{halted['id']}/decision"
    assert is_problem(await http.post(decision, json={"stop": True}, headers=ada), 403)
    assert is_problem(await http.post(decision, json={}, headers=owner), 422)
    wrong = await http.post(decision, json={"given": {"order": "PO-8"}}, headers=owner)
    assert is_problem(wrong, 409)
    gone_on = await http.post(decision, json={"given": {"amount": "120.00"}}, headers=owner)
    assert gone_on.status_code == 200 and gone_on.json()["state"] == "finished"
    again = await http.post(decision, json={"stop": True}, headers=owner)
    assert is_problem(again, 409), "a chain that ended is not stopped"


async def test_another_tenant_sees_no_chain_of_this_one(client: Client) -> None:
    http, given, base = client
    keys = await world(given, {"number": "PO-7", "amount": "120.00"})
    await http.put(f"{base}/chains/procure-to-pay", json=CHAIN, headers=bearer(keys["idn_owner"]))
    _, elsewhere = await given.identity.person(OTHER, "idn_zed")
    assert (await http.get(f"{base}/chains", headers=bearer(elsewhere))).json() == {"chains": []}
    assert is_problem(
        await http.get(f"{base}/chains/procure-to-pay", headers=bearer(elsewhere)), 404
    )
